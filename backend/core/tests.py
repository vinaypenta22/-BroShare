from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APITestCase

from .models import Cycle, Expense, Flat, Member, Settlement
from .services import allocate, generate_recurring, next_due, simplify


class MoneyTests(SimpleTestCase):
    def test_rounding_and_validation(self):
        rows = [{"member":i,"value":Decimal(v)} for i,v in [(7,"1"),(2,"2"),(4,"1")]]
        self.assertEqual([v for v,_ in allocate(1001,"EQUAL",rows)],[333,334,334])
        self.assertEqual([v for v,_ in allocate(1001,"SHARES",rows)],[250,501,250])
        self.assertEqual([v for v,_ in allocate(400,"EXACT",rows)],[100,200,100])
        percent = [{"member":2,"value":Decimal("70")},{"member":7,"value":Decimal("30")}]
        self.assertEqual([v for v,_ in allocate(101,"PERCENT",percent)],[71,30])
        for mode in ("PERCENT","EXACT"):
            with self.assertRaises(ValidationError):
                allocate(999,mode,rows)

    def test_simplification_and_calendar(self):
        self.assertEqual(simplify({1:500,2:-200,3:-300}),[
            {"payer":3,"receiver":1,"paise":300},{"payer":2,"receiver":1,"paise":200}
        ])
        self.assertEqual(next_due(date(2028,1,31),"MONTHLY"),date(2028,2,29))
        self.assertEqual(next_due(date(2028,2,29),"MONTHLY",31),date(2028,3,31))


class WorkflowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("lead",password="strong-demo-password")
        self.client.force_authenticate(self.user)
        self.flat = Flat.objects.create(name="Test flat",created_by=self.user)
        self.lead = Member.objects.create(flat=self.flat,user=self.user,name="Lead",role="LEAD",upi="lead@bank")
        self.b = Member.objects.create(flat=self.flat,name="Flatmate")
        self.cycle = Cycle.objects.create(flat=self.flat,month="2027-01")

    def expense(self, **payload):
        return self.client.post("/api/expenses/",{
            "title":"Rent","paise":1001,"category":"Rent","date":"2027-01-01",
            "payer":self.lead.pk,"cycle":self.cycle.pk,"split_type":"EQUAL",
            "splits":[{"member":self.lead.pk},{"member":self.b.pk}],**payload
        },format="json")

    def test_register_login_join_sync_and_permissions(self):
        browser = APIClient()
        self.assertEqual(browser.get("/api/expenses/").status_code,401)
        credentials = {"username":"Second","password":"Not-A-Common-Pass-249"}
        self.assertEqual(browser.post("/api/auth/register/",credentials).status_code,201)
        tokens = browser.post("/api/auth/login/",credentials).data
        self.assertIn("access",tokens)
        browser.credentials(HTTP_AUTHORIZATION="Bearer "+tokens["access"])
        self.assertEqual(browser.get("/api/expenses/",HTTP_X_FLAT_ID=str(self.flat.pk)).status_code,403)
        self.assertEqual(browser.post("/api/flats/",{"name":"Second","invite":self.flat.invite}).status_code,201)
        before = browser.get("/api/sync-check/").data["updated_at"]
        result = self.expense()
        self.assertEqual(result.status_code,201,result.data)
        self.assertNotEqual(browser.get("/api/sync-check/").data["updated_at"],before)
        self.assertEqual(browser.get("/api/expenses/").data["results"][0]["paise"],1001)
        rotated = browser.post("/api/auth/refresh/",{"refresh":tokens["refresh"]}).data
        self.assertIn("access",rotated)
        self.assertEqual(browser.post("/api/auth/refresh/",{"refresh":tokens["refresh"]}).status_code,401)
        self.assertEqual(browser.post("/api/auth/logout/",{"refresh":rotated["refresh"]}).status_code,204)

    def test_rollover_pending_confirm_reverse_and_reopen(self):
        self.assertEqual(self.expense(frequency="MONTHLY").status_code,201)
        original = self.client.get("/api/summary/").data
        self.assertEqual(original["dividend"],501)
        self.assertEqual(original["transfers"],[{"payer":self.b.pk,"receiver":self.lead.pk,"paise":500}])
        for _ in range(2):
            result = self.client.post("/api/billing-cycle/settle-month/",{"cycle":self.cycle.pk,"rollover":True},format="json")
            self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(Expense.objects.count(),2)
        payment = Settlement.objects.get()
        self.assertEqual((payment.status,payment.date),("PENDING",date(2027,2,1)))
        url = f"/api/summary/?cycle={self.cycle.pk}"
        self.assertEqual(self.client.get(url).data["transfers"],original["transfers"])
        result = self.client.post(f"/api/settlements/{payment.pk}/confirm/",{"method":"CASH"})
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(self.client.get(url).data["transfers"],[])
        self.assertEqual(self.client.post(f"/api/settlements/{payment.pk}/reverse/").status_code,200)
        self.assertEqual(self.client.get(url).data["transfers"],original["transfers"])
        self.assertEqual(self.expense().status_code,400)
        self.assertEqual(self.client.post("/api/billing-cycle/reopen/",{"cycle":self.cycle.pk}).status_code,200)
        self.assertEqual(self.expense().status_code,201)
        self.assertEqual(Settlement.objects.get().status,"REVERSED")

    def test_trip_isolation_upi_and_archival(self):
        trip = self.client.post("/api/trips/",{"name":"Goa","destination":"Goa","start":"2027-01-01","end":"2027-01-02",
            "participants":[self.lead.pk],"budget":100000},format="json")
        self.assertEqual(trip.status_code,201,trip.data)
        guest = self.client.post("/api/roommates/guest/",{"name":"Guest","trip":trip.data["id"]})
        self.assertEqual(guest.status_code,201,guest.data)
        result = self.expense(cycle=None,trip=trip.data["id"],splits=[{"member":guest.data["id"]}])
        self.assertEqual(result.status_code,201,result.data)
        self.assertEqual(self.client.get("/api/summary/").data["total"],0)
        self.assertEqual(self.client.get(f"/api/summary/?trip={trip.data['id']}").data["total"],1001)
        self.assertEqual(self.expense(splits=[{"member":guest.data["id"]}]).status_code,400)
        self.assertEqual(self.expense().status_code,201)
        self.assertEqual(self.client.delete(f"/api/roommates/{self.b.pk}/").status_code,204)
        self.assertFalse(self.flat.member_set.get(pk=self.b.pk).active)
        self.assertEqual(self.client.get("/api/summary/").data["transfers"][0]["payer"],self.b.pk)
        qr = self.client.post("/api/payment-qr/",{"receiver":self.lead.pk,"paise":501})
        self.assertEqual(qr.status_code,200,qr.data)
        self.assertIn("am=5.01",qr.data["link"])
        self.assertGreater(qr.data["size"],20)
        self.assertTrue(qr.data["path"].startswith("M"))

    def test_chores_maintenance_reminders_reports_backup(self):
        chore = self.client.post("/api/chores/",{"title":"Kitchen","due":"2027-01-01","assigned":self.lead.pk,"frequency":"WEEKLY","points":3})
        self.assertEqual(chore.status_code,201,chore.data)
        url=f"/api/chores/{chore.data['id']}/complete/"
        done=self.client.post(url,{"due":"2027-01-01"})
        self.assertEqual(done.status_code,200,done.data)
        self.assertEqual(done.data["assigned"],self.b.pk)
        self.assertEqual(done.data["logs"][0]["points"],3)
        self.assertEqual(self.client.post(url,{"due":"2027-01-01"}).status_code,400)
        issue = self.client.post("/api/maintenance/",{"title":"Leak","priority":"HIGH","estimated":1500,"status":"SCHEDULED"})
        self.assertEqual(issue.status_code,201,issue.data)
        path = f"/api/maintenance/{issue.data['id']}/convert-to-expense/"
        self.assertEqual(self.client.post(path,{"payer":self.lead.pk}).status_code,201)
        self.assertEqual(self.client.post(path,{"payer":self.lead.pk}).status_code,200)
        call_command("tick_broshare")
        self.assertTrue(any(r["kind"]=="MAINTENANCE" for r in self.client.get("/api/reminders/").data["results"]))
        self.assertEqual(self.client.get("/api/reports/categories/").data,[{"name":"Maintenance","total":1500}])
        exported = self.client.get("/api/export/").json()
        failed=self.client.post("/api/import/",{"confirmed":False,"backup":exported},format="json")
        self.assertEqual(failed.status_code,400,failed.data)
        imported=self.client.post("/api/import/",{"confirmed":True,"backup":exported},format="json")
        self.assertEqual(imported.status_code,201,imported.data)
        self.assertEqual(self.client.get("/api/summary/",HTTP_X_FLAT_ID=str(imported.data["id"])).data["total"],1500)
        exported["tables"]["expensesplit"][0]["paise"] += 1
        self.assertEqual(self.client.post("/api/import/",{"confirmed":True,"backup":exported},format="json").status_code,400)
        self.assertEqual(Flat.objects.count(),2)

    def test_multiple_recurrences_are_idempotent(self):
        self.assertEqual(self.expense(frequency="BIWEEKLY").status_code,201)
        through=date(2027,2,1)
        generate_recurring(self.flat,through)
        generate_recurring(self.flat,through)
        self.assertEqual(list(Expense.objects.filter(source__isnull=False).order_by("date").values_list("date",flat=True)),
                         [date(2027,1,15),date(2027,1,29)])

    @override_settings(DEMO_ENABLED=True,DEBUG=True)
    def test_demo_seed_leaves_archived_roster_intact(self):
        call_command("seed_broshare")
        demo = Flat.objects.get(created_by__username="Vinay")
        demo.member_set.filter(name="Sai").update(active=False)
        call_command("seed_broshare")
        self.assertEqual(demo.member_set.count(),4)
        self.assertFalse(demo.member_set.get(name="Sai").active)


class ConcurrentTests(TransactionTestCase):
    def test_same_payment_request_twice(self):
        user=get_user_model().objects.create_user("owner",password="strong-pass-string")
        flat=Flat.objects.create(name="Race test",created_by=user)
        lead=Member.objects.create(flat=flat,user=user,name="Owner",role="LEAD")
        member=Member.objects.create(flat=flat,name="Other")
        cycle=Cycle.objects.create(flat=flat,month=timezone.localdate().strftime("%Y-%m"))
        api=APIClient()
        api.force_authenticate(user)
        response=api.post("/api/expenses/",{"title":"Test","category":"Rent","paise":1000,"payer":lead.pk,"cycle":cycle.pk,
            "date":timezone.localdate().isoformat(),"splits":[{"member":member.pk}]},format="json")
        self.assertEqual(response.status_code,201,response.data)
        payload={"request_key":str(uuid4()),"payer":member.pk,"receiver":lead.pk,"cycle":cycle.pk,"paise":1000}
        def pay(_):
            try:
                client=APIClient()
                client.force_authenticate(user)
                return client.post("/api/settlements/",payload,format="json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=sorted(pool.map(pay,range(2)))
        self.assertEqual(statuses,[200,201])
        self.assertEqual(Settlement.objects.count(),1)

