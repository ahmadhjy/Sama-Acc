from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("bills/", views.bill_list, name="bill_list"),
    path("bills/new/", views.bill_create, name="bill_create"),
    path("bills/<uuid:bill_id>/open/", views.bill_open, name="bill_open"),
    path("bills/<uuid:bill_id>/edit/", views.bill_edit, name="bill_edit"),
    path("bills/<uuid:bill_id>/post/", views.post_bill, name="post_bill"),
    path("bills/<uuid:bill_id>/void/", views.void_bill, name="void_bill"),
]
