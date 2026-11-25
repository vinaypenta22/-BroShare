from rest_framework import serializers

from . import models as m
from .services import allocate, participants


class ModelSerializer(serializers.ModelSerializer):
    class Meta:
        read_only_fields = ["id","flat","created_at","updated_at"]
        exclude = ["flat"]


class MemberSerializer(ModelSerializer):
    class Meta(ModelSerializer.Meta):
        model = m.Member
        read_only_fields = [*ModelSerializer.Meta.read_only_fields, "user", "active", "is_trip_guest"]

    def validate_upi(self, value):
        import re
        if value and not re.fullmatch(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+", value):
            raise serializers.ValidationError("Enter a UPI ID such as name@bank.")
        return value


class CycleSerializer(ModelSerializer):
    month = serializers.RegexField(r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")

    class Meta(ModelSerializer.Meta):
        model = m.Cycle
        read_only_fields = [*ModelSerializer.Meta.read_only_fields, "status","closed_at","archived_members"]

    def validate_month(self, value):
        if value > "9998-12":
            raise serializers.ValidationError("Invalid billing month.")
        return value


class TripSerializer(ModelSerializer):
    participants = serializers.PrimaryKeyRelatedField(many=True, queryset=m.Member.objects.none())

    class Meta(ModelSerializer.Meta):
        model = m.Trip
        read_only_fields = [*ModelSerializer.Meta.read_only_fields, "archived"]

    def get_fields(self):
        fields = super().get_fields()
        fields["participants"].child_relation.queryset = self.context["flat"].member_set.all()
        return fields

    def validate(self, attrs):
        get = lambda key: attrs.get(key, getattr(self.instance, key, None))
        if get("end") < get("start"):
            raise serializers.ValidationError("End date must be on or after the start date.")
        if "participants" in attrs and not attrs["participants"]:
            raise serializers.ValidationError("Select at least one trip participant.")
        if "participants" in attrs:
            old = set(self.instance.participants.values_list("id", flat=True)) if self.instance else set()
            if any(not member.active and member.pk not in old for member in attrs["participants"]):
                raise serializers.ValidationError("New trip participants must be active.")
        return attrs


class SplitSerializer(serializers.Serializer):
    member = serializers.IntegerField(source="member_id")
    value = serializers.DecimalField(max_digits=12, decimal_places=4, required=False)
    paise = serializers.IntegerField(read_only=True)


class ExpenseSerializer(ModelSerializer):
    splits = SplitSerializer(many=True)

    class Meta(ModelSerializer.Meta):
        model = m.Expense
        read_only_fields = [*ModelSerializer.Meta.read_only_fields, "deleted","source"]
        extra_kwargs = {"paise":{"min_value":1}}

    def get_fields(self):
        fields = super().get_fields()
        flat = self.context["flat"]
        for field, qs in [("cycle",flat.cycle_set.all()),("trip",flat.trip_set.filter(archived=False)),("payer",flat.member_set.all())]:
            fields[field].queryset = qs
        return fields

    def validate(self, attrs):
        get = lambda key, default=None: attrs.get(key, getattr(self.instance, key, default))
        cycle, trip, payer = get("cycle"), get("trip"), get("payer")
        if bool(cycle) == bool(trip):
            raise serializers.ValidationError("Select exactly one billing month or trip.")
        if self.instance and (cycle != self.instance.cycle or trip != self.instance.trip):
            raise serializers.ValidationError("An expense cannot change its ledger.")
        if cycle and (cycle.status != "ACTIVE" or get("date").strftime("%Y-%m") != cycle.month):
            raise serializers.ValidationError("Choose a date in an open billing cycle.")
        if trip and (get("frequency") or not trip.start <= get("date") <= trip.end):
            raise serializers.ValidationError("Trip expenses must be one-time and dated within the trip.")
        eligible = set(participants(self.context["flat"], cycle, trip).values_list("id", flat=True))
        if self.instance:
            eligible.update(self.instance.splits.values_list("member_id", flat=True))
            eligible.add(self.instance.payer_id)
        rows = attrs.pop("splits", None)
        if rows is None:
            rows = [{"member_id":s.member_id,"value":s.value} for s in self.instance.splits.all()]
        self.entries = [{"member":row["member_id"],"value":row.get("value",1)} for row in rows]
        if payer.pk not in eligible or any(row["member"] not in eligible for row in self.entries):
            raise serializers.ValidationError("The payer and split members must belong to this ledger.")
        self.allocation = allocate(get("paise"), get("split_type","EQUAL"), self.entries)
        return attrs


class SettlementSerializer(ModelSerializer):
    class Meta(ModelSerializer.Meta):
        model = m.Settlement
        read_only_fields = [*ModelSerializer.Meta.read_only_fields, "status"]
        extra_kwargs = {"paise":{"min_value":1}, "date":{"read_only":True}}
        validators = []

    def get_fields(self):
        fields = super().get_fields()
        flat = self.context["flat"]
        for name, qs in [
            ("cycle",flat.cycle_set.all()),("trip",flat.trip_set.filter(archived=False)),
            ("payer",flat.member_set.all()),("receiver",flat.member_set.all())
        ]:
            fields[name].queryset = qs
        return fields


class ChoreLogSerializer(ModelSerializer):
    class Meta(ModelSerializer.Meta):
        model = m.ChoreLog


class ChoreSerializer(ModelSerializer):
    logs = ChoreLogSerializer(many=True, read_only=True)

    class Meta(ModelSerializer.Meta):
        model = m.Chore
        read_only_fields = [*ModelSerializer.Meta.read_only_fields,"active"]

    def get_fields(self):
        fields = super().get_fields()
        fields["assigned"].queryset = self.context["flat"].member_set.filter(active=True,is_trip_guest=False)
        return fields


class MaintenanceSerializer(ModelSerializer):
    class Meta(ModelSerializer.Meta):
        model = m.Maintenance
        read_only_fields = [*ModelSerializer.Meta.read_only_fields,"reported_by","expense","resolved"]


class ReminderSerializer(ModelSerializer):
    class Meta(ModelSerializer.Meta):
        model = m.Reminder
        read_only_fields = [*ModelSerializer.Meta.read_only_fields,"recipient","kind","key"]

