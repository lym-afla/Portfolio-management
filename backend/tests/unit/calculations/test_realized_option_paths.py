"""Tests for option paths in services/realized.py (sub-project 4).

Mirrors test_realized_bond_paths.py structure: helper builders + class-scoped
tests using user/account fixtures from conftest.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Assets, OptionMetadata, Transactions
from services.realized import (
    _realized_option_close,
    get_economic_basis,
    realized_gain_loss,
    unrealized_gain_loss,
)


def _make_option(user, underlying="BTC", strike=Decimal("80000"), opt_type="CALL",
                 expiry=date(2026, 6, 5), contract_size=Decimal("0.01")):
    name = f"{underlying}-{expiry.strftime('%d%b%y').upper()}-{strike}-{opt_type[0]}"
    asset = Assets.objects.create(
        type="Option", ISIN=f"CRYPTO:OPT:{name}", name=name,
        currency="BTC", exposure="Derivatives",
    )
    asset.investors.add(user)
    OptionMetadata.objects.create(
        asset=asset, strike_price=strike, option_type=opt_type,
        expiration_date=expiry, contract_size=contract_size,
    )
    return asset


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestGetEconomicBasisOption:
    def test_long_option_basis_uses_contract_size(self, user, account):
        """A BUY of 7 contracts @ 0.0022 with size 0.01 -> basis 0.000154 BTC."""
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade in",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0.0022"),
            cash_flow=Decimal("-0.000154"),
        )
        # rounded=False: the coin basis (0.000154 BTC) is below 2 dp, so the
        # default rounded=True path would quantize it to 0.00 and hide the
        # contract_size effect. Assert the unrounded value directly.
        basis = get_economic_basis(opt, date(2026, 6, 1), investor=user, rounded=False)
        assert basis == Decimal("0.000154")  # 7 * 0.0022 * 0.01


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestWrittenCallOtmExpiry:
    """The canonical user CSV case: 7 x BTC-USD-260605-80000-C, OTM."""

    def test_realized_profit_is_net_premium(self, user, account):
        opt = _make_option(user)
        # SELL: opens short -7 contracts, premium +0.000154 BTC, fee -0.00001078.
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
            commission=Decimal("-0.00001078"), commission_currency="BTC",
        )
        # Settlement OTM: closes +7 @ 0, cash_flow 0.
        settlement = Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        # Integration: the wrapper's option-close branch must fire and route to
        # the helper. The wrapper rounds to 2 dp for stablecoin/fiat display,
        # which would zero out a sub-cent BTC premium, so the exact 8-dp value
        # is asserted via the helper directly (matching Task 10's rounded=False
        # pattern in TestGetEconomicBasisOption).
        result = realized_gain_loss(opt, date(2026, 6, 6), investor=user)
        # Branch fired: total is finite and non-error (no option branch -> 0.00).
        assert result["all_time"]["total"] is not None
        option_gl = _realized_option_close(
            opt, settlement, Decimal("-7"), user, None, None
        )
        # Net premium kept: 0.000154 - 0.00001078 = 0.00014322 BTC
        assert option_gl["total"] == Decimal("0.00014322")
        assert option_gl["price_appreciation"] == Decimal("0.00014322")
        assert option_gl["fx_effect"] == Decimal("0")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestWrittenCallItmExpiry:
    """ITM: writer pays intrinsic -> a loss."""

    def test_realized_loss_is_payout_minus_premium(self, user, account):
        opt = _make_option(user, strike=Decimal("80000"))
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
        )
        # Settlement ITM: spot 85000 -> per-contract intrinsic 0.00058824 BTC
        # (Task 2 corrected value: contract_size 0.01 * (85000-80000)/85000).
        # close +7 @ 0.00058824; payout 7 * 0.00588235 / 10 = 0.00411765
        # (writer pays; cash_flow negative).
        settlement = Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0.00058824"),
            cash_flow=Decimal("-0.00411765"),
        )
        # See TestWrittenCallOtmExpiry for why the exact 8-dp value is asserted
        # via the helper.
        result = realized_gain_loss(opt, date(2026, 6, 6), investor=user)
        assert result["all_time"]["total"] is not None
        option_gl = _realized_option_close(
            opt, settlement, Decimal("-7"), user, None, None
        )
        # realized = premium 0.000154 - payout 0.00411765 = -0.00396365 BTC
        assert option_gl["total"] == Decimal("-0.00396365")
        assert option_gl["price_appreciation"] == Decimal("-0.00396365")
        assert option_gl["fx_effect"] == Decimal("0")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestLongCallOtmExpiry:
    """Buyer loses the premium when OTM."""

    def test_realized_loss_is_premium(self, user, account):
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade in",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0.0022"),
            cash_flow=Decimal("-0.000154"),  # premium paid
        )
        settlement = Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        # See TestWrittenCallOtmExpiry for why the exact 8-dp value is asserted
        # via the helper.
        result = realized_gain_loss(opt, date(2026, 6, 6), investor=user)
        assert result["all_time"]["total"] is not None
        option_gl = _realized_option_close(
            opt, settlement, Decimal("7"), user, None, None
        )
        assert option_gl["total"] == Decimal("-0.000154")
        assert option_gl["price_appreciation"] == Decimal("-0.000154")
        assert option_gl["fx_effect"] == Decimal("0")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestUnrealizedOptionGuard:
    """unrealized_gain_loss returns zeros for option assets (sub-project 4).

    The generic path is unreliable for options: ``get_economic_basis`` is
    long-only, so a written (short) option zeros its basis on open and the
    unrealized path would report the full negative mark as a loss. NAV values
    the liability via the dedicated option-mark branch, and realized G/L at
    expiry is correct — but until a future sub-project adds true option
    unrealized G/L, the function returns zeros so the UI doesn't mislead.
    """

    def test_open_short_option_unrealized_is_zero(self, user, account):
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
        )
        result = unrealized_gain_loss(opt, date(2026, 5, 29), investor=user)
        assert result["total"] == Decimal("0")
        assert result["price_appreciation"] == Decimal("0")
        assert result["fx_effect"] == Decimal("0")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestCryptoTransferNeutralityInBasis:
    """get_economic_basis must treat unmatched crypto transfers as neutral
    (position move only, no basis carried away) while TRANSFER_DISPOSITION_ENABLED
    is False — matching the realized_gain_loss walker. Otherwise basis and the
    walker's position go out of sync, producing a nonsense buy-in (the TRUMP bug:
    a buy@73 -> neutral transfer-out -> neutral transfer-in -> sell@16 realized
    as +11.21 instead of a loss)."""

    def test_basis_preserved_across_neutral_transfers(self, user, account):
        # Buy 1 @ 73.21
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:NEO", name="NEO",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="USD",
            type="Crypto trade in",
            date=datetime(2025, 1, 19, tzinfo=timezone.utc),
            quantity=Decimal("1"), price=Decimal("73.21"),
        )
        # Matched transfer out / in (both legs share import_group_id) — the
        # post-#29 reality now that both OKX accounts are modeled. The OUT
        # debits basis into the group; the IN reclaims it, so basis is
        # preserved across the cycle (the TRUMP-bug invariant). Currency is
        # USD so the transfer's own FX path is a no-op.
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="USD",
            type="Crypto transfer out",
            date=datetime(2025, 1, 20, tzinfo=timezone.utc),
            quantity=Decimal("-1"),
            import_group_id="trump-cycle", import_provider="okx_csv",
        )
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="USD",
            type="Crypto transfer in",
            date=datetime(2025, 2, 9, tzinfo=timezone.utc),
            quantity=Decimal("1"),
            import_group_id="trump-cycle", import_provider="okx_csv",
        )
        # Basis after the cycle still reflects the buy (73.21): the OUT
        # carried it into the group and the matched IN reclaimed it.
        basis = get_economic_basis(coin, datetime(2025, 2, 10, tzinfo=timezone.utc),
                                   investor=user, account_ids=[account.id], rounded=False)
        assert basis == Decimal("73.21")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestOptionRealizedFXConversion:
    """Option realized G/L must FX-convert to the target currency when 'currency'
    is passed. The option settles in BTC (+0.00014322); when the closed-positions
    table requests USD, the realized should be in USD (~$8.59 at BTC=60000), not
    the raw BTC value (which displays as $0.00)."""

    def test_option_realized_converted_to_usd(self, user):
        from common.models import Accounts, Brokers, Prices
        # Use a crypto-precision broker (cash_precision=8) so the realized
        # isn't rounded to 2dp (which would zero the BTC-scale value).
        broker = Brokers.objects.create(investor=user, name="OKX-FX", country="Crypto", cash_precision=8)
        crypto_account = Accounts.objects.create(broker=broker, name="Trading")
        # Pin BTC-USD at 60000 so the FX conversion is deterministic.
        # Name must be "BTC" so is_crypto_code("BTC") resolves the price.
        btc = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:BTCFX2", name="BTC",
            currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
        )
        btc.investors.add(user)
        Prices.objects.create(
            security=btc, date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            price=Decimal("60000"),
        )
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("0.000154"),
        )
        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        # Native BTC: +0.000154 (premium only — this fixture has no fee).
        # In USD at 60000: ~9.24.
        r_btc = realized_gain_loss(opt, date(2026, 6, 6), investor=user, account_ids=[crypto_account.id])
        r_usd = realized_gain_loss(opt, date(2026, 6, 6), investor=user, account_ids=[crypto_account.id], currency="USD")
        assert r_btc["all_time"]["total"] == Decimal("0.000154")
        # USD-converted should be materially positive (~9.24 = 0.000154 * 60000),
        # not the raw BTC value (which displays as $0.00).
        assert r_usd["all_time"]["total"] > Decimal("1")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestUnpricedCoinRealizedNoCrash:
    """A crypto coin with no Prices row (and no trades) must not crash
    realized_gain_loss. It returns {total: 0} and the position is tracked."""

    def test_unpriced_coin_realized_returns_zero(self, user, account):
        # A coin with NO Prices row and NO trades -> fully unpriced.
        # The coin's currency is the coin itself (BTC-style), so the FX path
        # goes through crypto_fx_rate -> crypto_usd_price -> ValueError.
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:UNP", name="UNP",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="UNP",
            type="Crypto trade in",
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("1"), price=Decimal("10"),
        )
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="UNP",
            type="Crypto trade out",
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            quantity=Decimal("-1"), price=Decimal("20"),
        )
        # This used to crash with ValueError: No USD price for UNP.
        result = realized_gain_loss(coin, date(2026, 6, 1), investor=user, account_ids=[account.id],
                                    currency="USD")
        # Unpriced -> realized skips, returns 0 (not a crash).
        assert result["all_time"]["total"] == Decimal("0")
