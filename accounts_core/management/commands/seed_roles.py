from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create Admin/Accounting/Sales role groups and baseline permissions."

    def handle(self, *args, **options):
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        accounting_group, _ = Group.objects.get_or_create(name="Accounting")
        sales_group, _ = Group.objects.get_or_create(name="Sales")

        all_perms = Permission.objects.all()
        admin_group.permissions.set(all_perms)

        accounting_codenames = [
            "view_salesinvoice",
            "change_salesinvoice",
            "view_supplierbill",
            "change_supplierbill",
            "view_payment",
            "add_payment",
            "change_payment",
            "view_arallocation",
            "add_arallocation",
            "view_apallocation",
            "add_apallocation",
        ]
        accounting_group.permissions.set(Permission.objects.filter(codename__in=accounting_codenames))

        sales_codenames = [
            "view_salesinvoice",
            "add_salesinvoice",
            "change_salesinvoice",
            "view_salesinvoiceline",
            "add_salesinvoiceline",
            "change_salesinvoiceline",
            "view_client",
        ]
        sales_group.permissions.set(Permission.objects.filter(codename__in=sales_codenames))

        self.stdout.write(self.style.SUCCESS("Role groups seeded successfully."))
