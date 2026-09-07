"""Data migration: delete null/empty currency-pair FX shell rows.

The wide->long FX refactor (0091) created one long-format row per non-null
named pair column, but left behind the original wide rows as empty "shells"
(``from_currency``/``to_currency``/``rate`` all NULL, or blank). These carry
no rate data and surface on the /database/fx grid as a spurious ``null/null``
column and phantom empty date rows. They also break date-level pagination,
since a date's only record may be a null shell.

This migration deletes every FX row whose ``from_currency`` or ``to_currency``
is NULL or blank. Real pair rows are untouched.

The reverse migration is a no-op: the deleted rows contained no data, so there
is nothing to restore (a true rollback would require a DB backup).
"""

from django.db import migrations
from django.db.models import Q


def delete_null_pair_shells(apps, schema_editor):
    """Delete FX rows with NULL/blank from_currency or to_currency."""
    FX = apps.get_model("common", "FX")
    FX.objects.filter(
        Q(from_currency__isnull=True)
        | Q(to_currency__isnull=True)
        | Q(from_currency="")
        | Q(to_currency="")
    ).delete()


def reverse_migration(apps, schema_editor):
    """No-op: deleted rows held no data; restore from a DB backup if needed."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0099_backfill_crypto_yahoo_symbol"),
    ]

    operations = [
        migrations.RunPython(delete_null_pair_shells, reverse_migration),
    ]
