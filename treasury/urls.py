from django.urls import path

from . import views

app_name = "treasury"

urlpatterns = [
    path("accounts/", views.money_accounts_list, name="money_accounts_list"),
    path("accounts/new/", views.money_account_create, name="money_account_create"),
    path("accounts/<uuid:account_id>/", views.money_account_detail, name="money_account_detail"),
    path("accounts/<uuid:account_id>/edit/", views.money_account_edit, name="money_account_edit"),
    path("accounts/<uuid:account_id>/deactivate/", views.money_account_deactivate, name="money_account_deactivate"),
    path("accounts/<uuid:account_id>/delete/", views.money_account_delete, name="money_account_delete"),
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/new/", views.payment_create, name="payment_create"),
    path("payments/<uuid:payment_id>/edit/", views.payment_edit, name="payment_edit"),
    path("payments/<uuid:payment_id>/receipt/", views.payment_receipt, name="payment_receipt"),
    path("payments/<uuid:payment_id>/post/", views.post_payment, name="post_payment"),
    path("payments/<uuid:payment_id>/void/", views.void_payment, name="void_payment"),
    path("payments/<uuid:payment_id>/delete/", views.payment_delete, name="payment_delete"),
    path("allocations/ar/new/", views.ar_allocation_create, name="ar_allocation_create"),
    path("allocations/ap/new/", views.ap_allocation_create, name="ap_allocation_create"),
    path("reconcile/", views.reconcile_account, name="reconcile_account"),
    path("transfers/new/", views.transfer_create, name="transfer_create"),
]
