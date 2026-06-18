"""Merge duplicate service types (e.g. TICKET -> Ticket) and re-point invoice lines."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from catalog.models import ServiceFieldDefinition, ServiceInstance, ServiceType
from sales.models import SalesInvoiceLine


class Command(BaseCommand):
    help = "Re-point invoice lines (and related records) from one service type to another, then remove the old type."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="from_name", required=True, help='Source service type name (e.g. "TICKET")')
        parser.add_argument("--to", dest="to_name", required=True, help='Target service type name (e.g. "Ticket")')
        parser.add_argument(
            "--deactivate-old",
            action="store_true",
            help="Deactivate the old service type instead of deleting it (when nothing else references it).",
        )
        parser.add_argument(
            "--delete-old",
            action="store_true",
            help="Delete the old service type after merge (default when it has no field definitions left).",
        )

    def handle(self, *args, **options):
        from_name = options["from_name"].strip()
        to_name = options["to_name"].strip()
        if from_name == to_name:
            raise CommandError("Source and target names must differ.")

        try:
            old_st = ServiceType.objects.get(name=from_name)
        except ServiceType.DoesNotExist:
            raise CommandError(f'Service type "{from_name}" not found.')

        try:
            new_st = ServiceType.objects.get(name=to_name)
        except ServiceType.DoesNotExist:
            raise CommandError(f'Service type "{to_name}" not found.')

        line_qs = SalesInvoiceLine.objects.filter(service_type=old_st)
        instance_qs = ServiceInstance.objects.filter(service_type=old_st)
        line_count = line_qs.count()
        instance_count = instance_qs.count()

        with transaction.atomic():
            updated_lines = line_qs.update(service_type=new_st)
            updated_instances = instance_qs.update(service_type=new_st)

            old_st.refresh_from_db()
            remaining = (
                SalesInvoiceLine.objects.filter(service_type=old_st).count()
                + ServiceInstance.objects.filter(service_type=old_st).count()
            )
            if remaining:
                raise CommandError(f"Merge incomplete: {remaining} records still reference {from_name}.")

            field_defs = ServiceFieldDefinition.objects.filter(service_type=old_st).count()
            if options["delete_old"] and field_defs:
                self.stdout.write(
                    self.style.WARNING(
                        f"Old type has {field_defs} custom field definition(s); deleting the type will remove them."
                    )
                )
                ServiceFieldDefinition.objects.filter(service_type=old_st).delete()

            if options["deactivate_old"]:
                old_st.is_active = False
                old_st.save(update_fields=["is_active"])
                action = "deactivated"
            elif options["delete_old"] or field_defs == 0:
                old_st.delete()
                action = "deleted"
            else:
                old_st.is_active = False
                old_st.save(update_fields=["is_active"])
                action = "deactivated (still has field definitions; use --delete-old to remove)"

        self.stdout.write(
            self.style.SUCCESS(
                f'Merged "{from_name}" -> "{to_name}": '
                f"{updated_lines} invoice line(s), {updated_instances} service instance(s); old type {action}."
            )
        )

        dupes = (
            ServiceType.objects.values("name")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
        )
        if dupes.exists():
            self.stdout.write(self.style.WARNING("Note: duplicate service type names still exist in the database."))
