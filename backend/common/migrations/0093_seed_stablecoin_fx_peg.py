"""Seed the stablecoin FX peg (1.0 USD↔USDT, 1.0 USD↔USDC).

These rates are universal constants (stablecoins peg to USD at 1.0), so they
are seeded as global FX rows (no investor link). The get_rate resolution
treats them as universal edges in the currency graph and exempts them from
the per-investor filter in the per-hop rate lookup.
"""
import logging
from datetime import date
from decimal import Decimal

from django.db import migrations

logger = logging.getLogger(__name__)

# The peg date is set well before the earliest transaction (2008) so the
# closest-date-on-or-before lookup (date__lte) always finds it.
PEG_DATE = date(2000, 1, 1)
PEG_RATE = Decimal("1.0000000000")

STABLECOIN_PEGS = [
    ("USD", "USDT"),
    ("USD", "USDC"),
]


def seed_peg(apps, schema_editor):
    FX = apps.get_model("common", "FX")
    for from_curr, to_curr in STABLECOIN_PEGS:
        FX.objects.get_or_create(
            date=PEG_DATE,
            from_currency=from_curr,
            to_currency=to_curr,
            defaults={"rate": PEG_RATE},
        )


def remove_peg(apps, schema_editor):
    FX = apps.get_model("common", "FX")
    for from_curr, to_curr in STABLECOIN_PEGS:
        FX.objects.filter(
            date=PEG_DATE,
            from_currency=from_curr,
            to_currency=to_curr,
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0092_fx_drop_wide_columns"),
    ]
    operations = [
        migrations.RunPython(seed_peg, remove_peg),
    ]
