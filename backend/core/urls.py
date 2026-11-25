from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import backup, views

router = DefaultRouter()
for prefix, view in [
    ("roommates", views.Members), ("billing-cycle", views.Cycles), ("expenses", views.Expenses),
    ("settlements", views.Settlements), ("trips", views.Trips), ("chores", views.Chores),
    ("maintenance", views.Maintenance), ("reminders", views.Reminders)
]:
    router.register(prefix,view,basename=prefix)

urlpatterns = [
    path("admin/",admin.site.urls),
    path("api/auth/register/",views.register),
    path("api/auth/login/",views.Login.as_view()),
    path("api/auth/refresh/",views.Refresh.as_view()),
    path("api/auth/logout/",views.logout),
    path("api/auth/me/",views.me),
    path("api/flats/",views.flats),
    path("api/workspace/",views.workspace),
    path("api/sync-check/",views.sync),
    path("api/summary/",views.summary),
    path("api/payment-qr/",views.payment_qr),
    path("api/reports/<str:kind>/",views.reports),
    path("api/export/",backup.export_data),
    path("api/import/",backup.import_data),
    path("api/",include(router.urls)),
]

