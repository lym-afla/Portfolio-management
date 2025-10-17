# Generated manually to convert existing date data to datetime format
from django.db import migrations


def convert_dates_to_datetime(apps, schema_editor):
    """
    Convert existing date values to datetime format in SQLite.
    SQLite stores dates as strings, so we need to update the format from 'YYYY-MM-DD' to 'YYYY-MM-DD HH:MM:SS'.
    """
    db_alias = schema_editor.connection.alias

    # Only run for SQLite databases
    if schema_editor.connection.vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            # Update Transactions table
            cursor.execute(
                """
                UPDATE common_transactions
                SET date = date || ' 00:00:00'
                WHERE length(date) = 10
            """
            )

            # Update FXTransaction table
            cursor.execute(
                """
                UPDATE common_fxtransaction
                SET date = date || ' 00:00:00'
                WHERE length(date) = 10
            """
            )


def reverse_datetime_to_dates(apps, schema_editor):
    """
    Reverse migration: convert datetime back to date format.
    """
    db_alias = schema_editor.connection.alias

    # Only run for SQLite databases
    if schema_editor.connection.vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            # Update Transactions table
            cursor.execute(
                """
                UPDATE common_transactions
                SET date = substr(date, 1, 10)
                WHERE length(date) > 10
            """
            )

            # Update FXTransaction table
            cursor.execute(
                """
                UPDATE common_fxtransaction
                SET date = substr(date, 1, 10)
                WHERE length(date) > 10
            """
            )


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0079_convert_transaction_date_to_datetime"),
    ]

    operations = [
        migrations.RunPython(convert_dates_to_datetime, reverse_datetime_to_dates),
    ]
