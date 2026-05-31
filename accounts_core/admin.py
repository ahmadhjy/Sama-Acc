from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts_core.models import (
    Attachment,
    BookingFile,
    Client,
    CompanyBranding,
    Currency,
    DocumentSequence,
    Employee,
    ExchangeRate,
    Passenger,
    Supplier,
    UserProfile,
)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"
    verbose_name_plural = "Profile (main accountant)"


User = get_user_model()

if admin.site.is_registered(User):
    admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = list(getattr(BaseUserAdmin, "inlines", ()) or ()) + [UserProfileInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_main_accountant")
    list_filter = ("is_main_accountant",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)


@admin.register(CompanyBranding)
class CompanyBrandingAdmin(admin.ModelAdmin):
    list_display = ("display_name", "email", "default_currency")
    fieldsets = (
        (
            "Company (PDF header)",
            {
                "fields": (
                    "name",
                    "logo",
                    "address",
                    "phone",
                    "email",
                    "financial_account_number",
                    "default_currency",
                )
            },
        ),
        ("PDF footer", {"fields": ("footer_text",)}),
    )

    def has_add_permission(self, request):
        return not CompanyBranding.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    search_fields = ("name_en", "name_ar", "client_code", "email")
    list_display = ("client_code", "name_en", "type", "date_of_birth", "outstanding_receivable_display")
    list_filter = ("type",)
    fieldsets = (
        (None, {"fields": ("client_code", "type", "name_en", "name_ar", "date_of_birth")}),
        ("Contact", {"fields": ("whatsapp", "email", "address", "phones")}),
        ("Travel", {"fields": ("main_passport", "notes")}),
    )

    def outstanding_receivable_display(self, obj):
        return obj.outstanding_receivable

    outstanding_receivable_display.short_description = "Outstanding A/R"


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    search_fields = ("name", "supplier_code", "email")
    list_display = ("supplier_code", "name", "type")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    search_fields = ("name", "user__username")
    list_display = ("name", "role", "is_active")
    autocomplete_fields = ("user",)


@admin.register(BookingFile)
class BookingFileAdmin(admin.ModelAdmin):
    search_fields = ("file_no", "client__name_en", "client__client_code")
    list_display = ("file_no", "client", "status")
    autocomplete_fields = ("client",)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    search_fields = ("category",)
    list_display = ("category", "uploaded_by", "created_at")
    autocomplete_fields = ("uploaded_by",)


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    search_fields = ("full_name_en", "passport_number", "client__name_en")
    autocomplete_fields = ("client", "passport_attachment")


admin.site.register(DocumentSequence)
admin.site.register(ExchangeRate)


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")
