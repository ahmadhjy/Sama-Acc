from django.apps import AppConfig


class AccountsCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts_core"
    verbose_name = "Accounts core"

    def ready(self):
        from django.db.models.signals import post_save
        from django.conf import settings
        from django.dispatch import receiver

        from accounts_core.models import UserProfile

        @receiver(post_save, sender=settings.AUTH_USER_MODEL)
        def ensure_user_profile(sender, instance, created, **kwargs):
            if created:
                UserProfile.objects.get_or_create(user=instance)
