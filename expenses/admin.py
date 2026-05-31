from django.contrib import admin

from expenses.models import OperatingExpense, OperatingExpenseAttachment


class OperatingExpenseAttachmentInline(admin.TabularInline):
    model = OperatingExpenseAttachment
    extra = 0


@admin.register(OperatingExpense)
class OperatingExpenseAdmin(admin.ModelAdmin):
    list_display = ("expense_no", "category", "expense_date", "amount", "amount_usd", "currency", "status")
    list_filter = ("status", "category", "currency")
    inlines = [OperatingExpenseAttachmentInline]
