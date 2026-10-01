"""Protected NAV_at_date diagnostics: default-off output equivalence and provenance.

``diagnostics`` is a new optional keyword-only argument. These tests prove the
default call output is identical with and without the argument across the
option/crypto/ordinary fixtures, that omission branches record the actual
omitted source, and that no state leaks between calls.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import (
    Accounts,
    Assets,
    Brokers,
    OptionMetadata,
    Prices,
    Transactions,
)
from services.nav import NAV_at_date, get_fx_rate

pytestmark = pytest.mark.django_db


def make_broker_account(user, name="Unified", cash_precision=8):
    broker = Brokers.objects.create(
        investor=user, name=f"broker-{name}", country="Crypto", cash_precision=cash_precision
    )
    return Accounts.objects.create(broker=broker, name=name)


def make_option(user, settle_coin="DOGE", expiry=date(2026, 6, 5)):
    name = f"{settle_coin}-{expiry.strftime('%d%b%y').upper()}-80000-C"
    asset = Assets.objects.create(
        type="Option",
        ISIN=f"CRYPTO:OPT:{name}",
        name=name,
        currency=settle_coin,
        exposure="Derivatives",
    )
    asset.investors.add(user)
    OptionMetadata.objects.create(
        asset=asset,
        strike_price=Decimal("80000"),
        option_type="CALL",
        expiration_date=expiry,
        contract_size=Decimal("0.01"),
    )
    return asset


def make_crypto(user, name="TRUMP", isin="CRYPTO:TRUMP"):
    asset = Assets.objects.create(
        type="Crypto", ISIN=isin, name=name, currency="USD", exposure="Commodity"
    )
    asset.investors.add(user)
    return asset


def make_unpriced_coin(user, name="DOGE"):
    """A Crypto-class coin asset with no Prices row (production unpriced coin)."""
    return make_crypto(user, name=name, isin=f"CRYPTO:{name}")


def make_stock(user, name="Priced Stock"):
    asset = Assets.objects.create(
        type="Stock",
        ISIN=f"US{abs(hash(name)) % 10**9:09d}",
        name=name,
        currency="USD",
        exposure="Equity",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def crypto_account(user):
    return make_broker_account(user)


@pytest.fixture(autouse=True)
def fresh_fx_cache():
    """The FX lru_cache is process-global; keep rate lookups deterministic."""
    get_fx_rate.cache_clear()
    yield
    get_fx_rate.cache_clear()


class TestDefaultEquivalence:
    def test_default_call_signature_unchanged_and_identical_output(
        self, user, crypto_account
    ):
        stock = make_stock(user)
        Prices.objects.create(security=stock, date=date(2026, 1, 1), price=Decimal("50"))
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            type="Cash in",
            currency="USD",
            date=datetime(2026, 1, 4, tzinfo=timezone.utc),
            cash_flow=Decimal("500"),
        )
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=stock,
            currency="USD",
            type="Buy",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("10"),
            price=Decimal("50"),
        )
        kwargs = dict(
            user_id=user.id,
            account_ids=(crypto_account.id,),
            date=date(2026, 1, 31),
            target_currency="USD",
            breakdown=("asset_type",),
        )
        default = NAV_at_date(**kwargs)
        explicit_off = NAV_at_date(**kwargs, diagnostics=None)
        assert default == explicit_off
        assert default["Total NAV"] == Decimal("500")

    def test_diagnostics_on_returns_same_dictionary(self, user, crypto_account):
        stock = make_stock(user)
        Prices.objects.create(security=stock, date=date(2026, 1, 1), price=Decimal("50"))
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            type="Cash in",
            currency="USD",
            date=datetime(2026, 1, 4, tzinfo=timezone.utc),
            cash_flow=Decimal("500"),
        )
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=stock,
            currency="USD",
            type="Buy",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("10"),
            price=Decimal("50"),
        )
        kwargs = dict(
            user_id=user.id,
            account_ids=(crypto_account.id,),
            date=date(2026, 1, 31),
            target_currency="USD",
            breakdown=("asset_type",),
        )
        without = NAV_at_date(**kwargs)
        collected = []
        with_on = NAV_at_date(**kwargs, diagnostics=collected)
        assert with_on == without
        assert collected == []  # nothing was omitted


class TestOmissionProvenance:
    def test_unpriced_crypto_records_missing_price_with_source(self, user, crypto_account):
        # The coin has a last-trade fallback quote but in a currency with no
        # FX path, so its USD price is unavailable: price_at_date raises and
        # NAV skips the coin (issue #5a behavior).
        trump = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:TRUMP", name="TRUMP",
            currency="ZZZ", exposure="Commodity",
        )
        trump.investors.add(user)
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=trump,
            currency="ZZZ",
            type="Crypto trade in",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("10"),
            price=Decimal("1"),
        )
        diagnostics = []
        nav = NAV_at_date(
            user.id,
            (crypto_account.id,),
            date(2026, 1, 31),
            "USD",
            breakdown=("asset_type",),
            diagnostics=diagnostics,
        )
        assert nav["Total NAV"] == Decimal("0")  # unpriced coin excluded, not zero-filled
        # Both omission sources record: the coin's USD price is unavailable
        # (securities loop) and its ZZZ cash side cannot be FX-converted
        # (cash loop).
        assert diagnostics == [
            {
                "reason": "missing_price",
                "account_id": crypto_account.id,
                "asset_id": trump.id,
                "currency": "ZZZ",
                "asset_type": "Crypto",
                "asset_class": "Commodity",
            },
            {
                "reason": "missing_fx",
                "account_id": crypto_account.id,
                "currency": "ZZZ",
                "asset_type": "Cash",
                "asset_class": "Cash",
            },
        ]

    def test_unpriced_option_settle_coin_records_missing_fx(self, user, crypto_account):
        make_unpriced_coin(user, name="DOGE")
        opt = make_option(user, settle_coin="DOGE")
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=opt,
            currency="DOGE",
            type="Crypto trade out",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("-7"),
            price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
        )
        diagnostics = []
        NAV_at_date(
            user.id,
            (crypto_account.id,),
            date(2026, 1, 31),
            "USD",
            breakdown=("asset_type",),
            diagnostics=diagnostics,
        )
        # The unpriced settle coin omits both the option liability (securities
        # loop) and the routed premium (option cash-flow loop): the coin has no
        # own transactions, so it is not in covered_crypto_names.
        assert diagnostics == [
            {
                "reason": "missing_fx",
                "account_id": crypto_account.id,
                "asset_id": opt.id,
                "currency": "DOGE",
                "asset_type": "Option",
                "asset_class": "Derivatives",
            },
            {
                "reason": "missing_fx",
                "account_id": crypto_account.id,
                "asset_id": opt.id,
                "currency": "DOGE",
            },
        ]

    def test_cash_without_fx_records_missing_fx(self, user, crypto_account):
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            type="Cash in",
            currency="GBP",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            cash_flow=Decimal("100"),
        )
        diagnostics = []
        nav = NAV_at_date(
            user.id,
            (crypto_account.id,),
            date(2026, 1, 31),
            "USD",
            breakdown=("asset_type",),
            diagnostics=diagnostics,
        )
        assert nav["Total NAV"] == Decimal("0")
        assert diagnostics == [
            {
                "reason": "missing_fx",
                "account_id": crypto_account.id,
                "currency": "GBP",
                "asset_type": "Cash",
                "asset_class": "Cash",
            }
        ]

    def test_option_cash_flow_unpriced_coin_records_missing_fx(self, user, crypto_account):
        make_unpriced_coin(user, name="DOGE")
        opt = make_option(user, settle_coin="DOGE")
        # Settlement payout in a coin that has no USD price and no own asset row.
        # The coin-settled premium is excluded from cash balances, so the only
        # omission comes from the option cash-flow routing branch.
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=opt,
            currency="DOGE",
            type="Option settlement",
            date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            cash_flow=Decimal("1"),
        )
        diagnostics = []
        NAV_at_date(
            user.id,
            (crypto_account.id,),
            date(2026, 1, 31),
            "USD",
            diagnostics=diagnostics,
        )
        assert diagnostics == [
            {
                "reason": "missing_fx",
                "account_id": crypto_account.id,
                "asset_id": opt.id,
                "currency": "DOGE",
            }
        ]

    def test_priced_sources_produce_no_diagnostics_and_count_in_nav(
        self, user, crypto_account
    ):
        btc = make_crypto(user, name="BTC", isin="CRYPTO:BTC")
        Prices.objects.create(security=btc, date=date(2026, 1, 1), price=Decimal("60000"))
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            type="Cash in",
            currency="USD",
            date=datetime(2026, 1, 4, tzinfo=timezone.utc),
            cash_flow=Decimal("60000"),
        )
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=btc,
            currency="USD",
            type="Crypto trade in",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("1"),
            price=Decimal("60000"),
        )
        diagnostics = []
        nav = NAV_at_date(
            user.id,
            (crypto_account.id,),
            date(2026, 1, 31),
            "USD",
            diagnostics=diagnostics,
        )
        assert nav["Total NAV"] == Decimal("60000")
        assert diagnostics == []

    def test_repeated_calls_do_not_leak_state(self, user, crypto_account):
        trump = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:TRUMP", name="TRUMP",
            currency="ZZZ", exposure="Commodity",
        )
        trump.investors.add(user)
        Transactions.objects.create(
            investor=user,
            account=crypto_account,
            security=trump,
            currency="ZZZ",
            type="Crypto trade in",
            date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("10"),
            price=Decimal("1"),
        )
        first, second = [], []
        NAV_at_date(user.id, (crypto_account.id,), date(2026, 1, 31), "USD", diagnostics=first)
        NAV_at_date(user.id, (crypto_account.id,), date(2026, 1, 31), "USD", diagnostics=second)
        assert first == second
        assert len(first) == 2  # coin omission + its cash side, deterministic

    def test_explicit_zero_portfolio_is_not_an_omission(self, user, crypto_account):
        # No transactions at all: the NAV is an observed exact zero, not an
        # omitted valuation. Zero is only 'zero_exposure' when a source
        # establishes it; absence is not proven zero exposure either.
        diagnostics = []
        nav = NAV_at_date(
            user.id, (crypto_account.id,), date(2026, 1, 31), "USD", diagnostics=diagnostics
        )
        assert nav["Total NAV"] == Decimal("0")
        assert diagnostics == []
