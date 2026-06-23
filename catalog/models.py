import uuid

from django.db import models


class Destination(models.Model):
    """Searchable tourism destinations for invoice service lines."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    country = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ServiceType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    requires_supplier = models.BooleanField(default=False)
    default_currency = models.CharField(max_length=3, default="USD")

    def __str__(self):
        return self.name


class ServiceFieldDefinition(models.Model):
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        CHOICE = "choice", "Choice"
        BOOL = "bool", "Boolean"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_type = models.ForeignKey(ServiceType, on_delete=models.CASCADE, related_name="field_definitions")
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=120)
    field_type = models.CharField(
        max_length=20,
        choices=FieldType.choices,
        default=FieldType.TEXT,
    )
    required = models.BooleanField(default=False)
    choices = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("service_type", "key")
        ordering = ["order", "key"]

    def __str__(self):
        return f"{self.service_type.code}.{self.key}"


class ServiceInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_type = models.ForeignKey(ServiceType, on_delete=models.PROTECT, related_name="instances")
    data = models.JSONField(default=dict, blank=True)
    passenger = models.ForeignKey("accounts_core.Passenger", null=True, blank=True, on_delete=models.SET_NULL)
    supplier = models.ForeignKey("accounts_core.Supplier", null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service_type.code} - {self.id}"
