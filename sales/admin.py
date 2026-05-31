from django.contrib import admin

from sales.models import CreditNote, SalesInvoice, SalesInvoiceAttachment, SalesInvoiceLine


class SalesInvoiceAttachmentInline(admin.TabularInline):
    model = SalesInvoiceAttachment
    extra = 0


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 0
    autocomplete_fields = ("service_type", "supplier", "line_employee", "service_instance")
    fields = (
        "service_type",
        "supplier",
        "line_employee",
        "qty",
        "sell_price",
        "cost_price",
        "line_discount",
        "line_data",
        "notes",
        "service_instance",
    )


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_no",
        "issue_date",
        "status",
        "package_type",
        "client",
        "grand_total",
        "grand_total_usd",
        "currency",
    )
    search_fields = ("invoice_no", "client__name_en", "client__client_code")
    list_filter = ("status", "package_type", "currency", "issue_date")
    autocomplete_fields = ("client", "file", "sales_employee", "posted_by", "voided_by")
    date_hierarchy = "issue_date"
    inlines = [SalesInvoiceLineInline, SalesInvoiceAttachmentInline]

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.status != SalesInvoice.Status.DRAFT:
            for f in (
                "grand_total",
                "subtotal",
                "discount_total",
                "grand_total_usd",
                "subtotal_usd",
                "discount_total_usd",
                "exchange_rate_to_usd",
                "currency",
            ):
                if f not in ro:
                    ro.append(f)
        return ro


@admin.register(SalesInvoiceLine)
class SalesInvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("invoice", "service_type", "sell_price", "cost_price", "qty")
    search_fields = ("invoice__invoice_no", "notes")
    autocomplete_fields = ("invoice", "service_type", "supplier", "line_employee", "service_instance")
    list_filter = ("service_type",)


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("credit_note_no", "sales_invoice", "amount", "status")
    search_fields = ("credit_note_no", "sales_invoice__invoice_no")
    autocomplete_fields = ("sales_invoice",)
