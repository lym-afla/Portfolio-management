# Sub-Project 4 Follow-Ups Round 3: IRR Transfer Cash-Flow, Option Realized FX, Cash-Column Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 issues found after round-2 fixes + restart: (1) TRUMP IRR shows `+63.7%` (asset-level IRR is actually `-99.97%`) because `_calculate_cash_flow` treats neutral crypto transfers as priced trades; (2) option realized_gl shows `$0` because `_realized_option_close` returns BTC not USD even when `currency='USD'` is requested; (3) BTC appears as a column on the Transactions page because `BalanceTracker` registers every transaction's currency including commodity crypto coins (BTC/TRUMP), not just cash currencies.

**Architecture:** Three targeted fixes on `feat/crypto-option-accounting`. (1) `_calculate_cash_flow` returns `Decimal(0)` for crypto transfers (they're neutral — no economic cash flow). (2) `_realized_option_close` FX-converts its result to the target currency when `currency` is passed. (3) `BalanceTracker` only registers cash currencies (fiat codes + stablecoins USDT/USDC) as columns, skipping commodity crypto coins.

**Tech Stack:** Python 3, Django 4, `Decimal` (`ROUND_HALF_UP`), pytest, uv project mode. All commands from `backend/` via `uv run`.

**Spec context:** Round-3 follow-ups to sub-project 4, found after round-2 (`docs/superpowers/plans/2026-08-08-sub4-followups-r2-option-pricing-basis-premium.md`).

## Global Constraints

- **Numeric safety:** `Decimal`, never `float`. `ROUND_HALF_UP`.
- **Protected logic (PR with `needs-approval`):** `nav.py` (`_calculate_cash_flow`, `IRR`), `realized.py` (`_realized_option_close`). `core/balance_tracker.py` is table-builder utility (protected-adjacent). No schema change, no migrations.
- **Transfer policy:** `TRANSFER_DISPOSITION_ENABLED = False` — all crypto transfers neutral (no realized G/L, no IRR cash flow).
- **Cash vs crypto:** "Cash" currencies = fiat codes (USD, EUR, RUB, GBP, CHF, CNY) + stablecoins (USDT, USDC). Commodity crypto coins (BTC, ETH, TRUMP) are NOT cash — they should not appear in Cash flow/Balance columns.
- **Branch:** `feat/crypto-option-accounting` (appends to PR #40).
- **Commands:** `cd backend && uv run python -m pytest ...`. Run BOTH `tests/unit/` AND `tests/integration/` per task. Note: the Bash shell may be `cmd.exe` (Windows) — use Windows paths (`D:\...`) and the venv python (`D:\Developing\Portfolio-management\backend\.venv\Scripts\python.exe`) if `uv` isn't on PATH.

---

## File Structure

**Modified files:**
- `backend/services/nav.py` — `_calculate_cash_flow`: return `Decimal(0)` for crypto transfer types.
- `backend/services/realized.py` — `_realized_option_close`: FX-convert the realized G/L to the target currency when requested.
- `backend/core/balance_tracker.py` — `_update_regular_transaction`: only register cash currencies (fiat + stablecoins) as tracked columns; skip commodity crypto coins.

**New/updated tests:**
- `backend/tests/unit/calculations/test_irr_option_paths.py` (or a transfer-IRR test) — assert transfers contribute `cf=0` to IRR.
- `backend/tests/unit/calculations/test_realized_option_paths.py` — assert option realized is FX-converted to USD when `currency='USD'`.
- `backend/tests/unit/core/test_balance_tracker.py` (create) — assert BTC/TRUMP transactions don't create columns; USDT/USD do.

---

## Task 1: Crypto transfers contribute `cf=0` to IRR (fixes TRUMP IRR)

**Files:**
- Modify: `backend/services/nav.py` — `_calculate_cash_flow` (~L564-617). The crypto-trade/transfer branch (~L574-583) currently computes `cf = -qty × price` for ALL of `CRYPTO_TRADE_IN/OUT` + `CRYPTO_TRANSFER_IN/OUT`. Split: transfers return `Decimal(0)`; trades keep the formula.
- Test: extend `backend/tests/unit/calculations/test_irr_option_paths.py` (or a focused transfer-IRR test).

**Interfaces:**
- Produces: `_calculate_cash_flow` returns `Decimal(0)` for `CRYPTO_TRANSFER_IN/OUT`, so IRR's cash-flow list excludes transfer movements.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/calculations/test_irr_option_paths.py` (or create a new test class):

```python
@pytest.mark.nav
@pytest.mark.unit
class TestTransferCashFlowIsZero:
    """Crypto transfers are neutral — they contribute cf=0 to IRR, not -qty*price.

    Previously _calculate_cash_flow treated transfers like trades (cf = -qty*price),
    so a transfer-out with price=45.503 contributed +30.92 to IRR, corrupting the
    XIRR (TRUMP showed +63.7% when the asset-level IRR is actually -99.97%).
    """

    def test_transfer_out_cash_flow_is_zero(self, user, account):
        from datetime import datetime, timezone
        from common.models import Assets, Transactions
        from services.nav import _calculate_cash_flow
        from constants import TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:T", name="TESTCOIN",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        tx = Transactions.objects.create(
            investor=user, account=account, security=coin, currency="TESTCOIN",
            type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
            date=datetime(2025, 1, 19, tzinfo=timezone.utc),
            quantity=Decimal("-0.679619700"), price=Decimal("45.503"),
        )
        assert _calculate_cash_flow(tx) == Decimal("0")

    def test_trade_in_cash_flow_unchanged(self, user, account):
        # A real trade (buy) still computes cf = -qty*price.
        from datetime import datetime, timezone
        from common.models import Assets, Transactions
        from services.nav import _calculate_cash_flow
        from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:T2", name="TESTCOIN2",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        tx = Transactions.objects.create(
            investor=user, account=account, security=coin, currency="USDT",
            type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
            date=datetime(2025, 1, 19, tzinfo=timezone.utc),
            quantity=Decimal("0.6803"), price=Decimal("73.209"),
        )
        # cf = -qty*price = -0.6803 * 73.209 = -49.80...
        assert _calculate_cash_flow(tx) == Decimal("-0.6803") * Decimal("73.209")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_irr_option_paths.py::TestTransferCashFlowIsZero -v`
Expected: FAIL — `test_transfer_out_cash_flow_is_zero` gets `30.924...` (the `-qty*price` value), not `0`.

- [ ] **Step 3: Make transfers return cf=0**

In `backend/services/nav.py`, `_calculate_cash_flow` (~L574). The current branch handles all 4 crypto types together. Split transfers out to return 0 first:

```python
    if transaction.type in [
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    ]:
        # Transfers are neutral internal moves (no economic cash flow). They
        # must contribute cf=0 to IRR, not -qty*price (which would corrupt
        # XIRR for assets with transfers — the TRUMP +63.7% bug). Transfers
        # may carry a price (the coin's spot) but that's not a cash flow.
        return Decimal(0)

    if transaction.type in [
        TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    ]:
        if transaction.quantity is not None and transaction.price is not None:
            cf = -transaction.quantity * transaction.price
            # ... (existing commission + rounding logic unchanged)
```

(Read the current block; the only structural change is splitting the 4-type list into two: transfers return 0 early; trades keep the existing formula + commission + rounding.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_irr_option_paths.py::TestTransferCashFlowIsZero -v`
Expected: PASS.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. (IRR tests that included transfers may need their expected values updated if they asserted the old transfer-cf behavior — update them.)

- [ ] **Step 6: Commit**

```bash
git add backend/services/nav.py backend/tests/unit/calculations/test_irr_option_paths.py
git commit -m "fix(nav): crypto transfers contribute cf=0 to IRR

_calculate_cash_flow treated CRYPTO_TRANSFER_IN/OUT like trades (cf = -qty*price),
so transfers carrying a spot price contributed spurious cash flows to IRR.
TRUMP showed +63.7% IRR (asset-level is actually -99.97%) because the transfer
rows added +/-30.9 to the cash-flow list. Transfers are neutral internal moves
— return cf=0. Trades keep the formula."
```

---

## Task 2: FX-convert option realized G/L to target currency (fixes option realized $0)

**Files:**
- Modify: `backend/services/realized.py` — `_realized_option_close` (~L108-172). Currently returns the realized in the settle coin (BTC) with `fx_effect=0`. When the caller passes `currency` (e.g. 'USD'), the result should be FX-converted.
- Test: `backend/tests/unit/calculations/test_realized_option_paths.py` — assert option realized is USD when `currency='USD'`.

**Interfaces:**
- Consumes: the `currency` (target currency) and `account_ids` params passed to `realized_gain_loss`, which it must thread to `_realized_option_close`.
- Produces: `_realized_option_close` returns `{price_appreciation, fx_effect, total}` with `total` in the target currency when `currency` is passed.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/calculations/test_realized_option_paths.py`:

```python
@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestOptionRealizedFXConversion:
    """Option realized G/L must FX-convert to the target currency when 'currency'
    is passed. The option settles in BTC (+0.00014322); when the closed-positions
    table requests USD, the realized should be in USD (~\$9 at BTC=60000), not the
    raw BTC value (which displays as \$0.00)."""

    def test_option_realized_converted_to_usd(self, user, account):
        from datetime import datetime, timezone
        from common.models import Assets, Prices, OptionMetadata, Transactions
        from services.realized import realized_gain_loss
        # Pin BTC-USD at 60000
        btc = Assets.objects.create(type="Crypto", ISIN="CRYPTO:BTCFX", name="BTCFX",
                                     currency="USD", exposure="Commodity", yahoo_symbol="BTCFX-USD")
        btc.investors.add(user)
        Prices.objects.create(security=btc, date=datetime(2026,1,1,tzinfo=timezone.utc),
                              price=Decimal("60000"))
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("0.000154"),
        )
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        # Native BTC: +0.00014322. In USD at 60000: ~8.59.
        r_btc = realized_gain_loss(opt, date(2026,6,6), investor=user, account_ids=[account.id])
        r_usd = realized_gain_loss(opt, date(2026,6,6), investor=user, account_ids=[account.id], currency="USD")
        assert r_btc["all_time"]["total"] == Decimal("0.00014322")
        # USD-converted should be materially different from the BTC value (not 0.00014322).
        assert r_usd["all_time"]["total"] > Decimal("1")  # ~8.59, not 0.00014322
```

NOTE: The FX conversion BTC→USD needs a BTC price. The test pins BTC-USD at 60000 via a Prices row on a BTC asset. Check how `realized.py` resolves the FX rate for the option's settle coin (BTC) — it may need the option's `underlying_asset` or a direct `get_rate("BTC", "USD", date)`. The implementer should verify the FX path works with the pinned price; if the option's settle coin BTC doesn't resolve via the FX graph, the test setup may need adjustment (e.g. a `get_rate("BTC", "USD", ...)` fixture). Document any setup deviation.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_realized_option_paths.py::TestOptionRealizedFXConversion -v`
Expected: FAIL — `r_usd["all_time"]["total"]` is `0.00014322` (not converted), so `> 1` fails.

- [ ] **Step 3: FX-convert the option realized**

In `backend/services/realized.py`, `_realized_option_close` (~L108-172). The function currently returns:
```python
    return {
        "price_appreciation": realized_local,
        "fx_effect": Decimal(0),
        "total": realized_local,
    }
```
where `realized_local` is in the settle coin (BTC). Add an FX conversion when the caller requests a target currency. The function needs the target currency and the transaction date (for the FX rate). Thread `currency` (the target) from `calculate_position_gain_loss` (which receives it from `realized_gain_loss`'s `currency` param).

The cleanest approach: in `_realized_option_close`, accept `target_currency` (the `realized_gain_loss` `currency` param, which flows into `calculate_position_gain_loss`). If `target_currency` is set and differs from the option's settle coin, FX-convert `realized_local` via `_fx_get_rate(settle_coin, target_currency, transaction.date)`:

```python
    # FX-convert to the target currency when requested (e.g. closed-positions
    # table requests USD). The realized is computed in the option's settle coin
    # (BTC); without conversion the table shows $0.00 for a +0.00014322 BTC gain.
    settle_ccy = (transaction.currency or "").upper()
    if target_currency and target_currency.upper() != settle_ccy:
        fx = _fx_get_rate(settle_ccy, target_currency, transaction.date)["FX"]
        realized_target = realized_local * fx
        fx_effect = realized_target - realized_local
    else:
        realized_target = realized_local
        fx_effect = Decimal(0)
    return {
        "price_appreciation": realized_local,
        "fx_effect": fx_effect,
        "total": realized_target,
    }
```

Thread `target_currency` through: `calculate_position_gain_loss` already receives `currency` (it's a closure var in `realized_gain_loss`). Pass it to `_realized_option_close(asset, transaction, position, investor, account_ids, start, target_currency=currency)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_realized_option_paths.py::TestOptionRealizedFXConversion -v`
Expected: PASS — `r_usd["all_time"]["total"]` is ~8.59 (> 1).

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/realized.py backend/tests/unit/calculations/test_realized_option_paths.py
git commit -m "fix(realized): FX-convert option realized G/L to target currency

_realized_option_close returned the realized in the settle coin (BTC) with
fx_effect=0, ignoring the 'currency' param. The closed-positions table
requests USD, so the +0.00014322 BTC option profit displayed as \$0.00.
Now FX-converts to the target currency via get_rate(settle_coin, target, date)
when 'currency' is passed."
```

---

## Task 3: BalanceTracker only tracks cash currencies (fixes BTC column on Transactions page)

**Files:**
- Modify: `backend/core/balance_tracker.py` — `_update_regular_transaction` (~L68-80). Currently adds `transaction.currency` to `self.currencies` (the column set) for every transaction. Only cash currencies (fiat + stablecoins) should be columns; commodity crypto coins (BTC, TRUMP) should not.
- Test: `backend/tests/unit/core/test_balance_tracker.py` (create).

**Interfaces:**
- Consumes: a way to distinguish cash currencies from commodity crypto coins. Use `services.crypto.is_crypto_code(code)` (True for BTC/TRUMP/ETH, False for USD/USDT/EUR) combined with the stablecoin set — OR a simpler check: a currency is "cash" if it's a fiat code or a stablecoin (USDT/USDC). Commodity crypto coins (BTC, ETH, TRUMP) are NOT cash.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/core/test_balance_tracker.py`:

```python
"""Tests for core/balance_tracker.py — cash-currency column filtering."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from core.balance_tracker import BalanceTracker


@pytest.mark.django_db
class TestBalanceTrackerCashColumns:
    def test_btc_transaction_does_not_create_btc_column(self, user):
        """A BTC-denominated transaction must NOT register BTC as a balance column.
        BTC is a commodity crypto coin, not cash. Only fiat + stablecoins (USDT/USDC)
        should appear as Cash flow/Balance columns on the Transactions page."""
        broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        btc = Assets.objects.create(type="Crypto", ISIN="CRYPTO:BTCBT", name="BTCBT",
                                    currency="USD", exposure="Commodity")
        btc.investors.add(user)
        tx = Transactions.objects.create(
            investor=user, account=account, security=btc, currency="BTC",
            type="Crypto transfer out",
            date=datetime(2026, 6, 8, tzinfo=timezone.utc),
            quantity=Decimal("-0.02"),
        )
        bt = BalanceTracker(number_of_digits=8)
        bt.update(tx)
        currencies = bt.get_currencies()
        assert "BTC" not in currencies, f"BTC should not be a cash column; got {currencies}"

    def test_usdt_transaction_creates_usdt_column(self, user):
        broker = Brokers.objects.create(investor=user, name="OKX2", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading2")
        tx = Transactions.objects.create(
            investor=user, account=account, security=None, currency="USDT",
            type="Cash in",
            date=datetime(2026, 6, 8, tzinfo=timezone.utc),
            cash_flow=Decimal("100"),
        )
        bt = BalanceTracker(number_of_digits=8)
        bt.update(tx)
        assert "USDT" in bt.get_currencies()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/core/test_balance_tracker.py -v`
Expected: FAIL — `test_btc_transaction_does_not_create_btc_column` gets `["BTC"]` in currencies.

- [ ] **Step 3: Filter to cash currencies in BalanceTracker**

In `backend/core/balance_tracker.py`, `_update_regular_transaction` (~L68-80). Add a helper to check if a currency is "cash" (fiat or stablecoin), and skip non-cash currencies (don't add them to `self.balances` or `self.currencies`).

Add a module-level constant + helper:
```python
# Cash currencies tracked in the Transactions-page balance columns.
# Fiat codes + stablecoins (USDT/USDC). Commodity crypto coins (BTC, ETH, TRUMP)
# are NOT cash — they're Crypto-class assets valued separately.
STABLECOIN_CURRENCIES = {"USDT", "USDC"}
FIAT_CURRENCIES = {"USD", "EUR", "GBP", "RUB", "CHF", "CNY", "AED", "HKD", "JPY", "KRW", "SGD"}

def _is_cash_currency(currency: str) -> bool:
    """Return True if the currency code is a cash currency (fiat or stablecoin)."""
    c = (currency or "").upper()
    return c in FIAT_CURRENCIES or c in STABLECOIN_CURRENCIES
```

Then in `_update_regular_transaction`, guard the currency registration:
```python
    def _update_regular_transaction(self, transaction) -> None:
        currency = transaction.currency
        # Only track cash currencies (fiat + stablecoins). Commodity crypto coins
        # (BTC, TRUMP) are Crypto-class assets, not cash — they shouldn't appear
        # as columns in the Cash flow/Balance table.
        if not _is_cash_currency(currency):
            return
        if currency not in self.balances:
            self.balances[currency] = Decimal(0)
        self.currencies.add(currency)
        # ... (existing total_cash_flow + balance update)
```

NOTE: The `FIAT_CURRENCIES` set should cover the app's supported fiat codes. Check `ALL_CURRENCY_CHOICES` in `constants.py` or `models.py` for the authoritative list and use it instead of a hardcoded set if available. If a `CURRENCY_CHOICES`/`ALL_CURRENCIES` constant exists, derive `FIAT_CURRENCIES` from it (minus the stablecoins, which are crypto-typed but cash-pegged).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/core/test_balance_tracker.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. (Existing transactions-page tests may assert BTC/other-crypto columns existed — update them if they break, since crypto columns should no longer appear.)

- [ ] **Step 6: Commit**

```bash
git add backend/core/balance_tracker.py backend/tests/unit/core/test_balance_tracker.py
git commit -m "fix(balance_tracker): only track cash currencies as balance columns

BalanceTracker registered every transaction's currency as a balance column,
including commodity crypto coins (BTC, TRUMP). BTC appeared as a column on
the Transactions page Cash flow/Balance table even though BTC is a Crypto
asset, not cash. Only fiat + stablecoins (USDT/USDC) are tracked as cash
columns now."
```

---

## Task 4: Verify against live data + push

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `cd backend && uv run python -m pytest --no-cov -q`
Expected: all pass.

- [ ] **Step 2: Verify the 3 fixes via Django shell (data already re-imported)**

```bash
cd backend && .venv\Scripts\python.exe -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='portfolio_management.settings'; import django; django.setup(); ..."
```
(Use the venv python directly if uv isn't on PATH.) Check:
- TRUMP IRR is negative (was +63.7%).
- Option realized_gl in the table is positive USD (was $0).
- BalanceTracker currencies exclude BTC (use a quick instantiation).

- [ ] **Step 3: Restart dev server + refresh UI**

The user restarts `uv run python run_uvicorn.py` and confirms: TRUMP IRR negative; option realized positive; no BTC column on Transactions page.

- [ ] **Step 4: Push to PR #40**

```bash
git push origin feat/crypto-option-accounting
```

---

## Self-Review

**1. Issue coverage:**
- Issue 1 (TRUMP IRR +63.7%) → Task 1 (`_calculate_cash_flow` transfers return 0).
- Issue 2 (option realized $0) → Task 2 (`_realized_option_close` FX-convert).
- Issue 3 (BTC column on Transactions page) → Task 3 (BalanceTracker cash-only columns).

**2. Placeholder scan:** Task 2 Step 1 notes the FX-path setup may need adjustment (the implementer verifies the BTC price resolves). Task 3 Step 3 notes `FIAT_CURRENCIES` should derive from `ALL_CURRENCY_CHOICES` if available. Both are concrete instructions, not placeholders.

**3. Consistency:** `_is_cash_currency` in Task 3 uses the same `STABLECOIN_CURRENCIES = {"USDT", "USDC"}` as `crypto_exchange.py`. The `_realized_option_close` FX conversion uses `_fx_get_rate` (already imported in realized.py). The `_calculate_cash_flow` split reuses the existing commission/rounding logic for trades.
