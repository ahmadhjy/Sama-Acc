from django.contrib import admin

from treasury.models import APAllocation, ARAllocation, AccountTransfer, MoneyAccount, Payment, ReconciliationRecord


@admin.register(MoneyAccount)
class MoneyAccountAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name", "type", "currency", "is_active")
    list_filter = ("type", "currency", "is_active")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_no", "date", "direction", "party_type", "amount", "currency", "status")
    search_fields = ("receipt_no", "reference", "client__name_en", "supplier__name")
    list_filter = ("status", "direction", "party_type", "currency", "date")
    autocomplete_fields = ("client", "supplier", "money_account", "attachment", "posted_by")
    date_hierarchy = "date"


@admin.register(ARAllocation)
class ARAllocationAdmin(admin.ModelAdmin):
    autocomplete_fields = ("payment", "sales_invoice")
    search_fields = ("payment__receipt_no", "sales_invoice__invoice_no")


@admin.register(APAllocation)
class APAllocationAdmin(admin.ModelAdmin):
    autocomplete_fields = ("payment", "supplier_bill")
    search_fields = ("payment__receipt_no", "supplier_bill__bill_no")


@admin.register(AccountTransfer)
class AccountTransferAdmin(admin.ModelAdmin):
    autocomplete_fields = ("from_account", "to_account")
    search_fields = ("reference", "from_account__name", "to_account__name")
    date_hierarchy = "date"


@admin.register(ReconciliationRecord)
class ReconciliationRecordAdmin(admin.ModelAdmin):
    autocomplete_fields = ("money_account",)
    search_fields = ("reason", "money_account__name")
    date_hierarchy = "reconciliation_date"
