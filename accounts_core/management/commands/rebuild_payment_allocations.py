"""Rebuild payment allocations oldest-due-first after import or data fixes."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from treasury.allocation import rebuild_client_ar_allocations, rebuild_supplier_ap_allocations


class Command(BaseCommand):
    help = "Rebuild AR/AP payment allocations using oldest due-date FIFO."

    def handle(self, *args, **options):
        ar_count = rebuild_client_ar_allocations()
        ap_count = rebuild_supplier_ap_allocations()
        self.stdout.write(self.style.SUCCESS(f"Rebuilt client payment allocations: {ar_count}"))
        self.stdout.write(self.style.SUCCESS(f"Rebuilt supplier payment allocations: {ap_count}"))
