from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("scheduled-payments/", views.scheduled_payment_list, name="scheduled_payment_list"),
    path("travellers/", views.travellers_list, name="travellers_list"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/<uuid:invoice_id>/edit/", views.invoice_edit, name="invoice_edit"),
    path("invoices/<uuid:invoice_id>/open/", views.invoice_open, name="invoice_open"),
    path("invoices/<uuid:invoice_id>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<uuid:invoice_id>/post/", views.post_invoice, name="post_invoice"),
    path("invoices/<uuid:invoice_id>/void/", views.void_invoice, name="void_invoice"),
    path("invoices/<uuid:invoice_id>/delete/", views.invoice_delete, name="invoice_delete"),
    path("invoices/<uuid:invoice_id>/adjust/", views.adjust_invoice, name="adjust_invoice"),
    path(
        "invoices/<uuid:invoice_id>/attachments/<uuid:attachment_id>/delete/",
        views.invoice_delete_attachment,
        name="invoice_delete_attachment",
    ),
    path(
        "scheduled-payments/<uuid:payment_id>/toggle/",
        views.scheduled_payment_toggle,
        name="scheduled_payment_toggle",
    ),
    path(
        "scheduled-payments/<uuid:payment_id>/note/",
        views.scheduled_payment_update_note,
        name="scheduled_payment_update_note",
    ),
]
