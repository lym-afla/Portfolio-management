"""Data migration: copy FX wide named-pair columns into long-format rows.

For each existing FX row, iterate the six named-pair columns (USDEUR, USDGBP,
CHFGBP, RUBUSD, PLNUSD, CNYUSD) and, for each non-null value, create a
long-format row (from_currency / to_currency / rate) on the same date. The
investors M2M linkage is copied from the source row.

Storage convention: column ``XXCUR`` stores "XX currency per 1 CUR"
(quote-per-base). The column name's first three chars are the ``from``
currency, the next three are the ``to`` currency — e.g. ``USDEUR`` with value
1.09 becomes ``from_currency="USD", to_currency="EUR", rate=1.09`` meaning
"1.09 USD per EUR". This matches the convention documented on the FX model.

The reverse migration is a no-op: this is a one-way data transformation.
"""

from django.db import migrations

# Column name -> (from_currency, to_currency). The first 3 chars of the column
# name are the from (quote) currency, the next 3 are the to (base) currency.
WIDE_COLUMNS = (
    ("USDEUR", "USD", "EUR"),
    ("USDGBP", "USD", "GBP"),
    ("CHFGBP", "CHF", "GBP"),
    ("RUBUSD", "RUB", "USD"),
    ("PLNUSD", "PLN", "USD"),
    ("CNYUSD", "CNY", "USD"),
)


def migrate_wide_to_long(apps, schema_editor):
    """Copy each non-null named-pair column into a long-format FX row."""
    FX = apps.get_model("common", "FX")
    for old_row in FX.objects.all():
        investor_ids = list(old_row.investors.values_list("id", flat=True))
        for column, from_cur, to_cur in WIDE_COLUMNS:
            value = getattr(old_row, column, None)
            if value is None:
                continue
            new_row, _ = FX.objects.get_or_create(
                date=old_row.date,
                from_currency=from_cur,
                to_currency=to_cur,
                defaults={"rate": value},
            )
            if investor_ids:
                new_row.investors.add(*investor_ids)


def reverse_migrate(apps, schema_editor):
    """No-op: this migration is a one-way data transformation.

    The long-format rows are derived from the wide columns; dropping them on
    rollback would lose any long-format rows created after this migration ran.
    Leave the wide columns untouched and let the operator restore from backup
    if a true rollback is required.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0090_fx_long_format_fields"),
    ]

    operations = [
        migrations.RunPython(migrate_wide_to_long, reverse_migrate),
    ]
