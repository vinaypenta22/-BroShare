from datetime import date
from urllib.parse import urlencode

import qrcode

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from . import models as m, serializers as s
from .services import (allocate, current_cycle, fail, generate_recurring, ledger, next_due,
                       participants, refresh_closed_status, set_splits)


class Login(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class Refresh(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class Registration(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    class Meta:
        model = get_user_model()
        fields = ["username","email","password"]


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def register(request):
    serializer = Registration(data=request.data)
    serializer.is_valid(raise_exception=True)
    candidate = get_user_model()(**serializer.validated_data)
    try:
        password_validation.validate_password(candidate.password, candidate)
        with transaction.atomic():
            user = get_user_model().objects.create_user(**serializer.validated_data)
    except DjangoValidationError as error:
        raise serializers.ValidationError({"password":error.messages}) from error
    except IntegrityError:
        fail("This username is already registered.")
    return Response({"id":user.pk,"username":user.username}, status=201)


register.cls.throttle_scope = "auth"


@api_view(["POST"])
def logout(request):
    try:
        token = RefreshToken(request.data.get("refresh", ""))
        if str(token.get("user_id")) == str(request.user.pk):
            token.blacklist()
    except TokenError:
        pass
    return Response(status=204)


@api_view(["GET", "PATCH"])
def me(request):
    user = request.user
    if request.method == "PATCH":
        field = serializers.EmailField(allow_blank=True)
        user.email = field.run_validation(request.data.get("email", user.email))
        user.save(update_fields=["email"])
    memberships = m.Member.objects.filter(user=user,active=True).select_related("flat")
    return Response({"username":user.username,"email":user.email,"flats":[
        {"id":x.flat_id,"name":x.flat.name,"member":x.pk,"role":x.role} for x in memberships
    ]})


def membership(request):
    try:
        flat_id = int(request.headers.get("X-Flat-ID","0"))
    except ValueError:
        fail("Invalid flat ID.")
    query = m.Member.objects.filter(user=request.user, active=True, is_trip_guest=False).select_related("flat")
    member = query.filter(flat_id=flat_id).first() if flat_id else query.order_by("id").first()
    if not member:
        raise PermissionDenied("Choose a flat you belong to.")
    return member


def touch(flat):
    m.Flat.objects.filter(pk=flat.pk).update(updated_at=timezone.now())


@api_view(["POST"])
def flats(request):
    name = serializers.CharField(max_length=120).run_validation(request.data.get("name",""))
    with transaction.atomic():
        if request.data.get("invite"):
            flat = get_object_or_404(m.Flat.objects.select_for_update(), invite=request.data["invite"])
            member, created = m.Member.objects.get_or_create(flat=flat,user=request.user,defaults={"name":name})
            if not member.active:
                raise PermissionDenied("Ask the flat lead to restore your access.")
        else:
            flat = m.Flat.objects.create(name=name,created_by=request.user)
            m.Member.objects.create(flat=flat,user=request.user,name=request.user.get_full_name() or request.user.username,role="LEAD")
            m.Cycle.objects.create(flat=flat,month=timezone.localdate().strftime("%Y-%m"))
        touch(flat)
    return Response({"id":flat.pk},status=201)


@api_view(["GET","POST","PATCH"])
def workspace(request):
    member = membership(request)
    flat = member.flat
    if request.method != "GET":
        if member.role != "LEAD":
            raise PermissionDenied("Only a flat lead can change workspace settings.")
        with transaction.atomic():
            flat = m.Flat.objects.select_for_update().get(pk=flat.pk)
            if request.method == "POST":
                flat.invite = m.invite_code()
            else:
                flat.name = serializers.CharField(max_length=120).run_validation(request.data.get("name",""))
            flat.save()
    return Response({"name":flat.name,"invite":flat.invite if member.role == "LEAD" else None})


@api_view(["GET"])
def sync(request):
    member = membership(request)
    return Response({"updated_at":member.flat.updated_at.isoformat()})


class Page(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class ScopedView(viewsets.ModelViewSet):
    pagination_class = Page
    lead_only = False
    http_method_names = ["get","post","put","patch","delete","head","options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request,*args,**kwargs)
        self.member = membership(request)
        self.flat = self.member.flat
        if request.method not in ["GET","HEAD","OPTIONS"]:
            self.flat = m.Flat.objects.select_for_update().get(pk=self.flat.pk)
            self.member.refresh_from_db()
            if not self.member.active:
                raise PermissionDenied()
            if self.lead_only and self.member.role != "LEAD":
                raise PermissionDenied("Only the flat lead can perform this action.")

    def dispatch(self, request, *args, **kwargs):
        if request.method in ["GET","HEAD","OPTIONS"]:
            return super().dispatch(request,*args,**kwargs)
        try:
            with transaction.atomic():
                response = super().dispatch(request,*args,**kwargs)
                if response.status_code >= 400:
                    transaction.set_rollback(True)
                elif hasattr(self,"flat"):
                    touch(self.flat)
                return response
        except IntegrityError:
            return Response({"detail":"This change conflicts with an existing record."},status=409)

    def get_serializer_context(self):
        return {**super().get_serializer_context(),"flat":self.flat}

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.filter(flat=self.flat).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(flat=self.flat)


class Members(ScopedView):
    serializer_class = s.MemberSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("id")

    def perform_create(self, serializer):
        if self.member.role != "LEAD":
            raise PermissionDenied()
        serializer.save(flat=self.flat)

    def perform_update(self, serializer):
        target = serializer.instance
        if self.member.role != "LEAD" and (target.pk != self.member.pk or "role" in self.request.data):
            raise PermissionDenied()
        if target.role == "LEAD" and serializer.validated_data.get("role") == "MEMBER":
            if not self.get_queryset().filter(role="LEAD",active=True,user__isnull=False).exclude(pk=target.pk).exists():
                fail("The flat needs at least one signed-in lead.")
        serializer.save()

    def perform_destroy(self, instance):
        if self.member.role != "LEAD" or instance.pk == self.member.pk:
            raise PermissionDenied()
        if instance.role == "LEAD" and instance.user_id and not self.get_queryset().filter(
            role="LEAD",active=True,user__isnull=False
        ).exclude(pk=instance.pk).exists():
            fail("The flat needs at least one signed-in lead.")
        instance.active = False
        instance.save(update_fields=["active","updated_at"])

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        if self.member.role != "LEAD":
            raise PermissionDenied()
        member = self.get_object()
        member.active = True
        member.save(update_fields=["active","updated_at"])
        return Response(self.get_serializer(member).data)

    @action(detail=False, methods=["post"])
    def guest(self, request):
        serializer = self.get_serializer(data={"name":request.data.get("name"),"upi":request.data.get("upi",""),"role":"MEMBER"})
        serializer.is_valid(raise_exception=True)
        trip_id = request.data.get("trip")
        trip = get_object_or_404(self.flat.trip_set.filter(archived=False),pk=trip_id) if trip_id else None
        guest = serializer.save(flat=self.flat,is_trip_guest=True)
        if trip:
            trip.participants.add(guest)
        return Response(self.get_serializer(guest).data,status=201)


class Cycles(ScopedView):
    serializer_class = s.CycleSerializer
    lead_only = True

    def get_queryset(self):
        return super().get_queryset().order_by("-month")

    def update(self, request, *args, **kwargs):
        fail("Use the close and reopen actions to manage a cycle.")

    def destroy(self, request, *args, **kwargs):
        fail("Billing cycles are kept for financial history.")

    @action(detail=False, methods=["post"], url_path="settle-month")
    def settle_month(self, request):
        cycle = get_object_or_404(self.get_queryset(),pk=request.data.get("cycle"))
        when = next_due(date.fromisoformat(cycle.month+"-01"),"MONTHLY")
        if cycle.status == "ACTIVE":
            data = ledger(self.flat,cycle=cycle)
            pending = set(cycle.settlement_set.filter(status="PENDING").values_list("payer_id","receiver_id","paise"))
            m.Settlement.objects.bulk_create([
                m.Settlement(flat=self.flat,cycle=cycle,date=when,status="PENDING",
                             payer_id=transfer["payer"],receiver_id=transfer["receiver"],paise=transfer["paise"])
                for transfer in data["transfers"] if (transfer["payer"],transfer["receiver"],transfer["paise"]) not in pending
            ])
            cycle.archived_members = list(participants(self.flat,cycle).values_list("pk",flat=True))
            cycle.closed_at = timezone.now()
            cycle.status = "CLOSED" if data["transfers"] else "SETTLED"
            cycle.save()
        following, _ = m.Cycle.objects.get_or_create(flat=self.flat,month=when.strftime("%Y-%m"))
        if request.data.get("rollover") is True:
            generate_recurring(self.flat,when)
        return Response({"cycle":following.pk})

    @action(detail=False, methods=["post"])
    def reopen(self, request):
        cycle = get_object_or_404(self.get_queryset(),pk=request.data.get("cycle"))
        cycle.status = "ACTIVE"
        cycle.save(update_fields=["status","updated_at"])
        return Response(self.get_serializer(cycle).data)


class Trips(ScopedView):
    serializer_class = s.TripSerializer

    def perform_update(self, serializer):
        serializer.save()

    def get_queryset(self):
        return super().get_queryset().filter(archived=False)

    def perform_destroy(self, instance):
        if self.member.role != "LEAD":
            raise PermissionDenied()
        instance.archived = True
        instance.save(update_fields=["archived","updated_at"])


class Expenses(ScopedView):
    serializer_class = s.ExpenseSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(deleted=False).prefetch_related("splits").order_by("-date","-id")
        params = self.request.query_params
        for query, field in [("cycle","cycle_id"),("trip","trip_id"),("payer","payer_id"),("category","category")]:
            if params.get(query):
                value = params[query]
                if field.endswith("_id") and not value.isdecimal():
                    fail("Invalid expense filter.")
                qs = qs.filter(**{field:value})
        if params.get("scope") in ["room","trip"]:
            qs = qs.filter(trip__isnull=params["scope"] == "room")
        if params.get("search"):
            qs = qs.filter(Q(title__icontains=params["search"]) | Q(notes__icontains=params["search"]))
        return qs

    def perform_create(self, serializer):
        expense = serializer.save(flat=self.flat)
        set_splits(expense,serializer.entries,serializer.allocation)

    def perform_update(self, serializer):
        expense = serializer.save()
        set_splits(expense,serializer.entries,serializer.allocation)

    def perform_destroy(self, instance):
        if instance.cycle and instance.cycle.status != "ACTIVE":
            fail("Reopen this cycle before deleting an expense.")
        if instance.trip and instance.trip.archived:
            fail("This trip is archived.")
        instance.deleted = True
        instance.save(update_fields=["deleted","updated_at"])


class Settlements(ScopedView):
    serializer_class = s.SettlementSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("-date","-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        key = data.get("request_key")
        if not key:
            fail("A unique request key is required.")
        existing = self.get_queryset().filter(request_key=key).first()
        if existing:
            if any(getattr(existing, field) != data.get(field) for field in ("payer","receiver","paise","cycle","trip")):
                fail("This request key was already used for another transfer.")
            return Response(self.get_serializer(existing).data)
        cycle, trip = data.get("cycle"), data.get("trip")
        if bool(cycle) == bool(trip):
            fail("Select one ledger for this transfer.")
        self.validate_payment(cycle,trip,data["payer"].pk,data["receiver"].pk,data["paise"])
        pending = cycle.settlement_set.filter(status="PENDING", payer=data["payer"],receiver=data["receiver"],paise=data["paise"]).first() if cycle else None
        if pending:
            fail("Confirm the existing pending settlement from its history entry.")
        item = serializer.save(flat=self.flat)
        refresh_closed_status(cycle)
        return Response(self.get_serializer(item).data,status=201)

    def validate_payment(self, cycle, trip, payer, receiver, amount):
        balances = {row["member"]:row["net"] for row in ledger(self.flat,cycle,trip)["balances"]}
        if payer == receiver or amount > min(-balances.get(payer,0),balances.get(receiver,0)):
            fail("This amount exceeds the outstanding balance. Refresh and review the transfer.")

    def update(self, request, *args, **kwargs):
        fail("Use confirm or reverse to change a settlement.")

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        item = self.get_object()
        if item.status == "CONFIRMED":
            return Response(self.get_serializer(item).data)
        if item.status != "PENDING" or (item.trip and item.trip.archived):
            fail("This settlement cannot be confirmed.")
        self.validate_payment(item.cycle,item.trip,item.payer_id,item.receiver_id,item.paise)
        field = serializers.ChoiceField(choices=["UPI","CASH","BANK"])
        item.method = field.run_validation(request.data.get("method",item.method))
        item.reference = serializers.CharField(max_length=100,allow_blank=True).run_validation(request.data.get("reference",""))
        item.notes = serializers.CharField(max_length=2000,allow_blank=True).run_validation(request.data.get("notes",""))
        item.status = "CONFIRMED"
        item.save()
        refresh_closed_status(item.cycle)
        return Response(self.get_serializer(item).data)

    def perform_destroy(self, item):
        if self.member.role != "LEAD" and item.payer_id != self.member.pk:
            raise PermissionDenied()
        item.status = "REVERSED"
        item.save(update_fields=["status","updated_at"])
        refresh_closed_status(item.cycle)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        item = self.get_object()
        self.perform_destroy(item)
        return Response(self.get_serializer(item).data)


class Chores(ScopedView):
    serializer_class = s.ChoreSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("logs")

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active","updated_at"])

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        chore = self.get_object()
        if not chore.active:
            fail("This chore is archived.")
        if request.data.get("due") != chore.due.isoformat():
            fail("This occurrence has already changed. Refresh before completing it.")
        m.ChoreLog.objects.create(flat=self.flat,chore=chore,member=chore.assigned,due=chore.due,points=chore.points)
        ids = list(participants(self.flat).order_by("id").values_list("pk",flat=True))
        if ids:
            chore.assigned_id = next((i for i in ids if i > chore.assigned_id),ids[0])
        chore.due = next_due(chore.due,chore.frequency)
        chore.save()
        return Response(self.get_serializer(m.Chore.objects.get(pk=chore.pk)).data)

    @action(detail=True, methods=["post"])
    def swap(self, request, pk=None):
        chore = self.get_object()
        member = get_object_or_404(participants(self.flat),pk=request.data.get("member"))
        chore.assigned = member
        chore.save()
        return Response(self.get_serializer(chore).data)


class Maintenance(ScopedView):
    serializer_class = s.MaintenanceSerializer

    def perform_create(self, serializer):
        serializer.save(flat=self.flat,reported_by=self.member,
                        resolved=timezone.localdate() if serializer.validated_data.get("status") == "RESOLVED" else None)

    def perform_update(self, serializer):
        item = serializer.instance
        status = serializer.validated_data.get("status",item.status)
        serializer.save(resolved=(item.resolved or timezone.localdate()) if status == "RESOLVED" else None)

    @action(detail=True,methods=["post"],url_path="convert-to-expense")
    def convert(self, request, pk=None):
        item = self.get_object()
        if item.expense_id:
            return Response({"expense":item.expense_id})
        today = timezone.localdate()
        cycle = current_cycle(self.flat)
        if not cycle or cycle.status != "ACTIVE":
            fail("Open a billing cycle before converting this request.")
        payer = get_object_or_404(participants(self.flat,cycle),pk=request.data.get("payer"))
        paise = item.actual or item.estimated
        if not paise:
            fail("Set a cost before converting the request.")
        expense = m.Expense.objects.create(flat=self.flat, cycle=cycle, payer=payer, paise=paise,
            date=today if today.strftime("%Y-%m") == cycle.month else date.fromisoformat(cycle.month+"-01"),
            title=item.title, category="Maintenance", notes=item.notes)
        rows = [{"member":i} for i in participants(self.flat,cycle).values_list("pk",flat=True)]
        set_splits(expense,rows,allocate(paise,"EQUAL",rows))
        item.expense = expense
        item.save()
        return Response({"expense":expense.pk},status=201)


class Reminders(ScopedView):
    serializer_class = s.ReminderSerializer

    def get_queryset(self):
        return super().get_queryset().filter(recipient=self.member,dismissed=False).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(flat=self.flat,recipient=self.member)

    def perform_destroy(self, instance):
        instance.dismissed = True
        instance.save(update_fields=["dismissed","updated_at"])


@api_view(["GET"])
def summary(request):
    flat = membership(request).flat
    if request.query_params.get("trip"):
        trip = get_object_or_404(flat.trip_set.filter(archived=False),pk=request.query_params["trip"])
        return Response(ledger(flat,trip=trip))
    month = request.query_params.get("cycle")
    if month == "all":
        return Response(ledger(flat,all_months=True))
    cycle = get_object_or_404(flat.cycle_set,pk=month) if month else current_cycle(flat)
    return Response(ledger(flat,cycle=cycle))


@api_view(["GET"])
def reports(request, kind):
    flat = membership(request).flat
    qs = flat.expense_set.filter(deleted=False)
    if kind == "settlements":
        return Response(s.SettlementSerializer(flat.settlement_set.all(),many=True,context={"flat":flat}).data)
    if kind == "contributions":
        return Response(ledger(flat,all_months=True)["balances"])
    if kind == "trips":
        rows = qs.filter(trip__archived=False).values("trip__name").annotate(total=Sum("paise"))
        return Response([{"name":r["trip__name"],"total":r["total"]} for r in rows])
    qs = qs.filter(trip__isnull=True)
    field = {"monthly":"cycle__month","categories":"category"}.get(kind)
    if not field:
        fail("Unknown report.")
    rows = qs.values(field).annotate(total=Sum("paise")).order_by(field)
    return Response([{"name":r[field],"total":r["total"]} for r in rows])



@api_view(["POST"])
def payment_qr(request):
    flat = membership(request).flat
    receiver_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("receiver"))
    amount = serializers.IntegerField(min_value=1,max_value=2147483647).run_validation(request.data.get("paise"))
    receiver = get_object_or_404(flat.member_set,pk=receiver_id)
    if not receiver.upi:
        fail("This flatmate has no UPI ID.")
    link = "upi://pay?" + urlencode({"pa":receiver.upi,"pn":receiver.name,
        "am":f"{amount // 100}.{amount % 100:02}","cu":"INR","tn":"BroShare settlement"})
    code = qrcode.QRCode(border=4)
    code.add_data(link)
    code.make(fit=True)
    matrix = code.get_matrix()
    return Response({"link":link,"size":len(matrix),"path":"".join(
        f"M{x} {y}h1v1h-1z" for y,row in enumerate(matrix) for x,cell in enumerate(row) if cell
    )})

