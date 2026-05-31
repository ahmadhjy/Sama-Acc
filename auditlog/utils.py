from auditlog.models import AuditEvent, DocumentEventLog


def log_document_event(event_type, instance, actor=None, metadata=None):
    DocumentEventLog.objects.create(
        event_type=event_type,
        model=instance.__class__.__name__,
        object_id=str(instance.pk),
        actor=actor,
        metadata=metadata or {},
    )


def log_audit(action, instance, actor=None, reason="", before=None, after=None):
    AuditEvent.objects.create(
        who=actor,
        action=action,
        model=instance.__class__.__name__,
        object_id=str(instance.pk),
        reason=reason,
        before_json=before or {},
        after_json=after or {},
    )
