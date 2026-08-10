"""Django app configuration for transactions."""

from django.apps import AppConfig


class TransactionsConfig(AppConfig):
    """Django configuration for the transactions app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "transactions"
