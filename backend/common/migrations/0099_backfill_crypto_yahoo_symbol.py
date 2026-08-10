"""Backfill yahoo_symbol on existing Crypto Assets rows.

Task 8 (crypto-as-currency): the price fetcher ``fetch_crypto_usd_price_from_yahoo``
now reads each coin's ``yahoo_symbol`` from its ``Assets`` row instead of a
hardcoded ``{"BTC": "BTC-USD"}`` dict. New coins get ``yahoo_symbol`` set on
creation by ``resolve_crypto_asset``; this migration backfills pre-existing
Crypto rows that lack one, using the ``<NAME>-USD`` convention (which is what
Yahoo Finance uses for crypto USD pairs, e.g. ``BTC-USD``, ``ETH-USD``).

Stablecoin rows (e.g. USDC) are also backfilled for uniformity — the value is
harmless because stablecoins are treated as cash (1:1 USD peg) and never enter
the crypto pricing path.

This is a DATA-only migration (no schema change).
"""
from django.db import migrations


def backfill_crypto_yahoo_symbol(apps, schema_editor):
    Assets = apps.get_model("common", "Assets")
    for asset in Assets.objects.filter(type="Crypto", yahoo_symbol__isnull=True):
        asset.yahoo_symbol = f"{asset.name}-USD"
        asset.save(update_fields=["yahoo_symbol"])


def reverse_backfill(apps, schema_editor):
    # No-op reverse: we cannot reliably restore the original NULL state, since
    # rows created after this migration legitimately carry a non-null value.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0098_brokers_cash_precision"),
    ]
    operations = [
        migrations.RunPython(backfill_crypto_yahoo_symbol, reverse_backfill),
    ]
