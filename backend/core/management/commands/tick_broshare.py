import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.utils import timezone

from core.models import Flat
from core.services import generate_recurring, generate_reminders
from core.views import touch


class Command(BaseCommand):
    help = "Generate due expenses and reminders. Use --watch for a continuous worker."

    def add_arguments(self, parser):
        parser.add_argument("--watch",action="store_true")

    def handle(self,*args,**options):
        while True:
            today = timezone.localdate()
            for pk in Flat.objects.values_list("pk",flat=True).iterator():
                with transaction.atomic():
                    flat = Flat.objects.select_for_update().get(pk=pk)
                    before = (flat.expense_set.count(),flat.reminder_set.count(),flat.cycle_set.count())
                    generate_recurring(flat,today)
                    generate_reminders(flat,today)
                    after = (flat.expense_set.count(),flat.reminder_set.count(),flat.cycle_set.count())
                    if before != after:
                        touch(flat)
            if not options["watch"]:
                return
            time.sleep(60)
            close_old_connections()

