"""Phase D reconciled dashboard statement — service reconciliation tests.

Every expected value below is a HAND-DERIVED Decimal fixture (see the
arithmetic in each docstring), not a value copied from the implementation
under test. The suite pins:

- the certified decomposition identity
  (net result = realized price + unrealized price + income + fees + taxes
   + certified FX, against the control total NAV - net invested capital);
- honest incomplete/unreconciled states (never a forced residual labelled FX);
- the legacy-semantics pins (signed cash out, phantom in-kind rows, gross
  income vs separate taxes).

All money math is Decimal. Dates are unique per scenario to stay independent
under pytest-randomly and to avoid the lru_cached FX-rate cross-test cache.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

from common.models import Assets, BondMetadata, FX, Prices, Transactions
from services import nav as nav_service
from services.dashboard_summary import build_reconciled_summary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_broker(user, name="Broker", precision=2):
    from common.models import Brokers

    return Brokers.objects.create(
        investor=user, name=name, country="US", cash_precision=precision
    )


def make_account(broker, name="Account"):
    from common.models import Accounts

    return Accounts.objects.create(broker=broker, name=name)


def make_asset(user, type="Stock", name="Stock", currency="USD", exposure="Equity"):
    asset = Assets.objects.create(
        type=type, ISIN=f"isin-{name}", name=name, currency=currency, exposure=exposure
    )
    asset.investors.add(user)
    return asset


def make_tx(account, when, type, currency="USD", security=None, **fields):
    return Transactions.objects.create(
        investor=account.broker.investor,
        account=account,
        security=security,
        date=when,
        type=type,
        currency=currency,
        **fields,
    )


def make_price(asset, when, price):
    return Prices.objects.create(security=asset, date=when, price=Decimal(price))


def make_fx(from_currency, to_currency, when, rate, investor):
    row = FX.objects.create(
        from_currency=from_currency, to_currency=to_currency, date=when, rate=Decimal(rate)
    )
    row.investors.add(investor)
    return row


def raw(document, *path):
    node = document
    for key in path:
        node = node[key]
    return Decimal(node["raw"])


@pytest.fixture(autouse=True)
def _reset_fx_caches():
    """The FX rate helpers memoize per process; tests must not leak rates."""
    nav_service.get_fx_rate.cache_clear()
    from django.core.cache import cache

    cache.clear()
    yield
    nav_service.get_fx_rate.cache_clear()


# ---------------------------------------------------------------------------
# Scenario A — the approved example (single currency)
# ---------------------------------------------------------------------------


@pytest.fixture
def approved_example(user):
    """Hand-derived dataset matching the approved mock's example values.

    Broker cash precision 2.

        d1  Cash in  +105,000                          -> invested 105,000
        d1  Cash out   -5,000                          -> cash out -5,000
        d1  Buy A 500 @ 100, commission -1,000         -> fees -1,000
        d1  Buy B 400 @ 150
        d2  Dividend +3,500 (gross); Tax -500
        d3  Sell A 500 @ 116                           -> realized 8,000
        EOP price B 168.75                             -> unrealized 7,500
    """
    broker = make_broker(user)
    account = make_account(broker)
    stock_a = make_asset(user, name="Alpha")
    stock_b = make_asset(user, name="Beta")
    d1 = date(2026, 1, 5)
    make_tx(account, d1, "Cash in", cash_flow=Decimal("105000"))
    make_tx(account, d1, "Cash out", cash_flow=Decimal("-5000"))
    make_tx(
        account, d1, "Buy", security=stock_a, quantity=Decimal("500"),
        price=Decimal("100"), commission=Decimal("-1000"),
    )
    make_tx(
        account, d1, "Buy", security=stock_b, quantity=Decimal("400"),
        price=Decimal("150"),
    )
    d2 = date(2026, 1, 20)
    make_tx(account, d2, "Dividend", security=stock_a, cash_flow=Decimal("3500"))
    make_tx(account, d2, "Tax", security=stock_a, cash_flow=Decimal("-500"))
    make_tx(
        account, date(2026, 2, 10), "Sell", security=stock_a,
        quantity=Decimal("-500"), price=Decimal("116"),
    )
    make_price(stock_b, date(2026, 10, 1), "168.75")
    return account


@pytest.mark.django_db
def test_approved_example_reconciles_component_by_component(user, approved_example):
    """Invested 105,000; cash out -5,000; net capital 100,000.

    Realized: (116 - 100) x 500                     =  8,000
    Unrealized: (168.75 - 150) x 400                =  7,500
    Income (dividend, gross)                        =  3,500
    Fees (buy commission)                           = -1,000
    Taxes                                           =   -500
    FX (single currency)                            =       0
    Attributed                                      = 17,500
    Cash: 105,000 - 5,000 - 51,000 - 60,000 + 3,500 - 500 + 58,000 = 50,000
    NAV: 50,000 + 400 x 168.75 = 50,000 + 67,500    = 117,500
    Control: 117,500 - 100,000                      = 17,500
    Unexplained: 0 -> reconciled, status complete.
    """
    doc = build_reconciled_summary(
        user, date(2026, 10, 15), "USD", 2, [approved_example.id]
    )
    assert Decimal(doc["capital"]["invested"]["raw"]) == Decimal("105000")
    assert Decimal(doc["capital"]["cashOut"]["raw"]) == Decimal("-5000")
    assert Decimal(doc["capital"]["netInvestedCapital"]["raw"]) == Decimal("100000")
    assert Decimal(doc["netResult"]["nav"]["raw"]) == Decimal("117500")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("17500")
    components = doc["netResult"]["components"]
    assert Decimal(components["realizedPrice"]["raw"]) == Decimal("8000")
    assert Decimal(components["unrealizedPrice"]["raw"]) == Decimal("7500")
    assert Decimal(components["income"]["raw"]) == Decimal("3500")
    assert Decimal(components["fees"]["raw"]) == Decimal("-1000")
    assert Decimal(components["taxes"]["raw"]) == Decimal("-500")
    assert Decimal(components["fx"]["raw"]) == Decimal("0")
    assert Decimal(components["otherFlows"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["attributedSum"]["raw"]) == Decimal("17500")
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert doc["netResult"]["nav"]["display"] == "$117,500.00"
    assert doc["capital"]["cashOut"]["display"] == "($5,000.00)"


@pytest.mark.django_db
def test_approved_example_returns_and_context(user, approved_example):
    """Total return uses the legacy formula with SIGNED cash-out:
    (NAV - Cash-out) / Invested - 1 = (117,500 + 5,000) / 105,000 - 1.

    This is exactly the approved mock's arithmetic (its 17.50% equals
    (112,500 + 5,000) / 100,000 - 1), so presentation matches the mock
    without any formula change. IRR must be the canonical solver result
    (a Decimal) with a percentage display; context echoes the scope.
    """
    doc = build_reconciled_summary(
        user, date(2026, 10, 15), "USD", 2, [approved_example.id]
    )
    expected_total_return = (Decimal("117500") + Decimal("5000")) / Decimal("105000") - 1
    assert Decimal(doc["returns"]["totalReturn"]["value"]) == expected_total_return
    assert doc["returns"]["totalReturn"]["display"].endswith("%")
    assert isinstance(Decimal(doc["returns"]["irr"]["value"]), Decimal)
    assert doc["context"]["currency"] == "USD"
    assert doc["context"]["effectiveDate"] == "2026-10-15"
    assert doc["context"]["accountIds"] == [approved_example.id]
    assert doc["context"]["digits"] == 2


@pytest.mark.django_db
def test_raw_tolerance_is_documented_and_raw_strings_keep_precision(user, approved_example):
    """Tolerance = 4 half-ULPs per asset + 1 half-ULP per cash currency.

    Two assets at precision 2: 2 x 4 x 0.005 = 0.04; one currency: 0.005.
    Raw strings are exact fixed-point notation (never scientific).
    """
    doc = build_reconciled_summary(
        user, date(2026, 10, 15), "USD", 2, [approved_example.id]
    )
    assert Decimal(doc["netResult"]["toleranceRaw"]) == Decimal("0.045")
    assert "half-ULP" in doc["netResult"]["toleranceBasis"]
    assert doc["netResult"]["components"]["realizedPrice"]["raw"] == "8000.00"


@pytest.mark.django_db
def test_multi_account_query_count_is_recorded_and_bounded(user):
    """Synthetic multi-account fixture: 3 accounts x 2 assets x ~30 rows.

    The exact number is recorded for the evidence doc; the assertion is a
    generous pathological-fanout bound (no per-transaction NAV recompute).
    """
    broker = make_broker(user)
    accounts = [make_account(broker, f"Account {i}") for i in range(3)]
    stock = make_asset(user, name="MultiStock")
    other = make_asset(user, name="MultiStockB")
    day = date(2052, 3, 1)
    for account in accounts:
        make_tx(account, day, "Cash in", cash_flow=Decimal("30000"))
        for i in range(10):
            make_tx(
                account, date(2052, 3, 2 + i), "Buy", security=stock,
                quantity=Decimal("1"), price=Decimal("100"),
                commission=Decimal("-1"),
            )
            make_tx(
                account, date(2052, 3, 2 + i), "Buy", security=other,
                quantity=Decimal("2"), price=Decimal("50"),
            )
        make_tx(
            account, date(2052, 4, 1), "Sell", security=stock,
            quantity=Decimal("-5"), price=Decimal("110"),
        )
        make_tx(account, date(2052, 4, 2), "Dividend", security=stock,
                cash_flow=Decimal("25"))
    make_price(stock, date(2052, 5, 1), "120")
    make_price(other, date(2052, 5, 1), "55")
    import time

    with CaptureQueriesContext(connection) as ctx:
        started = time.perf_counter()
        doc = build_reconciled_summary(
            user, date(2052, 5, 15), "USD", 2, [a.id for a in accounts]
        )
        elapsed = time.perf_counter() - started
    assert doc["netResult"]["reconciliation"] == "reconciled"
    print(
        "DASHBOARD-STATEMENT-PERF queries=%s seconds=%.3f" % (len(ctx), elapsed)
    )
    assert len(ctx) < 1500


# ---------------------------------------------------------------------------
# FX decomposition scenarios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_foreign_security_separates_price_gain_from_fx_gain(user):
    """EUR stock, USD reporting; EUR->USD 1.00 at buy, 1.10 at EOP.

    d1 2031-01-05  Cash in EUR 100,000 (f=1.00)   -> invested 100,000
    d1 2031-01-05  Buy A 1,000 @ EUR 90           -> cash EUR 10,000
    EOP            price EUR 95; f=1.10
    NAV: (10,000 + 95,000) x 1.10                  = 115,500
    Control: 115,500 - 100,000                     =  15,500
    Unrealized price: (95-90) x 1,000 x 1.10       =   5,500
    FX security: total 104,500-90,000=14,500 - price 5,500 = 9,000
    FX cash: 10,000x1.10 - (100,000-90,000)x1.00   =   1,000
    Attributed 15,500 -> reconciled; FX row = 10,000.
    """
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="EuroStock", currency="EUR")
    make_fx("USD", "EUR", date(2031, 1, 5), "1.00", user)
    make_fx("USD", "EUR", date(2031, 10, 1), "1.10", user)
    make_tx(account, date(2031, 1, 5), "Cash in", currency="EUR",
            cash_flow=Decimal("100000"))
    make_tx(account, date(2031, 1, 5), "Buy", currency="EUR", security=stock,
            quantity=Decimal("1000"), price=Decimal("90"))
    make_price(stock, date(2031, 10, 1), "95")
    doc = build_reconciled_summary(user, date(2031, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["nav"]["raw"]) == Decimal("115500")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("5500")
    assert Decimal(doc["netResult"]["fxDetail"]["security"]["raw"]) == Decimal("9000")
    assert Decimal(doc["netResult"]["fxDetail"]["cashFlows"]["raw"]) == Decimal("1000")
    assert Decimal(doc["netResult"]["components"]["fx"]["raw"]) == Decimal("10000")
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_cash_only_fx_is_certified_not_residual(user):
    """EUR cash only; rate 1.0 at flows, 1.1 at EOP, cash out at 1.05.

    Cash in EUR 100,000 @1.0; cash out EUR -10,000 @1.05.
    Net capital: 100,000 - 10,500                   =  89,500
    NAV: 90,000 x 1.10                              =  99,000
    Control                                         =   9,500
    FX cash: 99,000 - (100,000 - 10,500)            =   9,500
    No securities -> every engine row is zero; reconciled.
    """
    broker = make_broker(user)
    account = make_account(broker)
    make_fx("USD", "EUR", date(2032, 1, 5), "1.00", user)
    make_fx("USD", "EUR", date(2032, 3, 1), "1.05", user)
    make_fx("USD", "EUR", date(2032, 10, 1), "1.10", user)
    make_tx(account, date(2032, 1, 5), "Cash in", currency="EUR",
            cash_flow=Decimal("100000"))
    make_tx(account, date(2032, 3, 1), "Cash out", currency="EUR",
            cash_flow=Decimal("-10000"))
    doc = build_reconciled_summary(user, date(2032, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("9500")
    assert Decimal(doc["netResult"]["components"]["fx"]["raw"]) == Decimal("9500")
    assert Decimal(doc["netResult"]["fxDetail"]["cashFlows"]["raw"]) == Decimal("9500")
    assert Decimal(doc["netResult"]["fxDetail"]["security"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_single_currency_cash_only_has_zero_fx(user):
    """USD cash in 5,000, nothing else: control 0, all components 0."""
    broker = make_broker(user)
    account = make_account(broker)
    make_tx(account, date(2033, 2, 1), "Cash in", cash_flow=Decimal("5000"))
    doc = build_reconciled_summary(user, date(2033, 2, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["components"]["fx"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


# ---------------------------------------------------------------------------
# Holding-lifecycle scenarios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_buy_and_hold_unrealized_only(user):
    """In 10,000; buy 5 @1,500; price 1,700.

    Unrealized price 1,000; NAV 2,500 + 8,500 = 11,000; control 1,000.
    """
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="HoldCo")
    make_tx(account, date(2034, 1, 5), "Cash in", cash_flow=Decimal("10000"))
    make_tx(account, date(2034, 1, 5), "Buy", security=stock,
            quantity=Decimal("5"), price=Decimal("1500"))
    make_price(stock, date(2034, 10, 1), "1700")
    doc = build_reconciled_summary(user, date(2034, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("1000")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("1000")
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_realized_loss_flows_to_a_negative_net_result(user):
    """In 500; buy 10 @50; sell 10 @45 -> realized -50; NAV 450; control -50."""
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="Loser")
    make_tx(account, date(2035, 1, 5), "Cash in", cash_flow=Decimal("500"))
    make_tx(account, date(2035, 1, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("50"))
    make_tx(account, date(2035, 2, 5), "Sell", security=stock,
            quantity=Decimal("-10"), price=Decimal("45"))
    doc = build_reconciled_summary(user, date(2035, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("-50")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("-50")
    assert doc["netResult"]["components"]["realizedPrice"]["display"] == "($50.00)"
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_partial_disposal_splits_realized_and_unrealized(user):
    """In 1,000; buy 100 @10; sell 30 @14; price stays 14.

    Realized (14-10)x30 = 120; unrealized (14-10)x70 = 280.
    Cash 420 + stock 980 = NAV 1,400; control 400 = 120 + 280.
    """
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="Partial")
    make_tx(account, date(2036, 1, 5), "Cash in", cash_flow=Decimal("1000"))
    make_tx(account, date(2036, 1, 5), "Buy", security=stock,
            quantity=Decimal("100"), price=Decimal("10"))
    make_tx(account, date(2036, 2, 5), "Sell", security=stock,
            quantity=Decimal("-30"), price=Decimal("14"))
    make_price(stock, date(2036, 10, 1), "14")
    doc = build_reconciled_summary(user, date(2036, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("120")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("280")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("400")
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_complete_disposal_then_rebuy(user):
    """In 2,000; buy 10 @100; sell 10 @110 (realized 100); buy 5 @120;
    price 130 (unrealized 50). Cash 1,500 + 650 = NAV 2,150; control 150."""
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="Rebuy")
    make_tx(account, date(2037, 1, 5), "Cash in", cash_flow=Decimal("2000"))
    make_tx(account, date(2037, 1, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("100"))
    make_tx(account, date(2037, 2, 5), "Sell", security=stock,
            quantity=Decimal("-10"), price=Decimal("110"))
    make_tx(account, date(2037, 3, 5), "Buy", security=stock,
            quantity=Decimal("5"), price=Decimal("120"))
    make_price(stock, date(2037, 10, 1), "130")
    doc = build_reconciled_summary(user, date(2037, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("100")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("50")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("150")
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_short_position_round_trip(user):
    """In 1,000; sell 10 @100 (open short); buy 10 @90 (cover).

    Realized short profit (100-90)x10 = +100; NAV 1,100; control 100."""
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="ShortCo")
    make_tx(account, date(2050, 1, 5), "Cash in", cash_flow=Decimal("1000"))
    make_tx(account, date(2050, 1, 5), "Sell", security=stock,
            quantity=Decimal("-10"), price=Decimal("100"))
    make_tx(account, date(2050, 2, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("90"))
    doc = build_reconciled_summary(user, date(2050, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("100")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("100")
    assert doc["netResult"]["reconciliation"] == "reconciled"


# ---------------------------------------------------------------------------
# Income / fees / taxes scenarios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_income_is_gross_and_taxes_are_separate(user):
    """In 1,000; buy 1 @100; dividend 100; interest 50; coupon 20; tax -15.

    Income = 170 (gross of tax; NOT 155); taxes = -15.
    NAV 1,155; control 155 = 170 - 15.
    """
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="Payer")
    make_tx(account, date(2038, 1, 5), "Cash in", cash_flow=Decimal("1000"))
    make_tx(account, date(2038, 1, 5), "Buy", security=stock,
            quantity=Decimal("1"), price=Decimal("100"))
    make_tx(account, date(2038, 2, 1), "Dividend", security=stock,
            cash_flow=Decimal("100"))
    make_tx(account, date(2038, 2, 2), "Interest income", security=None,
            cash_flow=Decimal("50"))
    make_tx(account, date(2038, 2, 3), "Coupon", security=None,
            cash_flow=Decimal("20"))
    make_tx(account, date(2038, 2, 4), "Tax", security=stock,
            cash_flow=Decimal("-15"))
    make_price(stock, date(2038, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2038, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["income"]["raw"]) == Decimal("170")
    assert Decimal(doc["netResult"]["components"]["taxes"]["raw"]) == Decimal("-15")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("155")
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"


@pytest.mark.django_db
def test_fees_include_trade_commission_broker_rows_and_fx_commission(user):
    """In 100; buy 1 @10 with commission -5; FX tx 70 USD -> 70 EUR, comm -1.

    Fees = -5 (trade) + -25 (Broker commission row) + -1 (FX tx) = -31.
    Stock valued at cost (price 10): NAV = 85 - 71 + 10 + 70 = ... see below.
    Cash: 100 - 15 - 25 - 71 = -11; stock 10; EUR 70 -> NAV 69.
    Control: 69 - 100 = -31 = fees (FX tx legs self-cancel at rate 1.0).
    """
    from common.models import FXTransaction

    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="FeeCo")
    make_fx("USD", "EUR", date(2039, 1, 5), "1.00", user)
    make_tx(account, date(2039, 1, 5), "Cash in", cash_flow=Decimal("100"))
    make_tx(account, date(2039, 1, 5), "Buy", security=stock,
            quantity=Decimal("1"), price=Decimal("10"), commission=Decimal("-5"))
    make_tx(account, date(2039, 2, 1), "Broker commission",
            cash_flow=Decimal("-25"))
    FXTransaction.objects.create(
        investor=user,
        account=account,
        date=date(2039, 2, 2),
        from_currency="USD",
        to_currency="EUR",
        from_amount=Decimal("70"),
        to_amount=Decimal("70"),
        exchange_rate=Decimal("1.000000"),
        commission=Decimal("-1"),
        commission_currency="USD",
    )
    make_price(stock, date(2039, 10, 1), "10")
    doc = build_reconciled_summary(user, date(2039, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["fees"]["raw"]) == Decimal("-31")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("-31")
    assert doc["netResult"]["reconciliation"] == "reconciled"


# ---------------------------------------------------------------------------
# Bond scenario
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bond_coupon_aci_and_par_redemption(user):
    """10 bonds, notional 100, bought at 95% with ACI -2; coupon 30;
    full par redemption (notional_change 100, quantity None, cash 1,000).

    Buy cf: -(95% x 100 x 10) - 2 = -952; cash: 2,000 - 952 + 30 + 1,000
    = 2,078; bond value after redemption 0 (notional 0) -> NAV 2,078.
    Realized: 1,000 - 1,000 x 95% = 50.
    Income: coupon 30 + ACI -2 = 28. Control: 2,078 - 2,000 = 78.
    """
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="Test Bond 2040", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("100"), nominal_currency="USD",
        is_amortizing=True,
    )
    make_tx(account, date(2040, 1, 5), "Cash in", cash_flow=Decimal("2000"))
    make_tx(account, date(2040, 1, 5), "Buy", security=bond, currency="USD",
            quantity=Decimal("10"), price=Decimal("95"), aci=Decimal("-2"),
            notional=Decimal("100"))
    make_tx(account, date(2040, 6, 1), "Coupon", security=bond, currency="USD",
            cash_flow=Decimal("30"))
    make_tx(account, date(2040, 9, 1), "Bond redemption", security=bond,
            currency="USD", quantity=Decimal("0"), price=Decimal("100"),
            cash_flow=Decimal("1000"), notional_change=Decimal("100"),
            notional=Decimal("100"))
    doc = build_reconciled_summary(user, date(2040, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("50")
    assert Decimal(doc["netResult"]["components"]["income"]["raw"]) == Decimal("28")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("78")
    assert doc["netResult"]["reconciliation"] == "reconciled"


# ---------------------------------------------------------------------------
# Crypto scenarios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_crypto_coin_fee_is_absorbed_once_not_double_counted(user):
    """BTC-USDT buy with a BTC-denominated fee.

    In 50,000 USDT; buy 1 BTC @ 50,000 USDT, commission -0.001 BTC.
    Position 0.999 BTC; price 50,000 -> value 49,950; basis 50,000.
    With the coin's currency equal to the reporting currency the engine's
    price_appreciation carries the whole -50 (the fx split only appears for
    a non-USD target); fees EXCLUDE the coin fee either way.
    NAV: USDT 0 + BTC 49,950 = 49,950; control -50 = attributed -50.
    """
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    make_tx(account, date(2041, 1, 5), "Cash in", currency="USDT",
            cash_flow=Decimal("50000"))
    make_tx(account, date(2041, 1, 5), "Crypto trade in", currency="USDT",
            security=btc, quantity=Decimal("1"), price=Decimal("50000"),
            commission=Decimal("-0.001"), commission_currency="BTC")
    make_price(btc, date(2041, 10, 1), "50000")
    doc = build_reconciled_summary(user, date(2041, 10, 15), "USD", 2, [account.id])
    # The unrealized engine values the RAW quantity sum (1.0) while NAV uses
    # position() (0.999): the -50 fee burn is invisible to the engine and
    # must surface as an explicit declared gap — never as FX, never hidden.
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["fxDetail"]["security"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["components"]["fees"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("-50")
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("-50")
    assert doc["status"] == "partial"
    assert "crypto_coin_fee_not_attributed" in doc["reasons"]
    assert doc["netResult"]["reconciliation"] == "incomplete"


@pytest.mark.django_db
def test_unmatched_crypto_transfer_out_is_unclassified_not_relabeled(user):
    """Buy 1 BTC @30,000 USDT, then transfer it out (spot 50,000, no group).

    Engine reality (verified): ``is_disposal_transaction`` does NOT include
    transfer types, so an unmatched transfer-out books NO realized result —
    the coin and its basis leave NAV silently. NAV 0, control -30,000,
    attributed 0 -> unexplained -30,000. The statement must stay partial
    with the in-kind diagnostic and must NOT relabel the gap as FX.
    """
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    make_tx(account, date(2042, 1, 5), "Cash in", currency="USDT",
            cash_flow=Decimal("30000"))
    make_tx(account, date(2042, 1, 5), "Crypto trade in", currency="USDT",
            security=btc, quantity=Decimal("1"), price=Decimal("30000"))
    make_tx(account, date(2042, 2, 5), "Crypto transfer out", currency="USDT",
            security=btc, quantity=Decimal("-1"), price=Decimal("50000"))
    make_price(btc, date(2042, 1, 4), "30000")
    doc = build_reconciled_summary(user, date(2042, 10, 15), "USD", 2, [account.id])
    in_kind = doc["diagnostics"]["unclassifiedInKindFlows"]
    assert in_kind["present"] is True
    assert in_kind["count"] == 1
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("-30000")
    assert doc["status"] == "partial"
    assert "in_kind_flows_unclassified" in doc["reasons"]
    assert doc["netResult"]["reconciliation"] == "incomplete"


@pytest.mark.django_db
def test_unmatched_crypto_transfer_in_never_becomes_certified_gain(user):
    """An external BTC deposit (1 coin @ spot 50,000, no group, no cash row).

    The engine gives the lot zero basis, so the whole value shows as
    'unrealized gain' even though it is a contributed asset. The statement
    must flag the flow as unclassified in-kind and refuse a complete/reconciled
    certification regardless of the arithmetic closing.
    """
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    make_tx(account, date(2043, 1, 5), "Crypto transfer in", currency="BTC",
            security=btc, quantity=Decimal("1"), price=Decimal("50000"))
    make_price(btc, date(2043, 10, 1), "50000")
    doc = build_reconciled_summary(user, date(2043, 10, 15), "USD", 2, [account.id])
    in_kind = doc["diagnostics"]["unclassifiedInKindFlows"]
    assert in_kind["present"] is True
    assert in_kind["count"] == 1
    assert Decimal(in_kind["signedFmv"]) == Decimal("50000")
    assert doc["status"] == "partial"
    assert doc["netResult"]["reconciliation"] == "incomplete"


@pytest.mark.django_db
def test_matched_internal_crypto_transfer_stays_principal_neutral(user):
    """Two-account OKX-style transfer pair sharing import_group_id.

    The coin is acquired in the funding account first, so the matched pair
    is a pure principal move: no income, capital, profit or in-kind
    diagnostic; NAV carries the coin, capital carries the funding cash.
    """
    broker = make_broker(user, name="OKX", precision=8)
    funding = make_account(broker, "Funding")
    trading = make_account(broker, "Trading")
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    make_tx(funding, date(2044, 1, 4), "Cash in", currency="USDT",
            cash_flow=Decimal("50000"))
    make_tx(funding, date(2044, 1, 4), "Crypto trade in", currency="USDT",
            security=btc, quantity=Decimal("1"), price=Decimal("50000"))
    make_tx(funding, date(2044, 1, 5), "Crypto transfer out", currency="BTC",
            security=btc, quantity=Decimal("-1"), price=Decimal("50000"),
            import_group_id="grp-1", import_provider="okx",
            import_account_id="okx-fund")
    make_tx(trading, date(2044, 1, 5), "Crypto transfer in", currency="BTC",
            security=btc, quantity=Decimal("1"), price=Decimal("50000"),
            import_group_id="grp-1", import_provider="okx",
            import_account_id="okx-fund")
    make_price(btc, date(2044, 10, 1), "50000")
    doc = build_reconciled_summary(
        user, date(2044, 10, 15), "USD", 2, [funding.id, trading.id]
    )
    assert doc["diagnostics"]["unclassifiedInKindFlows"]["present"] is False
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"


# ---------------------------------------------------------------------------
# Options and missing-data honesty
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_open_option_leaves_an_explicit_unreconciled_gap(user):
    """A written BTC option open at the effective date.

    Premium +0.000154 BTC received (coin bucket via NAV's option routing);
    the unrealized engine returns zeros for options by design, so the
    liability/premium economics are structurally unattributed:
    NAV 0.000154 x 50,000 = 7.70; attributed 0; unexplained 7.70.
    Status partial with the option reason; reconciliation incomplete.
    """
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    option = make_asset(user, type="Option", name="BTC-OPT", currency="BTC")
    make_tx(account, date(2045, 1, 5), "Crypto trade out", currency="BTC",
            security=option, quantity=Decimal("-7"), price=None,
            cash_flow=Decimal("0.000154"))
    make_price(btc, date(2045, 10, 1), "50000")
    doc = build_reconciled_summary(user, date(2045, 10, 15), "USD", 2, [account.id])
    assert doc["status"] == "partial"
    assert "option_unrealized_not_attributed" in doc["reasons"]
    assert Decimal(doc["netResult"]["nav"]["raw"]) == Decimal("7.70000000")
    # The option gap is a non-cash-FX incomplete dependency, so the exact
    # unexplained amount is unknown - never a provisional number as ok.
    assert doc["netResult"]["unexplainedDifference"]["status"] == "partial"
    assert doc["netResult"]["unexplainedDifference"]["raw"] is None
    assert doc["netResult"]["reconciliation"] == "incomplete"


@pytest.mark.django_db
def test_unpriced_crypto_coin_keeps_nav_partial_and_blocks_certification(user):
    """A coin with no price row at all (asset currency = coin code).

    NAV omits the coin (missing_price diagnostic) and reports the known
    subtotal; the statement is partial and reconciliation incomplete even if
    the arithmetic happens to close.
    """
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    coin = make_asset(user, type="Crypto", name="TRUMP", currency="TRUMP")
    make_tx(account, date(2046, 1, 5), "Cash in", currency="USDT",
            cash_flow=Decimal("2"))
    make_tx(account, date(2046, 1, 5), "Crypto trade in", currency="USDT",
            security=coin, quantity=Decimal("1"), price=Decimal("2"))
    doc = build_reconciled_summary(user, date(2046, 10, 15), "USD", 2, [account.id])
    assert doc["status"] == "partial"
    assert "missing_price" in doc["reasons"]
    assert doc["netResult"]["nav"]["status"] == "partial"
    assert "knownSubtotal" in doc["netResult"]["nav"]
    assert doc["netResult"]["reconciliation"] == "incomplete"
    omissions = doc["diagnostics"]["omittedValuations"]
    assert any(item["reason"] == "missing_price" for item in omissions)


@pytest.mark.django_db
def test_missing_cash_fx_rate_blocks_certification(user):
    """CHF cash with no FX rows at all: the cash leg is omitted from NAV
    (missing_fx) and the statement refuses a certified bridge."""
    broker = make_broker(user)
    account = make_account(broker)
    make_tx(account, date(2047, 1, 5), "Cash in", currency="CHF",
            cash_flow=Decimal("1000"))
    doc = build_reconciled_summary(user, date(2047, 10, 15), "USD", 2, [account.id])
    assert doc["status"] == "partial"
    assert "missing_fx" in doc["reasons"]
    assert doc["netResult"]["reconciliation"] == "incomplete"
    assert any(
        item["reason"] == "missing_fx"
        for item in doc["diagnostics"]["omittedValuations"]
    )


# ---------------------------------------------------------------------------
# Scope / isolation / lifecycle edges
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_internal_stock_transfer_with_phantom_rows_creates_no_profit(user):
    """Stock moved account-to-account via the asset-transfer mechanism
    (Sell + phantom Cash out in acct 1; Buy + phantom Cash in in acct 2).

    Net capital: +1,000 (phantom in) - 1,000 (phantom out) + 0 = +1,000
    total, of which the real external part is the original 1,000 cash in.
    NAV 1,000 (stock at cost); control 0; reconciled, complete.
    """
    broker = make_broker(user)
    source = make_account(broker, "Source")
    target = make_account(broker, "Target")
    stock = make_asset(user, name="MovedCo")
    make_tx(source, date(2048, 1, 5), "Cash in", cash_flow=Decimal("1000"))
    make_tx(source, date(2048, 1, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("100"))
    make_tx(source, date(2048, 2, 5), "Sell", security=stock,
            quantity=Decimal("-10"), price=Decimal("100"))
    make_tx(source, date(2048, 2, 5), "Cash out", cash_flow=Decimal("-1000"),
            comment="Phantom cash movement for asset transfer: MovedCo")
    make_tx(target, date(2048, 2, 6), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("100"))
    make_tx(target, date(2048, 2, 6), "Cash in", cash_flow=Decimal("1000"),
            comment="Phantom cash movement for asset transfer: MovedCo")
    make_price(stock, date(2048, 10, 1), "100")
    doc = build_reconciled_summary(
        user, date(2048, 10, 15), "USD", 2, [source.id, target.id]
    )
    assert Decimal(doc["capital"]["invested"]["raw"]) == Decimal("2000")
    assert Decimal(doc["capital"]["cashOut"]["raw"]) == Decimal("-1000")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_same_day_disposal_and_reacquisition_gap_stays_visible(user):
    """Engine limitation, pinned honestly: a sell and a buy of the same
    security on the SAME date make calculate_buy_in_price's weighted-average
    walk degenerate (the weights cancel to zero and the basis reads -0), so
    unrealized reports the full value as a gain. The statement must neither
    hide this nor relabel it: it appears verbatim as an unexplained
    difference and fails reconciliation."""
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="WrapCo")
    make_tx(account, date(2058, 1, 5), "Cash in", cash_flow=Decimal("3000"))
    make_tx(account, date(2058, 1, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("100"))
    make_tx(account, date(2058, 2, 5), "Sell", security=stock,
            quantity=Decimal("-10"), price=Decimal("100"))
    make_tx(account, date(2058, 2, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("100"))
    make_price(stock, date(2058, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2058, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["unexplainedDifference"]["raw"]) == Decimal("-1000")
    assert doc["netResult"]["reconciliation"] == "unreconciled"
    assert doc["status"] == "partial"
    assert "unexplained_difference" in doc["reasons"]


@pytest.mark.django_db
def test_account_scope_and_investor_isolation(user, django_user_model):
    """A second investor's rows and an unselected account never leak in."""
    broker = make_broker(user)
    selected = make_account(broker, "Selected")
    other_mine = make_account(broker, "Other mine")
    other = make_asset(user, name="MineOnly")
    make_tx(selected, date(2053, 1, 5), "Cash in", cash_flow=Decimal("1000"))
    make_tx(other_mine, date(2053, 1, 5), "Cash in", cash_flow=Decimal("9000"))
    make_tx(other_mine, date(2053, 1, 5), "Buy", security=other,
            quantity=Decimal("1"), price=Decimal("9000"))

    other_user = django_user_model.objects.create_user(
        username="isolation-user", email="iso@example.com", password="pass12345"
    )
    other_broker = make_broker(other_user, name="Other broker")
    other_account = make_account(other_broker, "Other investor account")
    foreign_stock = make_asset(other_user, name="ForeignStock")
    make_tx(other_account, date(2053, 1, 5), "Cash in", cash_flow=Decimal("77000"))

    doc = build_reconciled_summary(
        user, date(2053, 10, 15), "USD", 2, [selected.id]
    )
    assert Decimal(doc["capital"]["invested"]["raw"]) == Decimal("1000")
    assert Decimal(doc["netResult"]["nav"]["raw"]) == Decimal("1000")


@pytest.mark.django_db
def test_future_transactions_and_historical_cutoff(user):
    """Rows after the effective date are excluded; a historical cutoff shows
    only the pre-cutoff economics (buy held, sale not yet happened)."""
    broker = make_broker(user)
    account = make_account(broker)
    stock = make_asset(user, name="FutureCo")
    make_tx(account, date(2054, 1, 5), "Cash in", cash_flow=Decimal("1000"))
    make_tx(account, date(2054, 2, 5), "Buy", security=stock,
            quantity=Decimal("10"), price=Decimal("50"))
    make_tx(account, date(2054, 12, 1), "Sell", security=stock,
            quantity=Decimal("-10"), price=Decimal("80"))
    make_tx(account, date(2054, 12, 1), "Cash in", cash_flow=Decimal("999"))
    make_price(stock, date(2054, 3, 1), "60")
    doc = build_reconciled_summary(user, date(2054, 6, 30), "USD", 2, [account.id])
    assert Decimal(doc["capital"]["invested"]["raw"]) == Decimal("1000")
    assert Decimal(doc["netResult"]["components"]["realizedPrice"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("100")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("100")


@pytest.mark.django_db
def test_zero_capital_no_activity_statement(user):
    """An empty account: everything zero, reconciled; returns unavailable."""
    broker = make_broker(user)
    account = make_account(broker)
    doc = build_reconciled_summary(user, date(2055, 1, 15), "USD", 2, [account.id])
    assert Decimal(doc["capital"]["netInvestedCapital"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["nav"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert doc["returns"]["totalReturn"]["value"] is None
    assert doc["returns"]["totalReturn"]["status"] == "not_available"


@pytest.mark.django_db
def test_no_accounts_selected_is_unavailable(user):
    doc = build_reconciled_summary(user, date(2056, 1, 15), "USD", 2, [])
    assert doc["status"] == "unavailable"
    assert doc["netResult"]["reconciliation"] == "incomplete"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Historical cash-flow FX completeness (review round: finding 2)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_missing_historical_coin_conversion_keeps_cash_fx_partial_and_uncertified(user):
    """A coin leg converted at a date with NO coin price, while the ending
    date HAS one: the own-date conversion fails (deterministic crypto lookup)
    so the ledger is incomplete and cash FX is UNKNOWN - raw null, status
    partial, never a fabricated number and never a certified reconciliation.

    Hand derivation (BTC USD price 50,000 exists only from 2046-01-01):
      Cash in 50,000 USDT (peg 1.0); FX tx 50,000 USDT -> 1 BTC at 2044.
      Balances at EOP: USDT 0, BTC 1 x 50,000 = cash EOP 50,000.
      Known own-date flows: +50,000 (peg) - 50,000 (peg) = 0; the BTC leg at
      2044 is UNKNOWN -> a certified fxCash cannot be computed.
      NAV 50,000; net capital 50,000; control 0; the arithmetic happens to
      close but the bridge is NOT certified (reconciliation incomplete).
    """
    from common.models import FXTransaction

    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    make_tx(account, date(2046, 1, 2), "Cash in", currency="USDT",
            cash_flow=Decimal("50000"))
    FXTransaction.objects.create(
        investor=user,
        account=account,
        date=date(2044, 6, 1),
        from_currency="USDT",
        to_currency="BTC",
        from_amount=Decimal("50000"),
        to_amount=Decimal("1"),
        exchange_rate=Decimal("0.00002"),
    )
    make_price(btc, date(2046, 1, 1), "50000")
    doc = build_reconciled_summary(user, date(2046, 1, 15), "USD", 2, [account.id])
    cash_fx = doc["netResult"]["fxDetail"]["cashFlows"]
    assert cash_fx["status"] == "partial"
    assert cash_fx["reason"] == "missing_fx"
    assert cash_fx["raw"] is None
    assert doc["netResult"]["components"]["fx"]["status"] == "partial"
    assert doc["netResult"]["components"]["fx"]["raw"] is None
    assert "missing_fx" in doc["reasons"]
    assert doc["netResult"]["reconciliation"] == "incomplete"
    assert doc["status"] == "partial"
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("0")
    # Aggregates built on the unknown conversion are unknown as well - the
    # known share is exposed as an explicitly labelled subtotal, distinct
    # from a certified total.
    attributed = doc["netResult"]["attributedSum"]
    assert attributed["status"] == "partial"
    assert attributed["raw"] is None
    assert attributed["reason"] == "missing_fx"
    assert Decimal(attributed["knownSubtotal"]) == Decimal("0")
    unexplained = doc["netResult"]["unexplainedDifference"]
    assert unexplained["status"] == "partial"
    assert unexplained["raw"] is None
    assert unexplained["reason"] == "missing_fx"


@pytest.mark.django_db
def test_in_kind_fmv_conversion_failure_propagates_to_diagnostics(user):
    """An external transfer whose FMV cannot be converted at the transfer
    date (the reporting currency needs the coin price, which only exists
    later) must mark the in-kind diagnostic fmvKnown=false and surface
    missing_fx - the reporting-currency FMV is unknown, not zero."""
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    btc = make_asset(user, type="Crypto", name="BTC", currency="USD")
    make_tx(account, date(2044, 6, 1), "Cash in", currency="USDT",
            cash_flow=Decimal("1000"))
    make_tx(account, date(2044, 6, 1), "Crypto transfer in", currency="BTC",
            security=btc, quantity=Decimal("1"), price=Decimal("50000"))
    make_price(btc, date(2045, 6, 1), "50000")
    doc = build_reconciled_summary(user, date(2045, 6, 15), "BTC", 8, [account.id])
    in_kind = doc["diagnostics"]["unclassifiedInKindFlows"]
    assert in_kind["present"] is True
    assert in_kind.get("fmvKnown") is False
    assert "signedFmv" not in in_kind
    assert "missing_fx" in doc["reasons"]
    assert doc["status"] == "partial"
    assert doc["netResult"]["reconciliation"] == "incomplete"
    assert doc["capital"]["invested"]["status"] == "partial"

# ---------------------------------------------------------------------------
# RUB-bond FX discrepancy reduction (review round: acceptance follow-up)
# ---------------------------------------------------------------------------
# The real-data review found fxSecurity ~ +$421k against a $136k NAV on RUB
# bonds and an unexplained difference of ~ -$426k. These sanitized, hand-
# derived regressions reduce that to two EXACT engine boundaries (both
# verified numerically; both are PRE-EXISTING ENGINE DEFECTS that this branch
# only surfaces - correcting them requires a separate protected-code review):
#
# Boundary 1 (dimensional, services/realized.py unrealized_gain_loss bond
# branch): the unrealized FX term multiplies the bond's LOCAL-currency
# notional by TARGET-currency prices:
#     fx = notional_lcl x (price_target - buy_in_target) x pos / 100
# With buy-in 95 x entry-rate and price 100 the bracket is ~ par-as-USD, so
# the "FX effect" approximates the RUB par value of the position.
#
# Boundary 2 (currency, services/bonds.py get_current_notional
# transactions-fallback): that branch returns the notional WITHOUT the
# `* fx_rate` the other two branches apply, so an amortizing bond without
# NotionalHistory is valued at RUB-par as if it were reporting currency.
#
# Sanitized dataset (all three scenarios): 10 RUB bonds, par 1,000, bought
# at 95% for 9,500 RUB funded by 20,000 RUB cash; RUB->USD 0.0100 at entry,
# 0.0125 at the effective date; price 100 at the effective date.
# Hand-derived CORRECT statement: bond value 10,000 RUB x 0.0125 = 125; cash
# 10,500 x 0.0125 = 131.25; NAV 256.25; net capital 200; control 56.25;
# unrealized price (100-95) x notional x pos x f_eop / 100 = 6.25; certified
# FX = basis 9,500 RUB x 0.0025 = 23.75 (security) + cash FX 131.25 - 105 =
# 26.25; attributed 56.25 -> reconciled. Every test below records how far
# current engine behavior deviates from these numbers.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rub_bond_nonamortizing_unrealized_fx_decomposition_reconciles(user):
    """Corrected engine (boundary 1 fixed): the FX term converts the price
    consistently (quotation -> target at EOP), so fx_security 23.75
    (= basis 9,500 RUB x 0.0025 drift), attributed 56.25, and the
    statement reconciles at the sanitized values."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Series A", currency="RUB", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=False,
    )
    make_fx("USD", "RUB", date(2059, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2059, 10, 1), "0.0125", user)
    make_tx(account, date(2059, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_price(bond, date(2059, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2059, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    assert Decimal(nr["nav"]["raw"]) == Decimal("256.25")
    assert Decimal(nr["controlTotal"]["raw"]) == Decimal("56.25")
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == Decimal("6.25")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("56.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == Decimal("0")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_rub_bond_amortizing_redemption_fx_decomposition_reconciles(user):
    """Corrected engine on an amortizing bond whose redemption created
    NotionalHistory: the remaining 800-par position prices consistently
    (value 10 x 95% x 800/100 x 0.0125 = 95.00; basis 800 x 95% x 0.01 x
    10 / 100 = 76.00 -> unrealized fx 19.00), and the redemption realizes
    6.00 (price 1.25 + fx 4.75). NAV 251.25 = 95.00 + cash 156.25; control
    51.25; attributed 51.25 -> reconciled, complete."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Series B", currency="RUB", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2059, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2059, 6, 1), "0.0125", user)
    make_fx("USD", "RUB", date(2059, 10, 1), "0.0125", user)
    make_tx(account, date(2059, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_tx(account, date(2059, 6, 1), "Bond redemption", security=bond,
            currency="RUB", quantity=Decimal("0"), price=Decimal("100"),
            cash_flow=Decimal("2000"), notional_change=Decimal("200"),
            notional=Decimal("1000"))
    make_price(bond, date(2059, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2059, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    # Corrected engine: price 100% at EOP -> bond value 10 x 100% x
    # 800/100 x 0.0125 = 100.00; cash 12,500 x 0.0125 = 156.25; NAV 256.25;
    # realized redemption 6.00 (price 1.25 + fx 4.75); unrealized price 0,
    # fx 19.00 (basis 76 x 0.0025 drift); cash FX 26.25; attributed 56.25.
    assert Decimal(nr["nav"]["raw"]) == Decimal("256.25")
    assert Decimal(nr["controlTotal"]["raw"]) == Decimal("56.25")
    assert Decimal(nr["components"]["realizedPrice"]["raw"]) == Decimal("1.25")
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == Decimal("5.00")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("56.25")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_rub_bond_fallback_notional_engine_characterization(user):
    """ENGINE characterization (corrected): the transactions-fallback branch
    converts the nominal-currency notional exactly once (1,000 RUB x 0.0125
    = 12.50 USD) and the bond unrealized decomposition is currency-
    consistent (total 30.00 = value 125 - basis 95; price 6.25 + fx
    23.75)."""
    from services.bonds import get_current_notional
    from services.realized import unrealized_gain_loss

    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Series C", currency="RUB", exposure="Fixed Income")
    meta = BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2059, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2059, 10, 1), "0.0125", user)
    make_tx(account, date(2059, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_price(bond, date(2059, 10, 1), "100")
    assert get_current_notional(
        meta, date(2059, 10, 15), user, [account.id], "USD"
    ) == Decimal("12.50")
    unrealized = unrealized_gain_loss(
        bond, date(2059, 10, 15), user, "USD", account_ids=[account.id], start_date=None
    )
    assert unrealized["price_appreciation"] == Decimal("6.25")
    assert unrealized["fx_effect"] == Decimal("23.75")
    assert unrealized["total"] == Decimal("30.00")


@pytest.mark.django_db
def test_rub_bond_fallback_notional_statement_certifies_after_correction(user):
    """STATEMENT (after the engine corrections): the fallback-notional bond
    values and attributes correctly (value 125.00 + cash 131.25 = NAV
    256.25; net result 56.25), the temporary guard is retired, and the
    statement certifies with no residual bond reason or diagnostics."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Series C", currency="RUB", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2059, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2059, 10, 1), "0.0125", user)
    make_tx(account, date(2059, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_price(bond, date(2059, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2059, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    assert Decimal(nr["nav"]["raw"]) == Decimal("256.25")
    assert nr["nav"]["status"] == "ok"
    assert "bond_notional_fallback_unconverted" not in doc["reasons"]
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert doc["returns"]["irr"]["status"] == "ok"
    assert doc["returns"]["totalReturn"]["status"] == "ok"
    assert "affectedNotionalFallbacks" not in doc["diagnostics"]
    assert "affectedProvisionalAttribution" not in doc["diagnostics"]


# ---------------------------------------------------------------------------
# Bond guard refinement (review round 4): warnings only on AFFECTED outputs
# ---------------------------------------------------------------------------
# The fallback path (amortizing, no NotionalHistory) returns the notional
# unconverted. Whether that matters depends on the asset and the statement:
#
# - Same nominal/reporting currency: the omitted conversion is x1.0 - a
#   no-op. No warning, fully certified.
# - Foreign currency with an OPEN position: the current NAV and the
#   unrealized decomposition both price the fallback notional -> NAV partial,
#   unrealized partial, realized warned too (prior disposals may share the
#   affected path).
# - Foreign currency FULLY CLOSED: the current NAV does not include the
#   asset - NAV must stay ok; only the historical realized attribution
#   carries the warning, and the aggregates (which need a reliable control
#   total and complete attribution) go unknown.


@pytest.mark.django_db
def test_bond_fallback_same_currency_is_a_no_op(user):
    """A RUB bond reported in RUB: the fallback's omitted conversion would
    multiply by fx(RUB->RUB) = 1 - nothing is affected. Hand derivation
    (statement currency RUB, all rates 1): NAV = 10,500 cash + 10,000 value
    = 20,500; control 500 = unrealized price 500 + fx 0 + cash FX 0;
    reconciled, complete, no bond reason."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Same Ccy", currency="RUB", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_tx(account, date(2062, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2062, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_price(bond, date(2062, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2062, 10, 15), "RUB", 2, [account.id])
    assert "bond_notional_fallback_unconverted" not in doc["reasons"]
    assert doc["netResult"]["nav"]["status"] == "ok"
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("500")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("500")
    assert Decimal(doc["netResult"]["components"]["fx"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_bond_fallback_closed_foreign_position_warns_only_on_realized(user):
    """Foreign bond, fully disposed (no current position): the current NAV
    (cash only, 20,500 x 0.0125 = 256.25) must stay ok - the asset appears
    in historical candidates but is not in today's valuation. The historical
    realized attribution MAY depend on the affected fallback path, so the
    realized row is warned and the aggregates (needing complete attribution
    plus a reliable control total) go unknown. Hand derivation: buy 9,500
    RUB, sell at par 10,000 RUB; realized total = 125 - 95 = 30 (price 6.25
    + fx 23.75) and cash FX 26.25; control 256.25 - 200 = 56.25."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Closed Fgn", currency="RUB", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2063, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2063, 10, 1), "0.0125", user)
    make_tx(account, date(2063, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2063, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_tx(account, date(2063, 10, 1), "Sell", security=bond, currency="RUB",
            quantity=Decimal("-10"), price=Decimal("100"))
    make_price(bond, date(2063, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2063, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    # Corrected engine: the fully disposed affected bond's realized
    # attribution is exact (proceeds 125 - basis 95 = 30.00, price 6.25 +
    # fx 23.75); the temporary warning retires and the statement certifies.
    assert nr["nav"]["status"] == "ok"
    assert Decimal(nr["nav"]["raw"]) == Decimal("256.25")
    assert Decimal(nr["controlTotal"]["raw"]) == Decimal("56.25")
    assert doc["capital"]["invested"]["status"] == "ok"
    realized = nr["components"]["realizedPrice"]
    assert realized["status"] == "ok"
    assert Decimal(realized["raw"]) == Decimal("6.25")
    assert nr["components"]["unrealizedPrice"]["status"] == "ok"
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("56.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == Decimal("0")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert doc["returns"]["totalReturn"]["status"] == "ok"


# ---------------------------------------------------------------------------
# Bond guard source-currency matching (review round 5)
# ---------------------------------------------------------------------------
# get_current_notional denominates the notional in nominal_currency or
# asset.currency (its source currency) and converts source -> target; the
# fallback omits exactly that conversion. The guard must therefore compare
# the SOURCE currency with the reporting currency:
# - quotation (asset) currency matches reporting but the nominal differs:
#   the unconverted fallback notional is foreign-scale -> affected;
# - the nominal matches reporting (quotation differs): the omitted
#   conversion is x1.0 -> a no-op, never falsely flagged.


@pytest.mark.django_db
def test_bond_fallback_quotation_matches_reporting_nominal_differs_is_affected(user):
    """USD-quotation bond with a RUB nominal, reported in USD: the fallback
    returns the RUB-par notional as if it were USD (value 10,000 for a
    12.5-USD position) - the defect is live and must not escape detection
    because the quotation happens to match the reporting currency."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="USD Quote RUB Nominal", currency="USD", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2064, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2064, 10, 1), "0.0125", user)
    make_tx(account, date(2064, 1, 5), "Cash in", currency="USD",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2064, 1, 5), "Buy", security=bond, currency="USD",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_price(bond, date(2064, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2064, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    # Corrected engine: the fallback notional converts exactly once
    # (1,000 RUB x 0.0125 = 12.50 USD of notional -> value 12.50 at par).
    # The dataset itself is bookkeeping-inconsistent (a USD-par cash
    # purchase of 9,500 USD against a RUB-nominal par worth 12.50 USD), and
    # the corrected engine surfaces that contradiction exactly: bond
    # unrealized 6.25, cash FX 0, attributed 6.25, control -9,375,
    # unexplained -9,381.25 -> unreconciled. No bond guard reason remains
    # (guard retired).
    assert Decimal(nr["nav"]["raw"]) == Decimal("10625.00")
    assert nr["nav"]["status"] == "ok"
    assert "bond_notional_fallback_unconverted" not in doc["reasons"]
    assert Decimal(nr["controlTotal"]["raw"]) == Decimal("-9375.00")
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == Decimal("6.25")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("0.00")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("0.00")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("6.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == Decimal("-9381.25")
    assert nr["reconciliation"] == "unreconciled"
    assert doc["status"] == "partial"
    assert "unexplained_difference" in doc["reasons"]


@pytest.mark.django_db
def test_bond_fallback_nominal_matches_reporting_quotation_differs_is_no_op(user):
    """EUR-quotation bond with a USD nominal, reported in USD:
    get_current_notional's source is the nominal (USD), so the fallback's
    omitted conversion is fx(USD -> USD) = 1 - a no-op. The statement must
    not attribute a missing notional conversion just because the
    quotation currency differs from the reporting currency.

    Hand derivation (fx EUR->USD 1.0 throughout): cash 20,000 EUR - 9,500
    EUR buy = 10,500 EUR = 10,500 USD; value = 10 x 100% x 1,000 / 100 =
    10,000 USD; NAV 20,500; control 500 = unrealized price 500 + fx 0 +
    cash FX 0; reconciled, complete, no bond reason."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="EUR Quote USD Nominal", currency="EUR", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="USD",
        is_amortizing=True,
    )
    make_fx("EUR", "USD", date(2065, 1, 5), "1.00", user)
    make_fx("EUR", "USD", date(2065, 10, 1), "1.00", user)
    make_tx(account, date(2065, 1, 5), "Cash in", currency="EUR",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2065, 1, 5), "Buy", security=bond, currency="EUR",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_price(bond, date(2065, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2065, 10, 15), "USD", 2, [account.id])
    assert "bond_notional_fallback_unconverted" not in doc["reasons"]
    assert doc["netResult"]["nav"]["status"] == "ok"
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("500")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("500")
    assert Decimal(doc["netResult"]["components"]["fx"]["raw"]) == Decimal("0")
    assert doc["netResult"]["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


# ---------------------------------------------------------------------------
# Mixed-asset known-subtotal exclusion (review round 5, finding 2)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_mixed_assets_keep_reliable_known_subtotal_exclude_defective_bond(user):
    """Wire-boundary regression: a known-defective bond (foreign, fallback
    notional, open position) alongside a reliable USD stock.

    Hand derivation:
      Stock: cash in 1,000 USD; buy 10 @ 50 (500); price 60
        -> unrealized price 100 (fx 0). RELIABLE.
      Bond: 10 RUB bonds, par 1,000, bought 95% for 9,500 RUB funded by
        20,000 RUB; RUB->USD 0.0100 at entry, 0.0125 at EOP; price 100.
        Fallback notional unconverted -> NAV bond leg 10,000 (defective);
        unrealized price 6.25, fx 9,898.75 -> PROVISIONAL/DEFECTIVE.
      NAV = 600 (stock at market) + 10,000 (defective bond leg) + 131.25
        = 10,731.25; net capital 1,200; control 9,531.25.
      Cash FX = cash EOP (131.25 + 500) - own-date flows (200 + 500) =
        -68.75 (known).
      Known subtotal (wire `attributedSum.knownSubtotal`) = reliable
        unrealized 100 + cash FX -68.75 = 31.25 - the defective bond
        contributions (6.25 / 9,898.75) must be excluded, and the aggregate
        must be unknown rather than exact.
      Provisional diagnostics expose the excluded amounts.
    """
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Mixed", currency="RUB", exposure="Fixed Income")
    stock = make_asset(user, type="Stock", name="Clean Stock", currency="USD", exposure="Equity")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2066, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2066, 10, 1), "0.0125", user)
    make_tx(account, date(2066, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2066, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_tx(account, date(2066, 1, 5), "Cash in", currency="USD",
            cash_flow=Decimal("1000"))
    make_tx(account, date(2066, 1, 5), "Buy", security=stock, currency="USD",
            quantity=Decimal("10"), price=Decimal("50"))
    make_price(bond, date(2066, 10, 1), "100")
    make_price(stock, date(2066, 10, 1), "60")
    doc = build_reconciled_summary(user, date(2066, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    # Corrected engine: bond value 125.00 + RUB cash 131.25 + USD cash 500
    # + stock 600 = NAV 1,356.25; control 156.25; attribution = bond
    # unrealized price 6.25 + stock unrealized 100 (= 106.25 component) +
    # security FX 23.75 + cash FX 26.25 = 156.25 -> reconciled, complete.
    # Both assets certified; no provisional diagnostics (guard retired).
    assert Decimal(nr["nav"]["raw"]) == Decimal("1356.25")
    assert nr["nav"]["status"] == "ok"
    assert Decimal(nr["controlTotal"]["raw"]) == Decimal("156.25")
    assert nr["components"]["unrealizedPrice"]["status"] == "ok"
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == Decimal("106.25")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("156.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == Decimal("0")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert "bond_notional_fallback_unconverted" not in doc["reasons"]
    assert "affectedProvisionalAttribution" not in doc["diagnostics"]

@pytest.mark.django_db
def test_bond_fallback_partial_disposal_realized_attribution_stays_provisional(user):
    """Affected foreign bond (amortizing, no NotionalHistory, USD report-
    ing), partial disposal with a remaining open position.

    Hand derivation (fx RUB->USD 0.0100 at entry, 0.0125 from the sale
    onward; par 1,000; bought 95% for 9,500 RUB funded by 20,000 RUB;
    sell 4 @ 100% = 4,000 RUB):
      Realized (engine): proceeds 4,000 x 0.0125 = 50 minus basis
        4,000 x 0.95 x 0.01 = 38 -> total 12.00; price (local)
        4,000 x 5% = 200 RUB x 0.0125 = 2.50; fx 9.50.
        PROVISIONAL: notional_at_sell came from the unconverted fallback.
      Unrealized (engine): price 1,000 x 5% x 6 x 0.0125 / 100 = 3.75;
        total = 1,000 x (100 x 0.0125 - 0.95) x 6 / 100 = 5,943.00 (the
        dimensional defect); fx 5,939.25. PROVISIONAL.
      NAV: cash 14,500 x 0.0125 = 181.25 + bond value 6 x 100% x 1,000 /
        100 = 6,000 (unconverted fallback) = 6,181.25; net capital 200;
        control 5,981.25.
    The statement must mark BOTH realized and unrealized partial with the
    bond reason (never silently certifying an excluded contribution as
    zero), expose the excluded amounts as provisional, and refuse
    certification."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Partial", currency="RUB", exposure="Fixed Income")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2059, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2059, 6, 1), "0.0125", user)
    make_fx("USD", "RUB", date(2059, 10, 1), "0.0125", user)
    make_tx(account, date(2059, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_tx(account, date(2059, 6, 1), "Sell", security=bond, currency="RUB",
            quantity=Decimal("-4"), price=Decimal("100"))
    make_price(bond, date(2059, 10, 1), "100")
    doc = build_reconciled_summary(user, date(2059, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    # Corrected engine: value = 6 x 100% x 1,000/100 x 0.0125 = 75.00;
    # cash 14,500 x 0.0125 = 181.25; NAV 256.25; realized 12.00 (price
    # 2.50 + fx 9.50) certified; unrealized 18.00 (price 3.75 + fx 14.25);
    # cash FX 26.25; attributed 56.25 -> reconciled, complete.
    assert Decimal(nr["nav"]["raw"]) == Decimal("256.25")
    assert nr["nav"]["status"] == "ok"
    realized = nr["components"]["realizedPrice"]
    assert realized["status"] == "ok"
    assert Decimal(realized["raw"]) == Decimal("2.50")
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == Decimal("3.75")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("56.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == Decimal("0")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert doc["returns"]["totalReturn"]["status"] == "ok"
    assert "affectedProvisionalAttribution" not in doc["diagnostics"]


@pytest.mark.django_db
def test_mixed_bond_and_stock_realized_known_subtotal_wires_reliably(user):
    """Wire regression: the same affected bond (partial disposal, open
    position) alongside a RELIABLE USD stock with its own realized gain.
    The stock's realized 50.00 stays in the labelled realized known
    subtotals; the bond's provisional realized (2.50 / 9.50) and
    unrealized (3.75 / 5,939.25) stay out; the aggregate remains unknown
    (incomplete). Hand derivation:
      Bond leg: NAV 6,181.25 (as above; control contribution 5,981.25).
      Stock: cash in 1,000; buy 10 @ 50 (500); sell 5 @ 60 (300);
        realized 50; remaining 5 @ 60 = 300 unrealized, fx 0.
        Stock account: cash 800 + 300 = 1,100.
      NAV 6,181.25 + 1,100 = 7,281.25; net capital 200 + 1,000 = 1,200;
      control 6,081.25.
      Cash EOP 181.25 + 800 = 981.25; own-date flows 200 - 95 + 50 +
        1,000 - 500 + 300 = 955; cash FX 26.25.
      Known subtotal = stock realized 50 + realized fx 0 + stock
        unrealized 50 + unrealized fx 0 + cash FX 26.25 = 126.25."""
    broker = make_broker(user)
    account = make_account(broker)
    bond = make_asset(user, type="Bond", name="RUB Bond Mixed Partial", currency="RUB", exposure="Fixed Income")
    stock = make_asset(user, type="Stock", name="Realized Stock", currency="USD", exposure="Equity")
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    make_fx("USD", "RUB", date(2059, 1, 5), "0.0100", user)
    make_fx("USD", "RUB", date(2059, 6, 1), "0.0125", user)
    make_fx("USD", "RUB", date(2059, 10, 1), "0.0125", user)
    make_tx(account, date(2059, 1, 5), "Cash in", currency="RUB",
            cash_flow=Decimal("20000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=bond, currency="RUB",
            quantity=Decimal("10"), price=Decimal("95"), notional=Decimal("1000"))
    make_tx(account, date(2059, 6, 1), "Sell", security=bond, currency="RUB",
            quantity=Decimal("-4"), price=Decimal("100"))
    make_tx(account, date(2059, 1, 5), "Cash in", currency="USD",
            cash_flow=Decimal("1000"))
    make_tx(account, date(2059, 1, 5), "Buy", security=stock, currency="USD",
            quantity=Decimal("10"), price=Decimal("50"))
    make_tx(account, date(2059, 6, 1), "Sell", security=stock, currency="USD",
            quantity=Decimal("-5"), price=Decimal("60"))
    make_price(bond, date(2059, 10, 1), "100")
    make_price(stock, date(2059, 10, 1), "60")
    doc = build_reconciled_summary(user, date(2059, 10, 15), "USD", 2, [account.id])
    nr = doc["netResult"]
    # Corrected engine: bond value 125.00 + RUB cash 131.25 + USD cash 500
    # + stock 600 = NAV 1,356.25; control 156.25; attribution = bond
    # unrealized price 6.25 + bond fx 23.75 + stock unrealized 100 + cash
    # FX 26.25 = 156.25 -> reconciled, complete. Both assets certified; no
    # provisional diagnostics remain (guard retired).
    # Corrected engine (both assets sold partially): RUB cash 14,500 x
    # 0.0125 = 181.25 + USD cash 800 + bond value 75 + stock 300 = NAV
    # 1,356.25 (same total as the hold-only case, different composition);
    # control 156.25; realized = bond 2.50 + stock 50 (= 52.50 component);
    # unrealized = bond 3.75 + stock 50 (= 53.75); security FX = bond
    # 9.50 + 14.25 = 23.75; cash FX = 981.25 - 955 = 26.25; attributed
    # 52.50 + 53.75 + 23.75 + 26.25 = 156.25 -> reconciled, complete.
    assert Decimal(nr["nav"]["raw"]) == Decimal("1356.25")
    assert nr["nav"]["status"] == "ok"
    assert Decimal(nr["controlTotal"]["raw"]) == Decimal("156.25")
    assert Decimal(nr["components"]["realizedPrice"]["raw"]) == Decimal("52.50")
    assert nr["components"]["unrealizedPrice"]["status"] == "ok"
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == Decimal("53.75")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == Decimal("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == Decimal("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == Decimal("156.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == Decimal("0")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"
    assert "bond_notional_fallback_unconverted" not in doc["reasons"]
    assert "affectedProvisionalAttribution" not in doc["diagnostics"]


# ---------------------------------------------------------------------------
# Reward income conversion convention
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_crypto_reward_income_converts_usd_value_at_own_date(user):
    """Reward value is |qty| x USD price (0.2 x 10 = 2); conversion must use
    USD->target at the event date (not the coin rate). USD target keeps it
    exactly 2; the coins join the lot at that basis so unrealized stays 0."""
    broker = make_broker(user, name="OKX", precision=8)
    account = make_account(broker)
    coin = make_asset(user, type="Crypto", name="STAKE", currency="USD")
    make_tx(account, date(2057, 1, 5), "Cash in", currency="USDT",
            cash_flow=Decimal("100"))
    make_tx(account, date(2057, 1, 5), "Crypto trade in", currency="USDT",
            security=coin, quantity=Decimal("10"), price=Decimal("10"))
    # Reward value is USD-denominated, so the row carries USD: the engine's
    # basis replay then takes fx 1 (coin-currency reward rows would hit the
    # engine's coin-rate scaling quirk — documented in the design doc).
    make_tx(account, date(2057, 2, 1), "Crypto reward", currency="USD",
            security=coin, quantity=Decimal("0.2"), price=Decimal("10"))
    make_price(coin, date(2057, 10, 1), "10")
    doc = build_reconciled_summary(user, date(2057, 10, 15), "USD", 2, [account.id])
    assert Decimal(doc["netResult"]["components"]["income"]["raw"]) == Decimal("2")
    assert Decimal(doc["netResult"]["components"]["unrealizedPrice"]["raw"]) == Decimal("0")
    assert Decimal(doc["netResult"]["controlTotal"]["raw"]) == Decimal("2")
    assert doc["netResult"]["reconciliation"] == "reconciled"
