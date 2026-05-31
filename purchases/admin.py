from django.contrib import admin

from purchases.models import ExpenseCategory, SupplierBill, SupplierBillLine


class SupplierBillLineInline(admin.TabularInline):
    model = SupplierBillLine
    extra = 0
    autocomplete_fields = ("sales_invoice_line", "service_instance", "file", "expense_category")


@admin.register(SupplierBill)
class SupplierBillAdmin(admin.ModelAdmin):
    list_display = ("bill_no", "bill_date", "status", "supplier", "grand_total", "currency")
    search_fields = ("bill_no", "supplier__name", "supplier__supplier_code")
    list_filter = ("status", "currency", "bill_date")
    autocomplete_fields = ("supplier", "posted_by")
    date_hierarchy = "bill_date"
    inlines = [SupplierBillLineInline]


@admin.register(SupplierBillLine)
class SupplierBillLineAdmin(admin.ModelAdmin):
    list_display = ("bill", "line_kind", "description", "cost_amount")
    search_fields = ("description", "bill__bill_no", "notes")
    autocomplete_fields = ("bill", "sales_invoice_line", "service_instance", "file", "expense_category")
    list_filter = ("line_kind",)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    search_fields = ("code", "name")
    list_display = ("code", "name", "is_active")
