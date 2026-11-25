from django.contrib import admin
from . import models as m

admin.site.register([m.Flat,m.Member,m.Cycle,m.Expense,m.ExpenseSplit,m.Trip,m.TripParticipant,
                     m.Settlement,m.Chore,m.ChoreLog,m.Maintenance,m.Reminder])
