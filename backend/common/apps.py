"""Django app configuration for common."""


from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Django configuration for the common app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "common"
