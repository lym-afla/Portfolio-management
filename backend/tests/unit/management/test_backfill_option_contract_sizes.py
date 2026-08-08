"""Tests for the backfill_option_contract_sizes management command."""
from decimal import Decimal

import pytest
from django.core.management import call_command

from common.models import Assets, OptionMetadata


def _make_option(user, name, underlying):
    asset = Assets.objects.create(
        type="Option", ISIN=f"CRYPTO:OPT:{name}", name=name,
        currency="USD", exposure="Derivatives",
    )
    asset.investors.add(user)
    meta = OptionMetadata.objects.create(
        asset=asset, strike_price=Decimal("80000"),
        option_type="CALL", contract_size=Decimal("1"),  # old default
    )
    return asset, meta


@pytest.mark.django_db
class TestBackfillOptionContractSizes:
    def test_sets_btc_and_eth(self, user):
        btc_asset, btc_meta = _make_option(user, "BTC-05JUN26-80000-C", "BTC")
        eth_asset, eth_meta = _make_option(user, "ETH-05JUN26-3000-P", "ETH")
        assert btc_meta.contract_size == Decimal("1")  # precondition

        call_command("backfill_option_contract_sizes")

        btc_meta.refresh_from_db()
        eth_meta.refresh_from_db()
        assert btc_meta.contract_size == Decimal("0.01")
        assert eth_meta.contract_size == Decimal("0.1")

    def test_idempotent(self, user):
        _make_option(user, "BTC-05JUN26-80000-C", "BTC")
        call_command("backfill_option_contract_sizes")
        # Running again must not error or change values.
        call_command("backfill_option_contract_sizes")
        meta = OptionMetadata.objects.get(asset__name="BTC-05JUN26-80000-C")
        assert meta.contract_size == Decimal("0.01")

    def test_only_touches_size_one_rows(self, user):
        """A row already set to 0.01 (correct) is left alone."""
        asset = Assets.objects.create(
            type="Option", ISIN="x", name="BTC-05JUN26-80000-C",
            currency="USD", exposure="Derivatives",
        )
        asset.investors.add(user)
        OptionMetadata.objects.create(
            asset=asset, strike_price=Decimal("80000"),
            option_type="CALL", contract_size=Decimal("0.01"),
        )
        call_command("backfill_option_contract_sizes")
        meta = OptionMetadata.objects.get(asset=asset)
        assert meta.contract_size == Decimal("0.01")  # unchanged
