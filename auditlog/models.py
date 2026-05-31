import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    who = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    when = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)


class DocumentEventLog(models.Model):
    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED_DRAFT = "UPDATED_DRAFT", "Updated Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"
        ALLOCATED = "ALLOCATED", "Allocated"
        DEALLOCATED = "DEALLOCATED", "Deallocated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)
