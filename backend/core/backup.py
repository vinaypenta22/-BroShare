from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ForeignKey
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from . import models as m
from .services import allocate, fail
from .views import membership

TABLES = (m.Member,m.Cycle,m.Trip,m.TripParticipant,m.Expense,m.ExpenseSplit,
          m.Settlement,m.Chore,m.ChoreLog,m.Maintenance,m.Reminder)
SKIP = {"id","flat","user","request_key","archived_members"}


def fields(model):
    return [field for field in model._meta.concrete_fields if field.name not in SKIP]


@api_view(["GET"])
def export_data(request):
    actor = membership(request)
    if actor.role != "LEAD":
        raise PermissionDenied()
    flat = actor.flat
    tables = {}
    for model in TABLES:
        query = model.objects.filter(**{{
            m.TripParticipant:"trip__flat",m.ExpenseSplit:"expense__flat"
        }.get(model,"flat"):flat})
        if model is m.Reminder:
            query = query.filter(recipient=actor)
        tables[model._meta.model_name] = [
            {"id":obj.pk, **{f.attname:getattr(obj,f.attname) for f in fields(model)},
             **({"archived_members":obj.archived_members} if model is m.Cycle else {})}
            for obj in query.order_by("pk")
        ]
    return Response({"version":1,"name":flat.name,"owner":actor.pk,"tables":tables})


@api_view(["POST"])
def import_data(request):
    actor = membership(request)
    if actor.role != "LEAD":
        raise PermissionDenied()
    if request.data.get("confirmed") is not True:
        fail("Confirm the import before continuing.")
    backup = request.data.get("backup")
    if not isinstance(backup,dict) or backup.get("version") != 1:
        fail("Select a BroShare version 1 export.")
    tables = backup.get("tables")
    if not isinstance(tables,dict) or set(tables) != {x._meta.model_name for x in TABLES}:
        fail("This export is missing required tables.")
    if any(not isinstance(rows,list) for rows in tables.values()) or sum(map(len,tables.values())) > 10000:
        fail("The export has invalid tables or exceeds 10,000 records.")
    if not isinstance(backup.get("name"),str) or not backup["name"].strip():
        fail("The export must have a workspace name.")
    mapping = defaultdict(dict)
    try:
        with transaction.atomic():
            flat = m.Flat.objects.create(name=(backup["name"][:105]+" · imported"),created_by=request.user)
            for model in TABLES:
                for item in tables[model._meta.model_name]:
                    old_id = item["id"]
                    if type(old_id) is not int or old_id < 1 or old_id in mapping[model]:
                        raise ValueError
                    data = {"flat":flat} if hasattr(model,"flat_id") else {}
                    times = {}
                    for f in fields(model):
                        value = item[f.attname]
                        if getattr(f,"auto_now",False) or getattr(f,"auto_now_add",False):
                            times[f.attname] = f.to_python(value)
                        else:
                            data[f.attname] = mapping[f.related_model][value] if isinstance(f,ForeignKey) and value is not None else value
                    if model is m.Member:
                        data["role"] = "MEMBER"
                        if old_id == backup.get("owner"):
                            data.update(user=request.user,role="LEAD",active=True,is_trip_guest=False)
                    if model is m.Cycle:
                        import re
                        if not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])",data["month"]) or data["month"] > "9998-12":
                            raise ValueError
                        data["archived_members"] = [mapping[m.Member][pk] for pk in item.get("archived_members",[])]
                    obj = model(**data)
                    obj.full_clean(exclude=list(times))
                    obj.save()
                    if times:
                        model.objects.filter(pk=obj.pk).update(**times)
                    mapping[model][old_id] = obj.pk
            if not flat.member_set.filter(user=request.user,role="LEAD").exists():
                raise ValueError
            for expense in flat.expense_set.prefetch_related("splits"):
                rows = list(expense.splits.all())
                allocation = allocate(expense.paise,expense.split_type,[{"member":x.member_id,"value":x.value} for x in rows])
                if [x.paise for x in rows] != [amount for amount,_ in allocation]:
                    raise ValueError
                if expense.cycle_id and (expense.date.strftime("%Y-%m") != expense.cycle.month or
                        expense.payer.is_trip_guest or any(row.member.is_trip_guest for row in rows)):
                    raise ValueError
            for payment in flat.settlement_set.filter(cycle__isnull=False).select_related("payer","receiver"):
                if payment.payer.is_trip_guest or payment.receiver.is_trip_guest:
                    raise ValueError
            if not flat.cycle_set.exists():
                m.Cycle.objects.create(flat=flat,month=timezone.localdate().strftime("%Y-%m"))
    except (ValidationError,KeyError,ValueError,TypeError,AttributeError,IntegrityError,OverflowError):
        fail("The backup contains invalid records. No workspace was imported.")
    return Response({"id":flat.pk,"name":flat.name},status=201)


