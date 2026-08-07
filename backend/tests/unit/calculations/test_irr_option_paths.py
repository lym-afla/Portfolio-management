"""IRR tests for the option cycle (sub-project 4, Task 16).

The SELL premium (BTC inflow) and OTM settlement (no payout) must produce an
XIRR consistent with the +0.00014322 BTC realized profit (premium 0.000154 -
fee 0.00001078). At portfolio scope (``asset_id=None``) the IRR function only
counts EXTERNAL flows (``Cash in`` / ``Cash out`` / crypto transfers); the
option cycle rows themselves are NOT external flows, so their effect on IRR
flows ONLY through the terminal NAV (which includes the BTC premium routed
into the Crypto bucket by Task 14).

Why structural (not exact-rate) assertions
------------------------------------------
XIRR is extremely sensitive to the exact cash-flow dates/magnitudes and the
terminal NAV. Two things make an exact-rate assertion brittle here:

1. The premium (+0.000154 BTC × 60000 = +9.24 USD) is small relative to the
   funding deposit, so the IRR magnitude is small and dominated by the
   holding-period choice (a few days vs. weeks swings the annualized rate).
2. The cash side rounds each currency's balance to 2dp (``account_balance``),
   while the Crypto bucket uses full precision — the terminal NAV has both
   contributions, and tiny rounding residuals accumulate.

Instead we assert what is genuinely invariant for a profitable cycle:
    - IRR returns a finite ``Decimal`` (not "N/A" for a calc failure, not
      "N/R" for short-position/over-MAX_IRR).
    - IRR has the right SIGN — positive for a cycle where net premium was
      kept (terminal NAV > external funding).
    - IRR is within a sane band (between 0 and ``MAX_IRR``).
These confirm the option pipeline doesn't crash the IRR path and that the
realized profit direction is reflected.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import (
    Accounts, Assets, Brokers, OptionMetadata, Prices, Transactions,
)
from services.nav import MAX_IRR, IRR


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
    deterministic: 1 BTC = 60000 USD. The Prices row is dated 2026-01-01 so
    any as-of date in May/June 2026 picks it up (latest-on-or-before lookup).
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
    return Accounts.objects.create(broker=broker, name="Unified", native_id="okx-irr-1")


@pytest.mark.nav
@pytest.mark.unit
class TestIRROptionCycle:
    def test_otm_option_cycle_irr_reflects_premium_kept(self, user, crypto_account):
        """OTM short-option cycle: portfolio IRR is finite and POSITIVE.

        Setup mirrors the canonical BTC-USD-260605-80000-C SELL + OTM expiry
        cycle (capstone test in test_okx_csv_parser.py):

            1. Fund the account with an external ``Cash in`` of 1000 USD on
               2026-01-01. This is the only external flow IRR sees — without
               it the portfolio would be empty and XIRR has nothing to
               reconcile against. The date is pinned EARLY (5 months before
               the cycle) deliberately: a 9.24 USD profit over a 10-day window
               annualizes to ~2500% (capped to "N/R" by MAX_IRR=3), but over
               ~156 days it annualizes to a few percent — well inside the
               function's reportable band.
            2. Open the short: -7 contracts @ 0.0022 BTC/contract,
               cash_flow = +0.000154 BTC (the premium), commission
               -0.00001078 BTC (the BTC fee).
            3. OTM settlement on 2026-06-05: +7 @ 0, cash_flow 0 -> position
               zeroes, no payout.

        Terminal NAV composition on 2026-06-06 (BTC-USD pinned at 60000):
            +1000.00 USD Cash in deposit (Cash side via account_balance)
            +9.24    USD BTC premium in Crypto bucket
                        (Task 14 routing: 0.000154 BTC × 60000 = 9.24)
                        (option contract value = 0: position closed)
            -------
            +1009.24 USD Total NAV

        IRR cash flows (external only): -1000 (Cash in inverted) on 2026-01-01,
        +1009.24 (terminal NAV) on 2026-06-06. Terminal NAV > funding -> XIRR > 0
        (a profitable cycle). The exact annualized rate is brittle (rounding
        of the BTC cash side, the held 9.24 / 1000 = 0.924% return annualizing
        to ~2.2%), so we assert structure + sign + sane band instead.
        """
        _make_btc_underlying(user, usd_price=Decimal("60000"))
        opt = _make_option(user)

        # 1. External funding flow (the ONLY external flow IRR sees). Pinned
        #    early so the small premium annualizes under MAX_IRR.
        Transactions.objects.create(
            investor=user, account=crypto_account, security=None, currency="USD",
            type="Cash in",
            date=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
            cash_flow=Decimal("1000.00"),
        )

        # 2. Open the short: -7 @ 0.0022, premium +0.000154 BTC, fee -0.00001078 BTC.
        #    cash_flow = +0.000154 BTC = 7 × 0.0022 × 0.01 (contract_size).
        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
            commission=Decimal("-0.00001078"), commission_currency="BTC",
        )

        # 3. OTM settlement: +7 @ 0, cash_flow 0 -> position zeroes, no payout.
        Transactions.objects.create(
            investor=user, account=crypto_account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )

        irr = IRR(
            user.id,
            date(2026, 6, 6),
            "USD",
            account_ids=[crypto_account.id],
        )

        # Structural: IRR is a finite Decimal, not a sentinel.
        assert isinstance(irr, Decimal), (
            f"IRR should return a Decimal for a profitable cycle; got sentinel {irr!r}"
        )

        # Sign: profitable cycle (premium kept) -> IRR > 0. Terminal NAV
        # (1009.24 USD) exceeds the funding deposit (1000 USD) by the kept
        # premium, so the rate of return is positive.
        assert irr > Decimal("0"), (
            f"IRR for a profitable OTM short cycle should be positive; got {irr}"
        )

        # Sane band: between 0 and MAX_IRR (the function caps at MAX_IRR=3 and
        # returns "N/R" above it, so any returned Decimal is already below).
        assert Decimal("0") < irr < MAX_IRR, (
            f"IRR should fall in (0, MAX_IRR) band; got {irr} (MAX_IRR={MAX_IRR})"
        )
