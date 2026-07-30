"""Migrate existing CRYPTO:USDT / CRYPTO:USDC data to the cash model.

Phase 5 of stablecoins-as-currency. Before this migration, stablecoin
deposits/withdrawals/rewards were stored as crypto-asset transactions
(``Crypto transfer in/out``, ``Crypto reward``) against a ``CRYPTO:USDT``
or ``CRYPTO:USDC`` asset with ``currency="USD"``. After Phase 4, new
imports create cash-type transactions (``Cash in/out``, ``Interest income``)
with ``currency="USDT"``, ``security=None``, ``cash_flow=qty``.

This one-time migration converts the existing historical data to match.

Transaction type mapping:
  Crypto transfer in  → Cash in          (deposit of stablecoin)
  Crypto transfer out → Cash out         (withdrawal of stablecoin)
  Crypto reward       → Interest income  (earn reward of stablecoin)

Field changes per transaction:
  - type: mapped per above
  - currency: "USD" → the stablecoin code ("USDT" or "USDC")
  - security: the CRYPTO:USDT/USDC asset → None
  - cash_flow: None → the transaction's quantity (signed)
  - quantity: unchanged → None (cash transactions use cash_flow, not quantity)
  - price: 1.0 → None (cash has no entry price)

After re-typing all transactions, the now-orphaned CRYPTO:USDT/USDC asset
rows are deleted (no remaining transactions reference them).
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

STABLECOIN_ISINS = ["CRYPTO:USDT", "CRYPTO:USDC"]

TYPE_MAP = {
    "Crypto transfer in": "Cash in",
    "Crypto transfer out": "Cash out",
    "Crypto reward": "Interest income",
}


def migrate_stablecoins_to_cash(apps, schema_editor):
    Assets = apps.get_model("common", "Assets")
    Transactions = apps.get_model("common", "Transactions")

    for isin in STABLECOIN_ISINS:
        try:
            asset = Assets.objects.get(ISIN=isin)
        except Assets.DoesNotExist:
            continue

        # Derive the stablecoin currency code from the ISIN suffix.
        stablecoin_code = isin.split(":")[-1]  # "USDT" or "USDC"

        txs = Transactions.objects.filter(security=asset)
        migrated = 0
        for tx in txs:
            new_type = TYPE_MAP.get(tx.type)
            if new_type is None:
                logger.warning(
                    "Stablecoin tx id=%s has unmappable type '%s'; skipping.",
                    tx.id, tx.type,
                )
                continue
            tx.type = new_type
            tx.currency = stablecoin_code
            tx.security = None
            # cash_flow takes the quantity (signed: deposits/rewards positive,
            # withdrawals negative — the quantity sign is already correct from
            # the normalizer).
            tx.cash_flow = tx.quantity
            tx.quantity = None
            tx.price = None
            tx.save()
            migrated += 1

        logger.info(
            "Migrated %d transactions from %s to cash (%s).",
            migrated, isin, stablecoin_code,
        )

        # Delete the orphaned asset if no transactions remain.
        remaining = Transactions.objects.filter(security=asset).count()
        if remaining == 0:
            asset.delete()
            logger.info("Deleted orphaned asset %s.", isin)
        else:
            logger.warning(
                "Asset %s still has %d transactions; not deleting.",
                isin, remaining,
            )


def reverse_migration(apps, schema_editor):
    """One-way migration — no automatic reverse.

    Reverting would require re-creating the CRYPTO:USDT/USDC assets and
    re-typing the transactions back. If needed, restore from a DB backup.
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0094_stablecoin_currency_choices"),
    ]
    operations = [
        migrations.RunPython(migrate_stablecoins_to_cash, reverse_migration),
    ]
