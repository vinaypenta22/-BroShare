import secrets
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def invite_code():
    return secrets.token_urlsafe(24)


class Flat(models.Model):
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    invite = models.CharField(max_length=40, unique=True, default=invite_code)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Scoped(models.Model):
    flat = models.ForeignKey(Flat, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Member(Scoped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=10, choices=[("LEAD", "Flat lead"), ("MEMBER", "Flatmate")], default="MEMBER")
    upi = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=7, default="#cee9dd")
    is_trip_guest = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["flat", "user"], name="one_user_per_flat")]


class Cycle(Scoped):
    month = models.CharField(max_length=7)
    status = models.CharField(max_length=8, choices=[(s, s) for s in ["ACTIVE", "SETTLED", "CLOSED"]], default="ACTIVE")
    closed_at = models.DateTimeField(null=True, blank=True)
    archived_members = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-month"]
        constraints = [models.UniqueConstraint(fields=["flat", "month"], name="unique_month")]


class Trip(Scoped):
    name = models.CharField(max_length=120)
    destination = models.CharField(max_length=120)
    start = models.DateField()
    end = models.DateField()
    budget = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=[(s,s) for s in ["PLANNED","ACTIVE","COMPLETED"]], default="PLANNED")
    participants = models.ManyToManyField(Member, through="TripParticipant")
    archived = models.BooleanField(default=False)


class TripParticipant(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["trip","member"], name="unique_trip_member")]


FREQUENCIES = [(s,s) for s in ["WEEKLY","BIWEEKLY","MONTHLY"]]
CATEGORIES = ["Rent", "Groceries", "Electricity", "Wi-Fi & Internet", "Cook & Maid", "Water & Gas",
              "Household Supplies", "Food & Dining", "Entertainment", "Maintenance", "Trip", "Other"]
SPLITS = [(s,s) for s in ["EQUAL","EXACT","PERCENT","SHARES"]]


class Expense(Scoped):
    cycle = models.ForeignKey(Cycle, null=True, blank=True, on_delete=models.PROTECT)
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=140)
    paise = models.PositiveIntegerField()
    category = models.CharField(max_length=40, choices=[(s,s) for s in CATEGORIES])
    payer = models.ForeignKey(Member, on_delete=models.PROTECT)
    date = models.DateField()
    notes = models.TextField(blank=True)
    split_type = models.CharField(max_length=8, choices=SPLITS, default="EQUAL")
    frequency = models.CharField(max_length=8, choices=FREQUENCIES, blank=True)
    source = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(cycle__isnull=False, trip__isnull=True) | Q(cycle__isnull=True, trip__isnull=False), name="expense_one_scope"),
            models.CheckConstraint(condition=Q(paise__gt=0), name="expense_positive"),
            models.UniqueConstraint(fields=["source","date"], name="unique_recurrence"),
        ]


class ExpenseSplit(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="splits")
    member = models.ForeignKey(Member, on_delete=models.PROTECT)
    paise = models.PositiveIntegerField()
    value = models.DecimalField(max_digits=12, decimal_places=4, default=1)

    class Meta:
        ordering = ["member_id"]
        constraints = [models.UniqueConstraint(fields=["expense","member"], name="unique_split")]


class Settlement(Scoped):
    cycle = models.ForeignKey(Cycle, null=True, blank=True, on_delete=models.PROTECT)
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.PROTECT)
    payer = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="+")
    receiver = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="+")
    paise = models.PositiveIntegerField()
    method = models.CharField(max_length=8, choices=[(s,s) for s in ["UPI","CASH","BANK"]], default="UPI")
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=9, choices=[(s,s) for s in ["PENDING","CONFIRMED","REVERSED"]], default="CONFIRMED")
    request_key = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-date","-id"]
        constraints = [
            models.CheckConstraint(condition=Q(cycle__isnull=False, trip__isnull=True) | Q(cycle__isnull=True, trip__isnull=False), name="settlement_one_scope"),
            models.CheckConstraint(condition=Q(paise__gt=0) & ~Q(payer=models.F("receiver")), name="valid_settlement"),
            models.UniqueConstraint(fields=["flat","request_key"], name="unique_payment_request"),
            models.UniqueConstraint(fields=["flat","reference"], condition=~Q(reference="") & Q(status="CONFIRMED"), name="unique_confirmed_reference"),
        ]


class Chore(Scoped):
    title = models.CharField(max_length=140)
    assigned = models.ForeignKey(Member, on_delete=models.PROTECT)
    frequency = models.CharField(max_length=8, choices=[("DAILY","DAILY"), *FREQUENCIES])
    points = models.PositiveSmallIntegerField(default=1)
    due = models.DateField()
    active = models.BooleanField(default=True)


class ChoreLog(Scoped):
    chore = models.ForeignKey(Chore, related_name="logs", on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.PROTECT)
    due = models.DateField()
    points = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["chore","due"], name="unique_chore_completion")]


class Maintenance(Scoped):
    title = models.CharField(max_length=140)
    notes = models.TextField(blank=True)
    technician = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=8, choices=[(s,s) for s in ["LOW","MEDIUM","HIGH","URGENT"]])
    status = models.CharField(max_length=12, choices=[(s,s) for s in ["REPORTED","SCHEDULED","IN_PROGRESS","RESOLVED"]], default="REPORTED")
    estimated = models.PositiveIntegerField(default=0)
    actual = models.PositiveIntegerField(default=0)
    resolved = models.DateField(null=True, blank=True)
    reported_by = models.ForeignKey(Member, on_delete=models.PROTECT)
    expense = models.OneToOneField(Expense, null=True, blank=True, on_delete=models.PROTECT)


class Reminder(Scoped):
    recipient = models.ForeignKey(Member, on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    kind = models.CharField(max_length=20, default="CUSTOM")
    key = models.CharField(max_length=120, null=True, blank=True)
    read = models.BooleanField(default=False)
    dismissed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["recipient","key"], name="unique_reminder")]

