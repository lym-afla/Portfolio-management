"""Django app configuration for common."""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Django configuration for the common app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "common"

    def ready(self):
        """Connect signal handlers once the app registry is ready.

        Imports ``common.signals`` lazily here (rather than at module top level)
        to avoid importing ``services.fx`` — and therefore ``common.models`` —
        during the model-loading phase.
        """
        from .signals import register_signals

        register_signals()
