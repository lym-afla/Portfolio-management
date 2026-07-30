"""Test the stablecoin-to-cash data migration (0095).

Verifies that existing CRYPTO:USDT transactions (Crypto transfer in/out,
Crypto reward) are correctly converted to cash-type transactions
(Cash in/out, Interest income) with the stablecoin currency, no security,
and cash_flow set. The orphaned CRYPTO:USDT asset is deleted.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path
import importlib.util

import pytest

from common.models import Accounts, Assets, Brokers, Transactions


def _load_migration_module():
    """Import the 0095 migration module by file path.

    The module name starts with digits, so a normal ``import`` statement is
    not valid Python; load it via importlib using the file location.
    """
    migration_path = (
        Path(Assets._meta.app_config.path)
        / "migrations"
        / "0095_migrate_stablecoins_to_cash.py"
    )
    spec = importlib.util.spec_from_file_location(
        "stablecoin_migration_0095", migration_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.django_db
class TestStablecoinCashMigration:
    """Test the migrate_stablecoins_to_cash data migration."""

    def _build_pre_migration_state(self, user):
        """Create a CRYPTO:USDT asset with crypto-type transactions."""
        broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
        account = Accounts.objects.create(broker=broker, name="Main")
        asset = Assets.objects.create(
            ISIN="CRYPTO:USDT",
            currency="USD",
            type="Crypto",
            name="USDT",
            ticker="USDT",
            exposure="FX",
        )
        asset.investors.add(user)

        # Deposit (Crypto transfer in)
        deposit = Transactions.objects.create(
            investor=user, account=account, security=asset,
            currency="USD", type="Crypto transfer in",
            date=date(2025, 3, 23),
            quantity=Decimal("29994.781592"),
            price=Decimal("1"),
            import_provider="okx", import_account_id="18",
            import_event_id="deposit:410907740:0",
        )
        # Reward (Crypto reward)
        reward = Transactions.objects.create(
            investor=user, account=account, security=asset,
            currency="USD", type="Crypto reward",
            date=date(2026, 7, 26),
            quantity=Decimal("1.002477"),
            price=Decimal("1"),
            import_provider="okx", import_account_id="18",
            import_event_id="earn:1785088949000:0",
        )
        return asset, deposit, reward, account

    def test_migration_converts_deposit_to_cash_in(self, user):
        """Crypto transfer in on CRYPTO:USDT → Cash in, currency=USDT, no security."""
        mod = _load_migration_module()
        from django.apps import apps as django_apps

        asset, deposit, reward, account = self._build_pre_migration_state(user)

        mod.migrate_stablecoins_to_cash(django_apps, None)

        deposit.refresh_from_db()
        assert deposit.type == "Cash in"
        assert deposit.currency == "USDT"
        assert deposit.security is None
        assert deposit.cash_flow == Decimal("29994.78")
        assert deposit.quantity is None
        assert deposit.price is None
        # Idempotency fields preserved
        assert deposit.import_event_id == "deposit:410907740:0"

    def test_migration_converts_reward_to_interest_income(self, user):
        """Crypto reward on CRYPTO:USDT → Interest income, currency=USDT."""
        mod = _load_migration_module()
        from django.apps import apps as django_apps

        asset, deposit, reward, account = self._build_pre_migration_state(user)

        mod.migrate_stablecoins_to_cash(django_apps, None)

        reward.refresh_from_db()
        assert reward.type == "Interest income"
        assert reward.currency == "USDT"
        assert reward.security is None
        assert reward.cash_flow == Decimal("1.00")

    def test_migration_deletes_orphaned_asset(self, user):
        """CRYPTO:USDT asset is deleted after all its transactions are migrated."""
        mod = _load_migration_module()
        from django.apps import apps as django_apps

        asset, deposit, reward, account = self._build_pre_migration_state(user)

        mod.migrate_stablecoins_to_cash(django_apps, None)

        assert not Assets.objects.filter(ISIN="CRYPTO:USDT").exists()

    def test_migration_preserves_btc_transactions(self, user):
        """BTC (non-stablecoin) transactions are NOT affected."""
        mod = _load_migration_module()
        from django.apps import apps as django_apps

        broker = Brokers.objects.create(investor=user, name="OKX2", country="Crypto")
        account = Accounts.objects.create(broker=broker, name="Main2")
        btc = Assets.objects.create(
            ISIN="CRYPTO:BTC", currency="USD", type="Crypto",
            name="BTC", ticker="BTC", exposure="Commodity",
        )
        btc.investors.add(user)
        btc_tx = Transactions.objects.create(
            investor=user, account=account, security=btc,
            currency="USD", type="Crypto trade in",
            date=date(2025, 6, 22),
            quantity=Decimal("0.027"), price=Decimal("60000"),
        )

        mod.migrate_stablecoins_to_cash(django_apps, None)

        btc_tx.refresh_from_db()
        # BTC is NOT a stablecoin — unchanged.
        assert btc_tx.type == "Crypto trade in"
        assert btc_tx.currency == "USD"
        assert btc_tx.security == btc

    def test_migration_idempotent(self, user):
        """Running the migration twice doesn't crash (second run is a no-op)."""
        mod = _load_migration_module()
        from django.apps import apps as django_apps

        asset, deposit, reward, account = self._build_pre_migration_state(user)

        mod.migrate_stablecoins_to_cash(django_apps, None)
        # Second run: no CRYPTO:USDT asset exists → skipped silently.
        mod.migrate_stablecoins_to_cash(django_apps, None)

        # State unchanged after second run.
        deposit.refresh_from_db()
        assert deposit.type == "Cash in"
