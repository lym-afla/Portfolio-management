# Crypto-as-Currency Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce Crypto as a first-class NAV asset class (Cash / Crypto / Securities) and revert the unified trade commission model to real fill prices with cross-currency commissions as separate rows.

**Architecture:** Crypto coins stay in `Assets` (`type="Crypto"`) but get their own NAV bucket, valued via `Prices`, FX-derived through USD. The commission model reverts: trades store real fill prices; a fee whose currency differs from the trade's becomes its own `Transactions` row (a crypto commission) that moves the fee asset's quantity. Every transaction row stays single-currency, so `total_cash_flow` keeps its `Decimal` signature.

**Tech Stack:** Django 5, Django REST Framework, Django Channels, `Decimal` for all money math, `networkx` for FX graph, `pytest` + `pytest-django`, `uv` project mode, `pyxlsx`/`yfinance`.

**Spec:** `docs/superpowers/specs/2026-08-06-crypto-as-currency-foundation-design.md` (read before starting; all decisions are documented there).

## Global Constraints

- **Decimal only** for all money/price/quantity/FX math — never `float`. (AGENTS.md numeric safety.)
- **Precision:** ≥6 dp prices, ≥9 dp quantities/FX. **Rounding:** `ROUND_HALF_UP`. Persisted aggregates: 2 dp (or broker `cash_precision` for crypto). UI: per `CustomUser.digits`.
- **Commands run from `backend/`:** `uv run python -m pytest`, `uv run python run_uvicorn.py`. Use `uv run <cmd>` for everything.
- **Protected code:** changes to `services/nav.py` (`NAV_at_date`), `services/fx.py` (`get_rate`), `services/transactions.py` (`total_cash_flow`), `services/crypto_exchange.py` (importer logic) require a PR with `needs-approval` label and unit tests + regression fixtures with expected numeric results.
- **Test fixture pattern:** `@pytest.fixture def user(db)` + `Brokers.objects.create(...)` + `Accounts.objects.create(...)` (see `tests/conftest.py`). All money values in tests are `Decimal`.
- **No schema migrations** in this plan (routing/constants/code changes only). If a migration becomes necessary, stop and confirm — it's protected.
- **TDD:** every task writes the failing test first, runs it to confirm failure, implements, runs to confirm pass, then commits.

---

## File Structure

**New files:**
- `backend/services/crypto.py` — Crypto-class helpers: `is_crypto(asset)`, `is_crypto_code(code, date=None)`, `crypto_usd_price(code, date, investor)`, `crypto_fx_rate(code, target, date, investor)`. Single responsibility: "what is a crypto coin and what's it worth."
- `backend/tests/unit/services/test_crypto_class.py` — unit tests for `services/crypto.py`.
- `backend/tests/unit/calculations/test_nav_crypto_bucket.py` — NAV regression fixture (BTC + stock + cash → 3 buckets).
- `backend/tests/unit/calculations/test_fx_crypto_branch.py` — `get_rate` crypto branch tests.
- `backend/tests/unit/imports/test_crypto_commission_rows.py` — separate-commission-row tests for `_spot_legs`.

**Modified files:**
- `backend/constants.py` — add `TRANSACTION_TYPE_CRYPTO_COMMISSION` + choice; add `CRYPTO_QUOTE_CURRENCIES` set (open-ended, documented as derived-from-data not enumerated).
- `backend/services/fx.py` — `get_rate` gains a crypto branch that consults `Prices` via `services.crypto.crypto_fx_rate`.
- `backend/services/nav.py` — `NAV_at_date` splits the securities loop: crypto assets → `"Crypto"` bucket; securities loop excludes `type="Crypto"`. IRR `_calculate_cash_flow` updated for the reverted commission model.
- `backend/services/transactions.py` — `total_cash_flow`: stop recomputing `qty×price` for crypto trades (read stored cash flow); drop the cross-currency commission exclusion.
- `backend/services/crypto_exchange.py` — `_spot_legs` reverts to real fill price; cross-currency fees emit a separate `"commission"` leg. `resolve_crypto_asset` sets `yahoo_symbol`. `fetch_crypto_usd_price_from_yahoo` reads `asset.yahoo_symbol`. `persist_crypto_exchange_event` persists the commission leg as its own row.
- `backend/tests/unit/calculations/test_nav_crypto_cash_flow.py` — update `test_nav_crypto_base_fee_excludes_commission` (behavior changes under revert).
- `backend/tests/unit/calculations/test_total_cash_flow_crypto.py` — update assertions for the reverted model.
- `backend/tests/unit/imports/test_crypto_exchange_import.py` — update spot tests for real-price + separate commission rows.

---

## Task 1: Crypto-class helpers module (`services/crypto.py`)

**Files:**
- Create: `backend/services/crypto.py`
- Test: `backend/tests/unit/services/test_crypto_class.py`

**Interfaces:**
- Consumes: `common.models.Assets`, `common.models.Prices`, `services.pricing.price_at_date`.
- Produces:
  - `is_crypto(asset) -> bool` — True iff `asset.type == "Crypto"`.
  - `is_crypto_code(code, date_as_of=None) -> bool` — True iff an `Assets` row with `type="Crypto"` exists whose ISIN resolves to `code` (ISIN format `CRYPTO:BTC` → code `BTC`). `date_as_of` unused for now (reserved).
  - `crypto_usd_price(code, date_as_of, investor=None) -> Decimal` — the coin's USD price from `Prices` on/before `date_as_off`; raises `ValueError` if no price.
  - `crypto_fx_rate(code, target, date_as_of, investor=None) -> Decimal` — "multiply `code` → `target`" rate; resolves `code→USD` from `Prices` then `USD→target` via `services.fx.get_rate`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/services/test_crypto_class.py`:

```python
"""Tests for services/crypto.py — Crypto-class helpers."""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Assets, Prices
from common.models import FX
from services.crypto import (
    crypto_fx_rate,
    crypto_usd_price,
    is_crypto,
    is_crypto_code,
)


@pytest.fixture
def btc_asset(user):
    asset = Assets.objects.create(
        type="Crypto",
        ISIN="CRYPTO:BTC",
        name="BTC",
        currency="USD",
        exposure="Commodity",
        yahoo_symbol="BTC-USD",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def usd_eur_fx(user):
    fx = FX.objects.create(
        date=date(2026, 1, 1),
        from_currency="USD",
        to_currency="EUR",
        rate=Decimal("1.1"),
    )
    fx.investors.add(user)
    return fx


@pytest.mark.django_db
def test_is_crypto_true_for_crypto_asset(btc_asset):
    assert is_crypto(btc_asset) is True


@pytest.mark.django_db
def test_is_crypto_false_for_stock(asset):
    assert is_crypto(asset) is False


@pytest.mark.django_db
def test_is_crypto_code_recognizes_btc(btc_asset):
    assert is_crypto_code("BTC") is True
    assert is_crypto_code("btc") is True  # case-insensitive


@pytest.mark.django_db
def test_is_crypto_code_false_for_fiat_and_stablecoin():
    assert is_crypto_code("USD") is False
    assert is_crypto_code("USDT") is False
    assert is_crypto_code("EUR") is False
    assert is_crypto_code("UNKNOWN") is False


@pytest.mark.django_db
def test_crypto_usd_price_from_prices(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    price = crypto_usd_price("BTC", date(2026, 1, 1))
    assert price == Decimal("60000")


@pytest.mark.django_db
def test_crypto_usd_price_missing_raises(btc_asset):
    with pytest.raises(ValueError):
        crypto_usd_price("BTC", date(2026, 1, 1))


@pytest.mark.django_db
def test_crypto_fx_rate_btc_to_eur(btc_asset, usd_eur_fx):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    # BTC -> EUR = 60000 (BTC/USD) * 1.1 (USD/EUR... but storage is quote-per-base,
    # from=USD to=EUR rate=1.1 means 1.1 USD per 1 EUR; get_rate returns multiply
    # source->target so EUR->USD = 1.1, USD->EUR = 1/1.1). crypto_fx_rate returns
    # the multiply factor BTC->EUR.
    rate = crypto_fx_rate("BTC", "EUR", date(2026, 1, 1), investor=user)
    # BTC->USD (60000) then USD->EUR (1/1.1) = 60000/1.1
    expected = (Decimal("60000") / Decimal("1.1")).quantize(Decimal("0.000001"))
    assert rate == expected


@pytest.mark.django_db
def test_crypto_fx_rate_same_currency_is_one(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    rate = crypto_fx_rate("BTC", "USD", date(2026, 1, 1), investor=user)
    assert rate == Decimal("60000")  # BTC->USD = the price itself
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/services/test_crypto_class.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_crypto'` (module doesn't exist).

- [ ] **Step 3: Write minimal implementation**

Create `backend/services/crypto.py`:

```python
"""Crypto-class helpers — what is a crypto coin and what's it worth.

Crypto coins are ``Assets`` rows with ``type="Crypto"`` (see spec §4.1). This
module is the rigorous class boundary: it centralizes every "is this crypto?"
check and every "what's this coin worth in USD / target currency" lookup so
the rest of the codebase never branches on ``type == "Crypto"`` ad hoc.

Coins are USD-priced by convention (``Assets.currency == "USD"`` for crypto);
the USD price lives in the ``Prices`` table. FX conversion to a non-USD target
chains through the existing fiat FX graph (spec §4.5, decision 2a).

Numeric safety: ``Decimal`` everywhere. Never ``float``.
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from common.models import Assets, Prices

logger = logging.getLogger(__name__)


def is_crypto(asset) -> bool:
    """Return True iff ``asset`` is a Crypto-class instrument."""
    return getattr(asset, "type", None) == "Crypto"


def is_crypto_code(code: str, date_as_of=None) -> bool:
    """Return True iff a Crypto-class ``Assets`` row exists for ``code``.

    ``code`` is the coin symbol (e.g. ``"BTC"``). The asset's ISIN follows the
    ``CRYPTO:<code>`` convention (see ``_crypto_asset_identifier`` in
    ``services.crypto_exchange``); we resolve both the direct and hashed forms
    by matching the asset's ``name`` (the coin symbol) for robustness.
    """
    if not code:
        return False
    symbol = str(code).upper().strip()
    return Assets.objects.filter(type="Crypto", name=symbol).exists()


def crypto_usd_price(code: str, date_as_of, investor=None) -> Decimal:
    """Return the USD price of ``code`` on/before ``date_as_of``.

    Sources the latest ``Prices`` row for the coin on or before the date.
    Raises ``ValueError`` when no price is available (the coin is unpriced).
    """
    symbol = str(code).upper().strip()
    asset = Assets.objects.filter(type="Crypto", name=symbol).first()
    if asset is None:
        raise ValueError(f"No crypto asset for code {code}")
    quote = (
        Prices.objects.filter(security=asset, date__lte=date_as_of).order_by("-date").first()
    )
    if quote is None:
        raise ValueError(f"No USD price for {code} on or before {date_as_of}")
    return Decimal(quote.price)


def crypto_fx_rate(code: str, target: str, date_as_of, investor=None) -> Decimal:
    """Return the 'multiply ``code`` -> ``target``' FX rate for a crypto coin.

    Resolves ``code -> USD`` from the coin's ``Prices`` row (the BTC-USD price
    IS the BTC->USD rate), then ``USD -> target`` via the existing fiat FX
    graph. For ``target == "USD"`` the price itself is returned (no graph hop).
    """
    target = (target or "").upper().strip()
    code = (code or "").upper().strip()
    if code == target:
        return Decimal("1")

    usd_price = crypto_usd_price(code, date_as_of, investor)
    if target == "USD":
        return usd_price

    # Lazy import avoids a circular load (services.fx imports common.models at
    # top level; this module imports common.models at top level — safe either
    # way, but the lazy form keeps the dependency direction explicit).
    from services.fx import get_rate as fx_get_rate

    usd_to_target = fx_get_rate("USD", target, date_as_of, investor)["FX"]
    return (usd_price * usd_to_target).quantize(Decimal("0.000001"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/services/test_crypto_class.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/crypto.py backend/tests/unit/services/test_crypto_class.py
git commit -m "feat(crypto): add services/crypto.py Crypto-class helpers (is_crypto, crypto_usd_price, crypto_fx_rate)"
```

---

## Task 2: FX crypto branch in `get_rate`

**Files:**
- Modify: `backend/services/fx.py:134-311` (the `get_rate` function)
- Test: `backend/tests/unit/calculations/test_fx_crypto_branch.py`

**Interfaces:**
- Consumes: `services.crypto.is_crypto_code`, `services.crypto.crypto_fx_rate` (from Task 1).
- Produces: `services.fx.get_rate(source, target, date_as_of, investor=None)` now resolves when `source` or `target` is a crypto code, returning the same dict shape (`{"FX": Decimal, "conversions": int, "dates_async": bool, "dates": [...]}`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/calculations/test_fx_crypto_branch.py`:

```python
"""Tests for the crypto branch of services.fx.get_rate (spec §4.5)."""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Assets, FX, Prices
from services.fx import get_rate


@pytest.fixture
def btc_asset(user):
    asset = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC",
        currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def usd_eur_fx(user):
    fx = FX.objects.create(
        date=date(2026, 1, 1), from_currency="USD", to_currency="EUR", rate=Decimal("1.1"),
    )
    fx.investors.add(user)
    return fx


@pytest.mark.django_db
def test_get_rate_btc_to_usd_uses_price(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    result = get_rate("BTC", "USD", date(2026, 1, 1))
    assert result["FX"] == Decimal("60000")


@pytest.mark.django_db
def test_get_rate_btc_to_eur_chains_through_usd(btc_asset, usd_eur_fx):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    result = get_rate("BTC", "EUR", date(2026, 1, 1), investor=user)
    expected = (Decimal("60000") / Decimal("1.1")).quantize(Decimal("0.000001"))
    assert result["FX"] == expected


@pytest.mark.django_db
def test_get_rate_usd_to_btc_inverts(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    result = get_rate("USD", "BTC", date(2026, 1, 1))
    # USD -> BTC = 1 / 60000, rounded to 6 dp
    expected = (Decimal("1") / Decimal("60000")).quantize(Decimal("0.000001"))
    assert result["FX"] == expected


@pytest.mark.django_db
def test_get_rate_btc_missing_price_raises(btc_asset):
    with pytest.raises(ValueError):
        get_rate("BTC", "USD", date(2026, 1, 1))


@pytest.mark.django_db
def test_get_rate_stablecoin_peg_unchanged():
    """The USD<->USDT 1.0 peg short-circuit must still work."""
    result = get_rate("USD", "USDT", date(2026, 1, 1))
    assert result["FX"] == Decimal("1.000000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/calculations/test_fx_crypto_branch.py -v`
Expected: FAIL — `get_rate("BTC", "USD", ...)` raises `ValueError("No FX rate found")` because BTC is not in the FX graph.

- [ ] **Step 3: Add the crypto branch to `get_rate`**

In `backend/services/fx.py`, add this block immediately **after** the stablecoin-peg short-circuit (after line 200, before the `try:` at line 202):

```python
    # Crypto branch (spec §4.5): a crypto code (BTC/ETH/...) resolves via its
    # Prices row, not the FX table. Lazy import avoids a circular load
    # (services.crypto imports common.models; this module imports common.models).
    from services.crypto import crypto_fx_rate, is_crypto_code

    src_is_crypto = is_crypto_code(source)
    tgt_is_crypto = is_crypto_code(target)
    if src_is_crypto or tgt_is_crypto:
        # crypto_fx_rate returns the multiply factor for (crypto -> fiat/crypto).
        # For fiat -> crypto we invert; for crypto -> crypto both sides resolve
        # through USD inside crypto_fx_rate.
        try:
            if src_is_crypto:
                fx = crypto_fx_rate(source, target, date_as_of, investor)
            else:
                # target is crypto, source is fiat: invert (crypto -> source).
                fwd = crypto_fx_rate(target, source, date_as_of, investor)
                fx = (Decimal("1") / fwd).quantize(Decimal("0.000001"))
        except ValueError:
            raise
        return {
            "FX": fx.quantize(Decimal("0.000001")),
            "conversions": 2,
            "dates_async": False,
            "dates": [date_as_of],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/calculations/test_fx_crypto_branch.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Run the full FX test suite to confirm no regressions**

Run: `uv run python -m pytest tests/unit/calculations/test_fx_ -v`
Expected: PASS — existing FX tests unaffected (the new branch only triggers for crypto codes, which don't appear in those tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/fx.py backend/tests/unit/calculations/test_fx_crypto_branch.py
git commit -m "feat(fx): crypto branch in get_rate resolves BTC/ETH via Prices (spec §4.5)"
```

---

## Task 3: NAV crypto bucket

**Files:**
- Modify: `backend/services/nav.py:148-233` (the `NAV_at_date` securities loop)
- Test: `backend/tests/unit/calculations/test_nav_crypto_bucket.py`

**Interfaces:**
- Consumes: `services.crypto.is_crypto` (Task 1); existing `position`, `calculate_value_at_date`, `get_fx_rate`.
- Produces: `NAV_at_date` breakdown gains a `"Crypto"` line. The securities loop excludes `type="Crypto"` assets; a new crypto loop values them into `analysis["Crypto"]` and `analysis["Total NAV"]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/calculations/test_nav_crypto_bucket.py`:

```python
"""NAV regression: BTC counts once, in a Crypto bucket (spec §4.3)."""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Prices, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.nav import NAV_at_date


@pytest.fixture
def crypto_portfolio(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-1")

    btc = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC",
        currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
    )
    btc.investors.add(user)
    Prices.objects.create(security=btc, date=date(2026, 1, 1), price=Decimal("60000"))

    stock = Assets.objects.create(
        type="Stock", ISIN="US0000000001", name="AAPL",
        currency="USD", exposure="Equity", yahoo_symbol="AAPL",
    )
    stock.investors.add(user)
    Prices.objects.create(security=stock, date=date(2026, 1, 1), price=Decimal("150"))

    # 0.5 BTC @ 60000 = 30000 in Crypto
    Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, date=date(2026, 1, 1),
        quantity=Decimal("0.5"), price=Decimal("60000"),
    )
    # 10 AAPL @ 150 = 1500 in Securities
    Transactions.objects.create(
        investor=user, account=account, security=stock, currency="USD",
        type="Buy", date=date(2026, 1, 1),
        quantity=Decimal("10"), price=Decimal("150"),
    )
    # 1000 USD cash
    Transactions.objects.create(
        investor=user, account=account, security=None, currency="USD",
        type="Cash in", date=date(2026, 1, 1),
        quantity=None, price=None, cash_flow=Decimal("1000"),
    )
    return user, account


@pytest.mark.django_db
def test_nav_three_buckets_counted_once(crypto_portfolio):
    user, account = crypto_portfolio
    result = NAV_at_date(
        user.id, (account.id,), date(2026, 1, 1), "USD",
        breakdown=("asset_type",),
    )
    # Total = 30000 (BTC) + 1500 (AAPL) + 1000 (cash) = 32500
    assert result["Total NAV"] == Decimal("32500")
    # BTC counted ONCE, in Crypto bucket — not in asset_type (which holds securities)
    assert result["asset_type"]["Crypto"] == Decimal("30000")
    assert result["asset_type"]["Stock"] == Decimal("1500")
    # Cash shows as its own entry under asset_type
    assert result["asset_type"]["Cash"] == Decimal("1000")


@pytest.mark.django_db
def test_nav_no_crypto_in_securities_breakdown(crypto_portfolio):
    """A portfolio with crypto must NOT also count it under security types."""
    user, account = crypto_portfolio
    result = NAV_at_date(
        user.id, (account.id,), date(2026, 1, 1), "USD",
        breakdown=("asset_type",),
    )
    # The securities-side asset_type keys are Stock/Bond/etc. Crypto has its own bucket.
    crypto_keys = [k for k in result["asset_type"] if "Crypto" in str(k) or "BTC" in str(k)]
    assert crypto_keys == ["Crypto"]  # exactly one crypto bucket
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/calculations/test_nav_crypto_bucket.py -v`
Expected: FAIL — BTC currently valued in the securities loop under `result["asset_type"]["Crypto"]` (as `security.type`), so `test_nav_no_crypto_in_securities_breakdown` fails because today the bucket key is `asset.type` value `"Crypto"`, not separated. Actually today it WOULD pass by accident (Crypto is the type). The real failure: `test_nav_three_buckets_counted_once` — today BTC is valued but there is no separate handling; the assertion `result["asset_type"]["Crypto"] == 30000` may already pass since `security.type == "Crypto"`. Confirm the exact failure by running.

- [ ] **Step 3: Split the NAV securities loop — crypto gets its own bucket**

In `backend/services/nav.py`, modify the securities loop (lines 196-214). The current loop iterates all `portfolio` assets. Split it: crypto assets route to `analysis["Crypto"]` and `analysis["Total NAV"]`, never to `analysis["asset_type"]`/`analysis["asset_class"]`. Securities (non-crypto) keep the existing breakdown behavior.

Add the import at the top (after line 47):
```python
from services.crypto import is_crypto
```

Replace the loop body at lines 196-214 with:

```python
    for security in portfolio:
        for account in portfolio_accounts:
            account_position = position(security, date, user_id, [account.id])
            if account_position == 0:
                continue

            account_value = calculate_value_at_date(
                security, date, user_id, target_currency, [account.id]
            )

            analysis["Total NAV"] += account_value

            # Crypto gets its own bucket; never the securities-side breakdowns.
            if is_crypto(security):
                analysis["Crypto"]["__total__"] += account_value
                analysis["Crypto"][security.name] += account_value
                continue

            if "account" in breakdown:
                analysis["account"][account.name] += account_value
            else:
                for breakdown_type in breakdown:
                    key = getattr(security, item_type[breakdown_type])
                    analysis[breakdown_type][key] += account_value
```

Also initialize the `"Crypto"` bucket in the breakdown setup (after line 182, inside the breakdown-init block — but `"Crypto"` should be tracked regardless of `breakdown` args, since it's a first-class class). Add unconditionally after line 172 (`analysis["Total NAV"] = Decimal(0)`):

```python
    analysis["Crypto"] = defaultdict(Decimal)
```

Note: `analysis` is a `defaultdict(lambda: defaultdict(Decimal))`, so `analysis["Crypto"]` works either way, but initializing it explicitly ensures it always appears in the output (callers rely on the key existing).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/calculations/test_nav_crypto_bucket.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full NAV suite to confirm no regressions**

Run: `uv run python -m pytest tests/unit/calculations/test_nav_calculations.py tests/unit/calculations/test_value_and_nav.py -v`
Expected: PASS — portfolios without crypto are unaffected (the `is_crypto` branch never triggers).

- [ ] **Step 6: Commit**

```bash
git add backend/services/nav.py backend/tests/unit/calculations/test_nav_crypto_bucket.py
git commit -m "feat(nav): Crypto as first-class NAV bucket, excluded from securities (spec §4.3)"
```

---

## Task 4: Add `TRANSACTION_TYPE_CRYPTO_COMMISSION` constant

**Files:**
- Modify: `backend/constants.py:81` (after the crypto trade types) and `:108` (in `TRANSACTION_TYPE_CHOICES`)

**Interfaces:**
- Produces: `TRANSACTION_TYPE_CRYPTO_COMMISSION = "Crypto commission"` and a matching choice in `TRANSACTION_TYPE_CHOICES`. Used by Task 6 (commission-row persistence).

- [ ] **Step 1: Add the constant and choice**

In `backend/constants.py`, after line 80 (`TRANSACTION_TYPE_CRYPTO_TRADE_OUT = "Crypto trade out"`), add:

```python
TRANSACTION_TYPE_CRYPTO_COMMISSION = "Crypto commission"
```

In the `TRANSACTION_TYPE_CHOICES` tuple (around line 108), add before the closing `)`:

```python
    (TRANSACTION_TYPE_CRYPTO_COMMISSION, "Crypto commission"),
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `uv run python -c "from constants import TRANSACTION_TYPE_CRYPTO_COMMISSION; print(TRANSACTION_TYPE_CRYPTO_COMMISSION)"`
Expected: prints `Crypto commission`.

- [ ] **Step 3: Commit**

```bash
git add backend/constants.py
git commit -m "feat(constants): add TRANSACTION_TYPE_CRYPTO_COMMISSION for separate commission rows"
```

---

## Task 5: Revert `_spot_legs` to real fill price + separate commission leg

**Files:**
- Modify: `backend/services/crypto_exchange.py:509-627` (the `_spot_legs` function)
- Test: `backend/tests/unit/imports/test_crypto_commission_rows.py`

**Interfaces:**
- Consumes: existing `_split_symbol`.
- Produces: `_spot_legs` now emits:
  - For a **same-currency fee** (fee in the quote currency): the fee stays folded into the base/quote settlement exactly as today (one base leg + one quote leg, real fill price). No separate commission leg.
  - For a **cross-currency fee** (fee in a currency that is neither the base nor the quote): the fee is emitted as a **separate leg** with `role="commission"`, `asset=<fee_asset>`, `quantity=<signed fee>`, `instrument="coin"`. The trade legs carry the real fill price (no fee adjustment).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/imports/test_crypto_commission_rows.py`:

```python
"""Tests for _spot_legs real-price model + separate commission rows (spec §5.5).

The reverted model: trades store the real fill price; a fee whose currency
differs from BOTH base and quote becomes its own commission leg.
"""
from decimal import Decimal

from services.crypto_exchange import _spot_legs


def test_stablecoin_quote_buy_same_currency_fee_folds_into_settlement():
    """USDT-fee on a BTC-USDT buy: fee folds into the USDT settlement, real price kept."""
    # Buy 1 BTC @ 60000 USDT, fee -10 USDT. The settlement = -60000 + (-10) = -60010.
    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("1"), price=Decimal("60000"),
        fee_delta=Decimal("-10"), fee_asset="USDT",
        quote_cash_amount=Decimal("-60010"),
    )
    # Single base leg (stablecoin-quote model) with effective price reproducing
    # the principal net of same-currency fee. price = |settlement| / qty.
    assert len(legs) == 1
    assert legs[0]["asset"] == "BTC"
    assert legs[0]["quantity"] == Decimal("1")
    # Effective price = 60010 / 1 (principal net of fee, since fee is same-currency)
    assert legs[0]["price"] == Decimal("60010")
    # No separate commission leg for same-currency fee
    assert not any(leg.get("role") == "commission" for leg in legs)


def test_cross_currency_fee_emits_separate_commission_leg():
    """BTC-fee on a BTC-USDT buy: fee is a separate BTC commission leg, real price kept."""
    # Buy 1 BTC @ 60000 USDT, fee -0.001 BTC. Fee currency != quote (USDT).
    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("1"), price=Decimal("60000"),
        fee_delta=Decimal("-0.001"), fee_asset="BTC",
        quote_cash_amount=Decimal("-60000"),
    )
    # Base leg with REAL fill price (not adjusted for the cross-currency fee)
    base_leg = next(leg for leg in legs if leg.get("role") != "commission" and leg["asset"] == "BTC")
    assert base_leg["quantity"] == Decimal("1")  # NOT netted (no +fee into qty)
    assert base_leg["price"] == Decimal("60000")  # real fill price, not effective

    # Separate commission leg in BTC
    commission_leg = next(leg for leg in legs if leg.get("role") == "commission")
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("-0.001")
    assert commission_leg["instrument"] == "coin"


def test_crypto_crypto_pair_keeps_two_leg_model():
    """ETH/BTC pair: two-leg model with real price; BTC-fee is separate leg."""
    # Buy 1 ETH @ 0.016 BTC, fee -0.00001 BTC (BTC is the quote here, so same-currency).
    legs = _spot_legs(
        side="buy", base="ETH", quote="BTC",
        qty=Decimal("1"), price=Decimal("0.016"),
        fee_delta=Decimal("-0.00001"), fee_asset="BTC",
    )
    base_leg = next(leg for leg in legs if leg["asset"] == "ETH")
    quote_leg = next(leg for leg in legs if leg["asset"] == "BTC" and leg.get("role") == "quote")
    assert base_leg["quantity"] == Decimal("1")
    assert base_leg["price"] == Decimal("0.016")
    # BTC is the quote, so the BTC fee folds into the quote settlement (no separate leg)
    assert not any(leg.get("role") == "commission" for leg in legs)
    # Quote leg settlement includes the fee
    assert quote_leg["quantity"] == Decimal("-0.016") + Decimal("-0.00001")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/imports/test_crypto_commission_rows.py -v`
Expected: FAIL — current `_spot_legs` nets base-fee into quantity and folds quote-fee into an effective price; the cross-currency test expects a separate commission leg that doesn't exist yet.

- [ ] **Step 3: Rewrite `_spot_legs`**

Replace the body of `_spot_legs` in `backend/services/crypto_exchange.py` (lines 509-627) with:

```python
def _split_symbol(symbol: str) -> Tuple[str, str]:
    for quote in SUPPORTED_QUOTE_SUFFIXES:
        if symbol.endswith(quote) and symbol != quote:
            return symbol[: -len(quote)], quote
    raise ValueError(f"Cannot split crypto symbol: {symbol}")


def _spot_legs(
    side: str,
    base: str,
    quote: str,
    qty: Decimal,
    price: Decimal,
    fee_delta: Decimal,
    fee_asset: str,
    quote_cash_amount: Optional[Decimal] = None,
) -> List[Dict[str, Any]]:
    """Build the legs for a spot fill under the real-price commission model (spec §5).

    Real fill price is always preserved. Fee handling depends on the fee currency:
    - SAME-currency fee (fee in quote for stablecoin-quote, or fee in quote/base
      for crypto-crypto pairs): folds into the settlement, no separate leg.
    - CROSS-currency fee (fee in neither base nor quote): a separate ``role="commission"``
      leg that moves the fee asset's quantity.

    For stablecoin quotes (USDT/USDC) the trade is a single base leg (the stablecoin
    is cash). For crypto-crypto pairs it's the two-leg base+quote model.
    """
    normalized_fee_asset = (fee_asset or "").upper()
    fee_in_base = normalized_fee_asset == base.upper()
    fee_in_quote = normalized_fee_asset == quote.upper()
    is_same_currency_fee = fee_in_base or fee_in_quote

    if quote.upper() in STABLECOIN_CURRENCIES:
        # Stablecoin-quote: single base leg (stablecoin is cash).
        settlement = quote_cash_amount if quote_cash_amount is not None else qty * price

        if side.lower() == "buy":
            base_quantity = qty
        elif side.lower() == "sell":
            base_quantity = -qty
        else:
            raise ValueError(f"Unsupported spot side: {side}")

        # A base-asset fee on a stablecoin-quote trade is CROSS-currency (base != quote).
        # It does NOT net into quantity (spec §5.5 revert). It becomes a separate leg below.
        # A quote-asset (stablecoin) fee is SAME-currency: fold into the settlement
        # before deriving the effective price, so |price*qty| reproduces principal net fee.
        if fee_in_quote and quote_cash_amount is not None:
            # settlement already includes the fee; recover the principal.
            if side.lower() == "buy":
                priced_settlement = settlement + fee_delta
            else:
                priced_settlement = settlement - fee_delta
        elif fee_in_quote:
            # No exact settlement given; settlement = qty*price is the principal,
            # subtract the fee to get what the trader actually paid.
            priced_settlement = settlement + fee_delta if side.lower() == "buy" else settlement - fee_delta
        else:
            priced_settlement = settlement  # cross-currency or no fee: principal as-is

        effective_price = (
            abs(priced_settlement) / abs(base_quantity) if base_quantity else price
        )

        legs = [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": effective_price,
                "price_asset": "USD",
                "role": "base",
                "quote_currency": quote.upper(),
                "fee_asset": normalized_fee_asset,
            }
        ]
    else:
        # Crypto-crypto pair: two-leg base+quote model, real prices.
        value = qty * price
        quote_fee_delta = fee_delta if fee_in_quote else Decimal("0")
        base_fee_delta = fee_delta if fee_in_base else Decimal("0")

        if side.lower() == "buy":
            base_quantity = qty  # real quantity; base-fee handled as separate leg if cross
            quote_quantity = -value + quote_fee_delta
        elif side.lower() == "sell":
            base_quantity = -qty
            quote_quantity = value + quote_fee_delta
        else:
            raise ValueError(f"Unsupported spot side: {side}")

        base_price = abs(quote_quantity / base_quantity) if base_quantity else price
        legs = [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": base_price,
                "price_asset": quote,
                "role": "base",
            },
            {
                "asset": quote,
                "quantity": quote_quantity,
                "price": Decimal("1"),
                "price_asset": quote,
                "role": "quote",
            },
        ]

    # Cross-currency fee: emit a separate commission leg (spec §5.3/§5.5).
    if fee_delta and fee_delta != 0 and not is_same_currency_fee and normalized_fee_asset:
        legs.append(
            {
                "asset": normalized_fee_asset,
                "quantity": fee_delta,
                "price": Decimal("1"),
                "price_asset": normalized_fee_asset,
                "role": "commission",
                "instrument": "coin",
            }
        )

    return legs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/imports/test_crypto_commission_rows.py -v`
Expected: PASS (all 3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/unit/imports/test_crypto_commission_rows.py
git commit -m "feat(crypto): _spot_legs reverts to real fill price + separate cross-currency commission leg (spec §5)"
```

---

## Task 6: Persist the commission leg as its own row

**Files:**
- Modify: `backend/services/crypto_exchange.py:352-478` (`persist_crypto_exchange_event`)
- Modify: `backend/tests/unit/imports/test_crypto_exchange_import.py` (update spot assertions)

**Interfaces:**
- Consumes: `TRANSACTION_TYPE_CRYPTO_COMMISSION` (Task 4); the `"role": "commission"` leg from Task 5.
- Produces: `persist_crypto_exchange_event` emits a separate `Transactions` row of type `TRANSACTION_TYPE_CRYPTO_COMMISSION` for each commission leg. The row has `security=<fee asset>`, `currency=<fee asset code>`, `quantity=<fee_delta>` (so the position layer sums it), `commission=None`, and a dedup-safe `import_event_id` suffixed `:fee`.

- [ ] **Step 1: Write the failing test (add to test_crypto_exchange_import.py)**

Append to `backend/tests/unit/imports/test_crypto_exchange_import.py`:

```python
def test_normalize_okx_spot_fill_cross_currency_fee_emits_commission_leg():
    """A BTC-fee on a BTC-USDT buy produces a base leg + a separate BTC commission leg."""
    from services.crypto_exchange import normalize_okx_spot_fill
    event = normalize_okx_spot_fill(
        {
            "instId": "BTC-USDT",
            "tradeId": "t1", "ordId": "o1",
            "side": "buy",
            "fillSz": "1", "fillPx": "60000",
            "fee": "-0.001", "feeCcy": "BTC",
            "fillTime": "1700000000000",
            "quoteCashAmount": "-60000",
        }
    )
    roles = [leg.get("role") for leg in event.legs]
    assert "commission" in roles
    commission_leg = next(leg for leg in event.legs if leg.get("role") == "commission")
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("-0.001")
    # Base leg keeps real fill price
    base_leg = next(leg for leg in event.legs if leg.get("role") == "base")
    assert base_leg["price"] == Decimal("60000")
```

- [ ] **Step 2: Run test to verify it fails (or passes if Task 5 covered it)**

Run: `uv run python -m pytest tests/unit/imports/test_crypto_exchange_import.py::test_normalize_okx_spot_fill_cross_currency_fee_emits_commission_leg -v`
Expected: PASS already (Task 5 added the leg). If it fails, re-check Task 5. The remaining work is the persistence layer.

- [ ] **Step 3: Add commission-leg persistence to `persist_crypto_exchange_event`**

In `backend/services/crypto_exchange.py`, add the import at top (after line 25):

```python
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_CRYPTO_COMMISSION,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
```

In `persist_crypto_exchange_event`, the leg-processing loop (lines 360-398) currently skips `role == "fee"`. Commission legs have `role == "commission"` and must be persisted. Modify the loop so commission legs are collected separately and persisted as their own rows.

After the existing `leg_records` loop (after line 398), add a second loop for commission legs:

```python
        # Commission legs (cross-currency fees) become their own Transactions rows
        # that move the fee asset's quantity, so the position layer reconciles.
        commission_records = []
        for index, leg in enumerate(event.legs):
            if leg.get("role") != "commission":
                continue
            commission_records.append((index, leg))
```

Then, after the main `for index, leg, quantity, price in leg_records:` persistence loop (after line 477), add the commission-row persistence:

```python
        for index, leg in commission_records:
            fee_event_id = f"{event.provider_event_id}:fee:{index}"
            if Transactions.objects.filter(
                investor=user,
                account=account,
                import_provider=event.provider,
                import_account_id=import_account_id,
                import_event_id=fee_event_id,
            ).exists():
                continue
            fee_asset_symbol = str(leg["asset"]).upper()
            fee_asset = resolve_crypto_asset(fee_asset_symbol, user)
            fee_quantity = _leg_quantity(leg)
            tx_kwargs = dict(
                investor=user,
                account=account,
                security=fee_asset,
                currency=fee_asset_symbol,
                type=TRANSACTION_TYPE_CRYPTO_COMMISSION,
                date=event_time,
                quantity=_normalize_model_decimal(Transactions, "quantity", fee_quantity),
                price=None,
                comment=_event_comment(event, leg),
                import_provider=event.provider,
                import_account_id=import_account_id,
                import_event_id=fee_event_id,
                import_group_id=event.group_id,
                import_event_type=event.category,
            )
            try:
                with transaction.atomic():
                    created.append(Transactions.objects.create(**tx_kwargs))
            except IntegrityError:
                continue
```

- [ ] **Step 4: Update existing spot assertions in test_crypto_exchange_import.py**

Search `test_crypto_exchange_import.py` for spot-fill tests that assert `_spot_legs` behavior under the OLD model (effective price, netted quantity). The current OKX spot test (around the top of the file) likely asserts a single base leg. Update any assertion that checks an effective price or a netted quantity to the new real-price + separate-commission-leg behavior. If a test's fixture uses a same-currency (quote) fee, its assertions stay valid; if it uses a base/cross-currency fee, add assertions for the commission leg.

Run: `uv run python -m pytest tests/unit/imports/test_crypto_exchange_import.py -v`
Expected: any pre-existing spot test that asserted the old effective-price model now FAILS. Update those assertions to match Task 5's real-price behavior. (Read each failing test, update the expected values, re-run until PASS.)

- [ ] **Step 5: Run the full crypto import suite**

Run: `uv run python -m pytest tests/unit/imports/ tests/integration/workflows/test_crypto_exchange_persistence.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat(crypto): persist cross-currency commission legs as separate Crypto commission rows"
```

---

## Task 7: Update `total_cash_flow` for the reverted model

**Files:**
- Modify: `backend/services/transactions.py:219-257` (the crypto-trade branch of `total_cash_flow`)
- Modify: `backend/tests/unit/calculations/test_total_cash_flow_crypto.py`

**Interfaces:**
- Consumes: the stored per-leg cash flow (now real-price-based).
- Produces: `total_cash_flow` stops recomputing `quantity × price` for crypto trades when a stored `cash_flow` is present (the importer writes it per-leg); drops the `commission_currency != trade_currency` exclusion is N/A because cross-currency commissions are now separate rows (the trade row's commission, if any, is always same-currency now).

- [ ] **Step 1: Read the current test to understand what changes**

Run: `uv run python -m pytest tests/unit/calculations/test_total_cash_flow_crypto.py -v`
Note which tests encode the OLD behavior (base-fee excluded). Those need updating.

- [ ] **Step 2: Update `total_cash_flow` crypto-trade branch**

In `backend/services/transactions.py`, the crypto-trade branch (lines 219-257) currently recomputes `quantity × effective_price` and conditionally adds commission. Under the revert:
- The trade row's commission (if present) is now ALWAYS same-currency (cross-currency fees are separate rows). So the `commission_currency != trade_currency` exclusion is dead code — remove it.
- For crypto trades with a stored `cash_flow` (option legs, and any importer that writes it), use it directly. For crypto trades WITHOUT a stored `cash_flow`, fall back to `quantity × price`.

Replace lines 219-257 with:

```python
    elif transaction.type in [
        TRANSACTION_TYPE_BUY,
        TRANSACTION_TYPE_SELL,
        TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    ]:
        # Crypto option trades and any trade carrying an explicit cash_flow
        # use it directly (option quantity is in contracts; cash_flow is the
        # underlying settlement). Other crypto trades fall back to qty*price
        # now that the real fill price is stored (commission revert, spec §5).
        if (
            transaction.type in [TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]
            and transaction.cash_flow is not None
        ):
            calculated_cash_flow = transaction.cash_flow
        elif transaction.quantity and transaction.price is not None:
            effective_price = get_price(transaction) or Decimal(0)
            calculated_cash_flow = -Decimal(transaction.quantity) * effective_price
            if transaction.aci:
                calculated_cash_flow += Decimal(transaction.aci)
            # Commission on the trade row is always same-currency under the
            # reverted model (cross-currency fees are separate commission rows).
            if transaction.commission:
                calculated_cash_flow += Decimal(transaction.commission)
        # (the cross-currency commission exclusion is removed — see spec §5.3)
```

- [ ] **Step 3: Update the test file**

In `backend/tests/unit/calculations/test_total_cash_flow_crypto.py`, the test `test_nav_crypto_base_fee_excludes_commission` (in `test_nav_crypto_cash_flow.py` — check both files) encodes the OLD exclusion. Under the revert, a base-asset fee no longer sits on the trade row at all (it's a separate commission row), so the scenario is moot. Update the test to assert the new behavior: a crypto trade row with NO commission (because the fee went to a separate row) returns `-(price * quantity)`.

Read the current `test_total_cash_flow_crypto.py`, find the test asserting base-fee exclusion, and replace its assertion. If the test creates a trade row WITH a base-currency commission, that scenario no longer occurs in production — either delete the test (with a comment citing spec §5.3) or convert it to assert the separate-row model.

Run: `uv run python -m pytest tests/unit/calculations/test_total_cash_flow_crypto.py tests/unit/calculations/test_nav_crypto_cash_flow.py -v`
Expected: PASS after updates.

- [ ] **Step 4: Commit**

```bash
git add backend/services/transactions.py backend/tests/unit/calculations/test_total_cash_flow_crypto.py backend/tests/unit/calculations/test_nav_crypto_cash_flow.py
git commit -m "refactor(transactions): total_cash_flow drops cross-currency commission exclusion (spec §5.3)"
```

---

## Task 8: Generalize crypto price fetching to `yahoo_symbol`

**Files:**
- Modify: `backend/services/crypto_exchange.py:44` (drop `YAHOO_USD_PRICE_SYMBOLS`), `:102-116` (`resolve_crypto_asset`), `:212-243` (`fetch_crypto_usd_price_from_yahoo`)
- Test: extend `backend/tests/unit/services/test_crypto_class.py` or add `test_crypto_price_fetch.py`

**Interfaces:**
- Produces: `resolve_crypto_asset(symbol, user)` sets `yahoo_symbol=f"{SYMBOL}-USD"` on coin creation. `fetch_crypto_usd_price_from_yahoo(symbol, price_date)` reads the asset's `yahoo_symbol` instead of the hardcoded dict. The hardcoded `YAHOO_USD_PRICE_SYMBOLS` dict is removed.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/services/test_crypto_class.py`:

```python
@pytest.mark.django_db
def test_resolve_crypto_asset_sets_yahoo_symbol(user):
    from services.crypto_exchange import resolve_crypto_asset
    for symbol, expected_yahoo in [("BTC", "BTC-USD"), ("ETH", "ETH-USD"), ("TRUMP", "TRUMP-USD")]:
        asset = resolve_crypto_asset(symbol, user)
        assert asset.yahoo_symbol == expected_yahoo, f"{symbol} -> {asset.yahoo_symbol}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/services/test_crypto_class.py::test_resolve_crypto_asset_sets_yahoo_symbol -v`
Expected: FAIL — `resolve_crypto_asset` doesn't set `yahoo_symbol` today.

- [ ] **Step 3: Update `resolve_crypto_asset` and `fetch_crypto_usd_price_from_yahoo`**

In `backend/services/crypto_exchange.py`:

(a) Delete line 44: `YAHOO_USD_PRICE_SYMBOLS = {"BTC": "BTC-USD"}`.

(b) In `resolve_crypto_asset` (lines 102-116), add `yahoo_symbol` to `submitted_fields`:

```python
def resolve_crypto_asset(symbol, user):
    normalized_symbol = str(symbol).upper()
    result = resolve_or_create_asset(
        user=user,
        isin=_crypto_asset_identifier(normalized_symbol),
        currency="USD",
        submitted_fields={
            "type": ASSET_TYPE_CRYPTO,
            "name": normalized_symbol,
            "ticker": normalized_symbol[:10],
            "exposure": "FX" if normalized_symbol in STABLECOINS else "Commodity",
            "yahoo_symbol": f"{normalized_symbol}-USD",
        },
        mode="silent",
    )
    return result.asset
```

(c) Rewrite `fetch_crypto_usd_price_from_yahoo` (lines 212-243) to look up the asset's `yahoo_symbol`:

```python
def fetch_crypto_usd_price_from_yahoo(symbol, price_date):
    """Fetch a USD crypto close price from Yahoo Finance for import-time valuation.

    Reads the coin's ``yahoo_symbol`` (e.g. ``"BTC-USD"``) from its ``Assets``
    row. Coins without a ``yahoo_symbol`` return ``None`` (unpriced).
    """
    normalized = str(symbol).upper()
    asset = Assets.objects.filter(type="Crypto", name=normalized).first()
    if asset is None or not asset.yahoo_symbol:
        return None
    yahoo_symbol = asset.yahoo_symbol

    start_date = price_date - timedelta(days=6)
    end_date = price_date + timedelta(days=1)
    try:
        history = yf.Ticker(yahoo_symbol).history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            auto_adjust=False,
        )
    except Exception as exc:
        logger.warning("Could not fetch %s price from Yahoo: %s", yahoo_symbol, exc)
        return None

    if history.empty or history["Close"].isnull().all():
        logger.warning("Yahoo returned no close price data for %s", yahoo_symbol)
        return None
    requested_date_rows = history[history.index.date == price_date]
    close_values = requested_date_rows["Close"].dropna()
    if close_values.empty:
        logger.warning("Yahoo returned no close price for %s on %s", yahoo_symbol, price_date)
        return None
    close = close_values.iloc[-1]
    return Decimal(str(close))
```

Also ensure `Assets` is imported at the top (it is — line 14).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/services/test_crypto_class.py -v`
Expected: PASS.

- [ ] **Step 5: Backfill `yahoo_symbol` on existing coin rows**

Create a Django data migration to backfill existing crypto `Assets` rows that lack a `yahoo_symbol`. First check whether any exist:

Run: `uv run python -c "from common.models import Assets; rows = Assets.objects.filter(type='Crypto', yahoo_symbol__isnull=True); print(rows.count(), [a.name for a in rows])"`

If count > 0, create `backend/common/migrations/00XX_backfill_crypto_yahoo_symbol.py`. First determine the previous migration and the next number:

Run: `ls backend/common/migrations/ | grep -E "^[0-9]" | sort | tail -3`
The new file's number is one higher than the highest existing; its `dependencies` references the current highest. For example, if the highest is `0090_last.py`, the new file is `0091_backfill_crypto_yahoo_symbol.py` and `dependencies = [("common", "0090_last")]` (use the actual name without `.py`).

**This is a data migration (no schema change) — still protected; flag for review.** The migration:

```python
from django.db import migrations


def backfill_crypto_yahoo_symbol(apps, schema_editor):
    Assets = apps.get_model("common", "Assets")
    for asset in Assets.objects.filter(type="Crypto", yahoo_symbol__isnull=True):
        asset.yahoo_symbol = f"{asset.name}-USD"
        asset.save(update_fields=["yahoo_symbol"])


def reverse_backfill(apps, schema_editor):
    # No-op reverse (we can't know the original null state reliably).
    pass


class Migration(migrations.Migration):
    dependencies = [
        # Replace with the actual previous migration name (see instruction above).
        ("common", "<highest_existing_migration_number_name>"),
    ]
    operations = [
        migrations.RunPython(backfill_crypto_yahoo_symbol, reverse_backfill),
    ]
```

If the count is 0 (fresh dev DB), skip the migration and document in the commit that no backfill was needed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/unit/services/test_crypto_class.py backend/common/migrations/
git commit -m "feat(crypto): per-asset yahoo_symbol for price fetching (BTC/ETH/TRUMP)"
```

---

## Task 9: Full regression run + final verification

**Files:** None (verification only).

- [ ] **Step 1: Run the entire backend test suite**

Run: `uv run python -m pytest -x --tb=short`
Expected: PASS (no failures). If a pre-existing test encodes the old commission model and breaks, read it, confirm it's testing the reverted behavior, and update per Task 7's approach. Do NOT silence failures.

- [ ] **Step 2: Verify the spec's regression scenario**

Re-read spec §8 "Regression fixtures." Confirm each numeric scenario is covered by a test added in Tasks 1-8:
- BTC 0.5 @ $60,000 in Crypto bucket; AAPL 10 @ $150 in Securities; $1,000 cash → Total $32,500 → covered by Task 3's `test_nav_three_buckets_counted_once`.
- BTC→EUR FX conversion → covered by Task 2's `test_get_rate_btc_to_eur_chains_through_usd`.
- Cross-currency commission separates into its own row, position reconciles → covered by Tasks 5 & 6.

- [ ] **Step 3: Verify no double-count**

Manually confirm via a quick shell check (using the Task 3 fixture pattern) that BTC appears in exactly one bucket:

Run: `uv run python -c "import django; django.setup(); ..."` (or rely on the Task 3 test which already asserts `crypto_keys == ["Crypto"]`).

- [ ] **Step 4: Update AGENTS.md if any protected-path note changed**

Skim `AGENTS.md` "Protected code" section. If Task 6 added `TRANSACTION_TYPE_CRYPTO_COMMISSION` and the commission-row persistence is a new financial behavior, consider whether a note is warranted. Likely no change needed (the protected globs already cover `services/crypto_exchange.py`).

- [ ] **Step 5: Final commit (if any cleanup)**

If the regression run surfaced cleanup, commit it. Otherwise skip.

---

## Notes for the implementer

- **Protected code:** Tasks 2, 3, 5, 6, 7, 8 touch protected paths (`fx.get_rate`, `nav.NAV_at_date`, `crypto_exchange` importer logic, `transactions.total_cash_flow`). Each must ship with its unit test + regression fixture. The PR for this whole plan (or per-task PRs) needs the `needs-approval` label.
- **Order matters:** Tasks 1→2→3 establish the Crypto class with the OLD commission model still in place (no behavior change to existing trades — BTC just moves buckets). Tasks 4→5→6→7 do the revert. Task 8 is independent and can land anytime after Task 1. Task 9 is the gate.
- **Option legs are untouched** (spec §5.5 / decision 7). Do NOT modify `normalize_okx_option_fill` or the option-settlement path. The #33 fix is a separate spec (sub-project 4). **Regression guard:** the existing `test_normalize_okx_option_fill_sell_put` (in `test_crypto_exchange_import.py:700`) and `test_normalize_bybit_option_execution_buy_call` (line 673) must still PASS after Tasks 5-7 — if either breaks, the spot revert has leaked into the option path and must be fixed before proceeding. Run them explicitly in Task 9 Step 1.
- **Decimal everywhere.** If you find yourself writing `float(...)`, stop.

---

## Task 9b: Option-leg regression guard (spec §5.5)

**Files:**
- Test: `backend/tests/unit/imports/test_crypto_exchange_import.py` (existing tests, no new file)

**Purpose:** Explicitly confirm the spot-model revert does NOT change option-fill behavior. This is the guard for spec decision 7.

- [ ] **Step 1: Run the option tests in isolation**

Run: `uv run python -m pytest tests/unit/imports/test_crypto_exchange_import.py -k "option" -v`
Expected: PASS — `test_normalize_bybit_option_execution_buy_call`, `test_normalize_okx_option_fill_sell_put`, `test_normalize_bybit_option_settlement_exercised`, `test_normalize_okx_option_settlement` all pass unchanged.

- [ ] **Step 2: If any option test FAILS, the revert leaked — fix before finishing**

The option normalizers (`normalize_okx_option_fill`, `normalize_bybit_option_execution`, `normalize_*_option_settlement`) must not have been touched by Tasks 4-8. If a test fails, inspect which change broke it: most likely Task 5's `_spot_legs` rewrite was accidentally applied to option legs, or Task 6's commission-row persistence was applied to the option `fee` dict. Restore the option-specific behavior. Do NOT update the option test assertions to match a new behavior — option behavior is frozen per spec §5.5.

- [ ] **Step 3: Add an explicit frozen-behavior comment to the option tests**

In `test_crypto_exchange_import.py`, above `test_normalize_okx_option_fill_sell_put` (around line 700), add:

```python
# FROZEN per spec 2026-08-06 §5.5 (crypto-as-currency foundation): option-fill
# behavior is unchanged in the foundation spec. The calculated-premium +
# collateral-transfer model lands in sub-project 4 (options accounting). If this
# test breaks during the foundation work, the spot revert has leaked into options.
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/imports/test_crypto_exchange_import.py
git commit -m "test(crypto): freeze option-fill behavior for foundation spec (§5.5 guard)"
```
