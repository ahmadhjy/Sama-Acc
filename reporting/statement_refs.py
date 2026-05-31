from django.urls import reverse


def invoice_ref_url(invoice_id):
    return reverse("sales:invoice_open", kwargs={"invoice_id": invoice_id})


def payment_ref_url(payment_id):
    return reverse("treasury:payment_receipt", kwargs={"payment_id": payment_id})


def bill_ref_url(bill_id):
    return reverse("purchases:bill_open", kwargs={"bill_id": bill_id})
