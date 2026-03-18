from django.apps import AppConfig


class CommunicationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core.communication'
    label = 'core_communication'

    def ready(self):
        from . import signals  # noqa: F401
