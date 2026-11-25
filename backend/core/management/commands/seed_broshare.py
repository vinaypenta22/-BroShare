from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Cycle, Flat, Member


class Command(BaseCommand):
    help = "Initialize the development demo account and shared flat exactly once."

    @transaction.atomic
    def handle(self, *args, **options):
        if not (settings.DEBUG and settings.DEMO_ENABLED):
            raise CommandError("Demo seeding requires DEBUG=true and DEMO_ENABLED=true.")
        user, created = get_user_model().objects.get_or_create(username="Vinay")
        if not created:
            self.stdout.write("Vinay already exists. No data changed.")
            return
        user.first_name, user.last_name = "Vinay", "Penta"
        user.set_password("Test@123")
        user.save()
        flat = Flat.objects.create(name="The Flat",created_by=user)
        Member.objects.create(flat=flat,user=user,role="LEAD",name="Vinay Penta",upi="vinaypenta@oksbi")
        Member.objects.bulk_create([Member(flat=flat,name=name) for name in ("Tharun","Sai","Ashwin")])
        Cycle.objects.create(flat=flat,month=timezone.localdate().strftime("%Y-%m"))
        self.stdout.write(self.style.SUCCESS("Created the BroShare demo account."))
