"""Django app configuration for database."""

from django.apps import AppConfig


class DatabaseConfig(AppConfig):
    """Django configuration for the database app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "database"
