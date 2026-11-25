from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Cycle, Expense, ExpenseSplit, Member, Reminder, Settlement


def fail(message):
    raise ValidationError({"detail": message})


def next_due(day, frequency, anchor=None):
    if frequency != "MONTHLY":
        return day + timedelta(days={"DAILY":1, "WEEKLY":7, "BIWEEKLY":14}[frequency])
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(anchor or day.day, monthrange(year, month)[1]))


def current_cycle(flat):
    return flat.cycle_set.order_by("-month").first()


def participants(flat, cycle=None, trip=None):
    if trip:
        return trip.participants.filter(active=True)
    members = flat.member_set.filter(is_trip_guest=False)
    if cycle and cycle.archived_members:
        return members.filter(pk__in=cycle.archived_members)
    return members.filter(active=True)


def allocate(paise, split_type, entries):
    if not entries or len({row["member"] for row in entries}) != len(entries):
        fail("Select at least one participant and include each participant once.")
    values = [row.get("value", Decimal(1)) if split_type != "EQUAL" else Decimal(1) for row in entries]
    total = sum(values)
    if min(values) < 0 or total <= 0:
        fail("Enter valid, nonnegative split values with a positive total.")
    if split_type == "EXACT":
        amounts = [value * 100 for value in values]
        if sum(amounts) != paise or any(amount != int(amount) for amount in amounts):
            fail("Exact shares must total the expense in rupees and paise.")
        return list(zip(map(int, amounts), values))
    if split_type == "PERCENT" and total != 100:
        fail("Percentages must total 100.")
    raw = [paise * value / total for value in values]
    result = [int(amount) for amount in raw]
    order = sorted(range(len(result)), key=lambda i: (result[i] - raw[i], entries[i]["member"]))
    for i in order[:paise - sum(result)]:
        result[i] += 1
    return list(zip(result, values))


def set_splits(expense, entries, allocation):
    expense.splits.all().delete()
    ExpenseSplit.objects.bulk_create([
        ExpenseSplit(expense=expense, member_id=row["member"], paise=amount, value=value)
        for row, (amount, value) in zip(entries, allocation)
    ])


def simplify(balances):
    positive = {i: v for i, v in balances.items() if v > 0}
    negative = {i: -v for i, v in balances.items() if v < 0}
    transfers = []
    while positive and negative:
        receiver = min(positive, key=lambda i: (-positive[i], i))
        payer = min(negative, key=lambda i: (-negative[i], i))
        amount = min(positive[receiver], negative[payer])
        transfers.append({"payer":payer, "receiver":receiver, "paise":amount})
        positive[receiver] -= amount
        negative[payer] -= amount
        if not positive[receiver]:
            del positive[receiver]
        if not negative[payer]:
            del negative[payer]
    return transfers


def ledger(flat, cycle=None, trip=None, all_months=False):
    expenses = flat.expense_set.filter(deleted=False, trip=trip)
    payments = flat.settlement_set.filter(trip=trip)
    if not all_months:
        expenses = expenses.filter(cycle=cycle)
        payments = payments.filter(cycle=cycle)
    paid, shares, net = (defaultdict(int) for _ in range(3))
    ids = set(participants(flat, cycle, trip).values_list("id", flat=True))
    for expense in expenses.prefetch_related("splits"):
        paid[expense.payer_id] += expense.paise
        net[expense.payer_id] += expense.paise
        ids.add(expense.payer_id)
        for split in expense.splits.all():
            shares[split.member_id] += split.paise
            net[split.member_id] -= split.paise
            ids.add(split.member_id)
    for payment in payments.filter(status="CONFIRMED"):
        net[payment.payer_id] += payment.paise
        net[payment.receiver_id] -= payment.paise
        ids.update([payment.payer_id, payment.receiver_id])
    count = participants(flat, cycle, trip).count()
    total = sum(paid.values())
    return {"total":total, "count":count, "dividend": (total + count // 2) // count if count else 0,
            "balances":[{"member":i,"paid":paid[i],"share":shares[i],"net":net[i]} for i in sorted(ids)],
            "transfers":simplify(net), "pending":payments.filter(status="PENDING").aggregate(total=Sum("paise"))["total"] or 0}


def refresh_closed_status(cycle):
    if cycle and cycle.status != "ACTIVE":
        cycle.status = "SETTLED" if not ledger(cycle.flat, cycle=cycle)["transfers"] else "CLOSED"
        cycle.save(update_fields=["status", "updated_at"])


def generate_recurring(flat, through):
    templates = flat.expense_set.filter(source__isnull=True, deleted=False, trip__isnull=True).exclude(frequency="")
    for source in templates.prefetch_related("splits"):
        when = next_due(source.date, source.frequency, source.date.day)
        while when <= through:
            cycle, _ = Cycle.objects.get_or_create(flat=flat, month=when.strftime("%Y-%m"))
            if cycle.status == "ACTIVE":
                eligible = set(participants(flat, cycle).values_list("id", flat=True))
                entries = [{"member":s.member_id,"value":s.value} for s in source.splits.all() if s.member_id in eligible]
                complete = len(entries) == len(source.splits.all())
                if entries and source.payer_id in eligible and (complete or source.split_type in ["EQUAL","SHARES"]):
                    instance, created = Expense.objects.get_or_create(flat=flat, source=source, date=when, defaults={
                        "cycle":cycle,"title":source.title,"paise":source.paise,"category":source.category,
                        "payer":source.payer,"notes":source.notes,"split_type":source.split_type,
                    })
                    if created:
                        set_splits(instance, entries, allocate(instance.paise, instance.split_type, entries))
            when = next_due(when, source.frequency, source.date.day)


def add_reminder(flat, recipient, kind, key, title, notes=""):
    Reminder.objects.get_or_create(flat=flat, recipient=recipient, key=key,
                                  defaults={"kind":kind,"title":title,"notes":notes})


def generate_reminders(flat, today):
    cycle = current_cycle(flat)
    members = flat.member_set.filter(active=True, user__isnull=False, is_trip_guest=False)
    for member in members:
        if today.day == 1:
            add_reminder(flat, member, "RENT", f"rent:{today:%Y-%m}", "Rent is due today")
        for chore in flat.chore_set.filter(assigned=member, active=True, due__lt=today):
            add_reminder(flat, member, "CHORE", f"chore:{chore.pk}:{chore.due}", f"Overdue: {chore.title}")
        for item in flat.maintenance_set.filter(reported_by=member).exclude(status="REPORTED"):
            add_reminder(flat, member, "MAINTENANCE", f"maintenance:{item.pk}:{item.status}", item.title, item.get_status_display())
        for source in flat.expense_set.filter(source__isnull=True, deleted=False, payer=member).exclude(frequency=""):
            when = next_due(source.date, source.frequency, source.date.day)
            while when < today:
                when = next_due(when, source.frequency, source.date.day)
            if when <= today + timedelta(days=3):
                add_reminder(flat, member, "RECURRING", f"bill:{source.pk}:{when}", f"Upcoming bill: {source.title}", str(when))
    for payment in flat.settlement_set.filter(status="PENDING", payer__in=members):
        add_reminder(flat, payment.payer, "PAYMENT", f"payment:{payment.pk}", f"Settlement pending with {payment.receiver.name}")
    if cycle:
        for transfer in ledger(flat, cycle=cycle)["transfers"]:
            member = members.filter(pk=transfer["payer"]).first()
            if member:
                add_reminder(flat, member, "BALANCE", f"balance:{cycle.pk}:{transfer['receiver']}:{today:%Y-%m}", "You have an outstanding household balance")

