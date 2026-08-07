"""Tests for option valuation in the NAV loop (sub-project 4, Task 13).

Spec §5.4 (crypto-option-accounting-and-realized-gain-design.md): a short
option is valued at the manual ``Prices`` mark if present, else at entry cost
(the premium received) so that opening a short is NAV-neutral. At OTM expiry
the position closes to 0 so the liability disappears.

Why ``contract_size`` appears in the option-value formula
---------------------------------------------------------
The NAV-neutral contract (spec §3.4 table) requires the option liability at
entry to EQUAL the premium in magnitude:

    premium (BTC cash_flow)   = +qty × fillPx × contract_size
    option liability (NAV)    = −qty × fillPx × contract_size
    ⇒ ΔNAV at entry = 0  (the two cancel, modulo the real fee)

``calculate_buy_in_price`` returns the per-CONTRACT fill price (coin per
contract, e.g. 0.0022 BTC), and ``position()`` returns the position in
CONTRACTS (e.g. -7), so converting to coin-notional requires multiplying by
``contract_size`` (0.01 for BTC options). Without it the liability would be
100× the premium (0.0154 BTC vs 0.000154 BTC premium) and opening would NOT
be NAV-neutral — contradicting spec §3.4 / §5.4.

Scope note: Task 13 wires only the option's OWN contribution to NAV (the
liability in the Securities breakdown). Routing the BTC premium into the
Crypto bucket is Task 14, so these tests assert on the option's contribution
and the post-expiry zero, NOT on full entry-exit NAV-neutrality.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import (
    Accounts, Assets, Brokers, OptionMetadata, Prices, Transactions,
)
from services.nav import NAV_at_date


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


def _make_btc_underlying(user, usd_price=Decimal("60000")):
    """Create the BTC Crypto asset + a pinned USD price for FX conversion.

    The option settles in BTC, so valuing its BTC-notional liability in USD
    chains through ``fx.get_rate("BTC", "USD")`` → ``crypto_fx_rate`` → the
    BTC asset's ``Prices`` row. Pinning 60000 USD/BTC makes the math
    deterministic: 1 BTC = 60000 USD.
    """
    btc = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC",
        currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
    )
    btc.investors.add(user)
    Prices.objects.create(security=btc, date=date(2026, 1, 1), price=usd_price)
    return btc


@pytest.fixture
def crypto_account(user):
    """A crypto-flavored broker/account (cash_precision=8 for BTC balances)."""
    broker = Brokers.objects.create(
        investor=user, name="OKX", country="Crypto", cash_precision=8
    )
    return Accounts.objects.create(broker=broker, name="Unified", native_id="okx-opt-1")


@pytest.mark.nav
@pytest.mark.unit
class TestNavOpenShortOption:
    def test_open_short_option_valued_at_entry_mark(self, user, crypto_account):
        """Open short -7 @ 0.0022 (size 0.01) marked at fillPx -> -9.24 USD.

        With NO Prices row for the OPTION asset, mark = entry cost (the
        per-contract fill price 0.0022 BTC). The option's contribution to NAV:

            position × mark × contract_size × FX(BTC→USD)
            = -7 × 0.0022 × 0.01 × 60000
            = -9.24 USD   (a liability in the Securities-side asset_type).

        The option MUST appear under asset_type as "Option" with a NEGATIVE
        value (short → liability). Task 14 will route the +0.000154 BTC premium
        into the Crypto bucket to make the open NAV-neutral; until then the
        Total NAV reflects just this liability.
        """
        _make_btc_underlying(user, usd_price=Decimal("60000"))
        opt = _make_option(user)

        # Open the short: -7 contracts @ 0.0022 BTC/contract.
        # cash_flow = +0.000154 BTC = qty × fillPx × contract_size = 7 × 0.0022 × 0.01.
        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
        )

        nav = NAV_at_date(
            user.id, (crypto_account.id,), date(2026, 5, 29), "USD",
            breakdown=("asset_type",),
        )

        # Structure: the option appears under Securities-side asset_type as
        # "Option" (its Assets.type), valued as a liability.
        assert "Option" in nav["asset_type"], (
            f"option missing from asset_type breakdown; got {dict(nav['asset_type'])}"
        )
        # Value = -7 × 0.0022 × 0.01 × 60000 = -9.24 USD (negative = liability).
        assert nav["asset_type"]["Option"] == Decimal("-9.24"), (
            f"option liability wrong; got {nav['asset_type']['Option']}, "
            "expected -9.24 (-7 × 0.0022 × 0.01 × 60000)"
        )

    def test_manual_option_mark_overrides_entry_cost(self, user, crypto_account):
        """A Prices row on the OPTION asset -> NAV marks to it (manual MTM).

        With a manual mark of 0.005 BTC/contract, the option's contribution
        becomes -7 × 0.005 × 0.01 × 60000 = -21.00 USD, not the entry-cost
        -9.24 USD. (Spec §5.4: "Prices row present -> NAV marks to that price
        -> on-demand MTM. No auto-fetch.")
        """
        _make_btc_underlying(user, usd_price=Decimal("60000"))
        opt = _make_option(user)

        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
        )
        # Manual MTM mark on the OPTION asset: 0.005 BTC per contract.
        # (Entry cost was 0.0022; the user is marking it higher -> bigger liability.)
        Prices.objects.create(
            security=opt, date=date(2026, 5, 29), price=Decimal("0.005"),
        )

        nav = NAV_at_date(
            user.id, (crypto_account.id,), date(2026, 5, 29), "USD",
            breakdown=("asset_type",),
        )
        # -7 × 0.005 × 0.01 × 60000 = -21.00 USD (manual mark, NOT entry cost).
        assert nav["asset_type"]["Option"] == Decimal("-21.00"), (
            f"manual MTM mark wrong; got {nav['asset_type']['Option']}, "
            "expected -21.00 (-7 × 0.005 × 0.01 × 60000)"
        )

    def test_closed_option_has_zero_nav_contribution(self, user, crypto_account):
        """After OTM settlement closes the position, the option contributes 0.

        The settlement row (+7 contracts) zeroes the position, so the option
        no longer appears in NAV — the liability disappears (spec §5.4: "At
        expiry OTM the closing Option settlement row zeroes the position ->
        option_value = 0 -> the liability disappears").
        """
        _make_btc_underlying(user, usd_price=Decimal("60000"))
        opt = _make_option(user)

        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
        )
        # OTM settlement: +7 @ 0, cash_flow 0 -> position zeroes.
        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )

        nav = NAV_at_date(
            user.id, (crypto_account.id,), date(2026, 6, 6), "USD",
            breakdown=("asset_type",),
        )
        # Position closed -> option contributes 0 (absent from breakdown, or 0).
        option_value = nav["asset_type"].get("Option", Decimal("0"))
        assert option_value == Decimal("0"), (
            f"closed option should contribute 0; got {option_value}"
        )
