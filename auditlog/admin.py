from django.contrib import admin
from auditlog.models import AuditEvent, DocumentEventLog

admin.site.register(AuditEvent)
admin.site.register(DocumentEventLog)
