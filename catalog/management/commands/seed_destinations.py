from django.core.management.base import BaseCommand

from catalog.models import Destination

DEFAULT_DESTINATIONS = [
    ("Dubai", "UAE", 1),
    ("Abu Dhabi", "UAE", 2),
    ("Istanbul", "Turkey", 3),
    ("Paris", "France", 4),
    ("London", "United Kingdom", 5),
    ("Riyadh", "Saudi Arabia", 6),
    ("Jeddah", "Saudi Arabia", 7),
    ("Beirut", "Lebanon", 8),
    ("Cairo", "Egypt", 9),
    ("Amman", "Jordan", 10),
    ("Doha", "Qatar", 11),
    ("Kuwait City", "Kuwait", 12),
    ("Manama", "Bahrain", 13),
    ("Muscat", "Oman", 14),
    ("Rome", "Italy", 15),
    ("Barcelona", "Spain", 16),
    ("Athens", "Greece", 17),
    ("Bangkok", "Thailand", 18),
    ("Singapore", "Singapore", 19),
    ("New York", "United States", 20),
    ("United Arab Emirates", "UAE", 100),
    ("Saudi Arabia", "Saudi Arabia", 101),
    ("Turkey", "Turkey", 102),
    ("France", "France", 103),
    ("United Kingdom", "United Kingdom", 104),
    ("Lebanon", "Lebanon", 105),
    ("Egypt", "Egypt", 106),
]


class Command(BaseCommand):
    help = "Seed searchable destinations for invoice service lines."

    def handle(self, *args, **options):
        created = 0
        for name, country, order in DEFAULT_DESTINATIONS:
            _, was_created = Destination.objects.get_or_create(
                name=name,
                defaults={"country": country, "sort_order": order, "is_active": True},
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Destinations ready ({created} new)."))
