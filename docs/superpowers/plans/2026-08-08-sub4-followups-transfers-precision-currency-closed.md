# Sub-Project 4 Follow-Ups: Transfer Neutrality, Precision, Currency, Closed-Positions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four issues found when re-importing OKX data against sub-project 4 (PR #40): (1) BTC appearing in the Cash flows/balance column, (2) the BTC option missing from Closed positions, (3) TRUMP IRR incorrect, (4) BTC showing a -0.0002 position with spurious realized gain + IRR N/R — plus adopt a currency-aware rounding policy so crypto-scale values display correctly.

**Architecture:** Five independent fixes on the `feat/crypto-option-accounting` branch. (A) Revert the crypto-transfer disposition logic to all-neutral until #29's two-account model lands (fixes #3, #4, and the spurious realized gains). (B) Make rounding precision currency-aware via `broker.cash_precision` (8 for crypto, 2 for fiat) at every hardcoded 2dp spot. (C) Fix the importer's transfer-leg currency bug (transfer rows were mislabeled `USD` → fixes #1). (D) Guard the closed-positions table builder against `None` prices (the option settlement row's OTM terminal price `0` resolves to `None` via `get_price` → `None * Decimal` TypeError → row dropped → fixes #2). (E) Update the Task-12 transfer tests to reflect the revert.

**Tech Stack:** Python 3, Django 4, `Decimal` (`ROUND_HALF_UP`), pytest, uv project mode. All commands from `backend/` via `uv run`.

**Spec context:** These are scoped fixes to `docs/superpowers/specs/2026-08-07-crypto-option-accounting-and-realized-gain-design.md` (sub-project 4), discovered during live re-import testing. The transfer revert and the precision policy are user-approved (see session).

## Global Constraints

- **Numeric safety:** Always `Decimal` for money/price — never `float`. Rounding `ROUND_HALF_UP`.
- **Protected logic (PR with `needs-approval`):** `realized.py` (`realized_gain_loss`, `get_economic_basis`, `unrealized_gain_loss`), `transactions.py`, `nav.py`, `crypto_exchange.py`, `importer.py`, `accounts.py`. Also `core/tables_utils.py` and `core/positions_utils.py` (financial-table builders). **No `models.py` schema change, no migrations.**
- **Precision policy (user-approved):** rounding is **currency-aware via `broker.cash_precision`** (8 for crypto brokers OKX/Bybit per migration `0098`, 2 for fiat). Fiat outputs unchanged. The existing canonical pattern is `transactions.py:283-288` / `nav.py:589-598` — copy it.
- **Transfer policy (user-approved):** ALL crypto transfers are neutral (position += qty, no realized G/L) until #29 lands. Task-12's `_transfer_is_matched` distinction is reverted for now; the helper stays in the code (gated off) for #29 to reactivate.
- **Branch:** Continue on `feat/crypto-option-accounting` (the PR #40 vehicle). These commits append to that PR.
- **Commands:** `cd backend && uv run python -m pytest ...`. Run the FULL `tests/unit/` tree per task (lesson from sub-project 4: scoped runs miss cross-dir regressions).

---

## File Structure

**Modified files:**
- `backend/services/realized.py` — (1) revert the unmatched-transfer disposition in `realized_gain_loss` to all-neutral; (2) make the three rounding spots (L748, L1269, L1428-1430) currency-aware.
- `backend/services/accounts.py` — make the `balance()` rounding (L109) currency-aware.
- `backend/services/crypto_exchange.py` — fix transfer-leg currency (L475): use the coin itself, not the missing `quote_currency`.
- `backend/core/tables_utils.py` — guard the entry/exit value loops (L185, L198) against `None` prices.
- `backend/tests/unit/calculations/test_realized_transfer_paths.py` — update Task-12's tests to reflect all-neutral.
- `backend/tests/unit/calculations/test_realized_option_paths.py` — option unrealized-guard test already exists; may need a closed-positions-style test.

**New test files:**
- `backend/tests/unit/calculations/test_precision_paths.py` — currency-aware rounding regression tests.
- `backend/tests/unit/core/test_tables_option_closed.py` — closed-positions builder test for the option (issue #2).

---

## Task Interfaces

- **`realized.py` rounding helper** (Task 2): a module-level `_cash_precision_for(asset, account_ids) -> int` that resolves `broker.cash_precision` from `account_ids` (falls back to 2 when `account_ids` is None/empty or the broker lookup fails). Used by the three rounding spots.
- **`realized.py` transfer revert** (Task 1): the neutral-transfer branch at ~L913 returns to unconditional `position += quantity; continue`. The `_transfer_is_matched` helper + `is_unmatched_out/in` logic is removed (or gated behind a constant `TRANSFER_DISPOSITION_ENABLED = False` for #29 to flip later).
- **`crypto_exchange.py` currency fix** (Task 3): line 475 reads `currency` from the leg's own asset for transfer legs (no `quote_currency` key exists).
- **`tables_utils.py` None guard** (Task 4): `get_price(transaction) or Decimal(0)` at L185 + L198.

---

## Task 1: Revert crypto-transfer disposition to all-neutral

**Files:**
- Modify: `backend/services/realized.py` (the neutral-transfer branch ~L912-930, and the `is_unmatched_out`/`is_unmatched_in` extensions ~L932-964)
- Test: `backend/tests/unit/calculations/test_realized_transfer_paths.py`

**Interfaces:**
- Produces: all crypto transfers neutral again (position += qty, no G/L). `_transfer_is_matched` may stay (unused) or be removed; the `is_unmatched_out/in` logic is removed.

- [ ] **Step 1: Update the failing test to expect all-neutral**

In `backend/tests/unit/calculations/test_realized_transfer_paths.py`, the `TestUnmatchedTransferOutIsDisposition` class asserts the transfer realizes G/L. **Replace it** with a class asserting the transfer is now NEUTRAL (the revert). Also keep `TestMatchedTransferIsNeutral` (unchanged). Replace the body of `TestUnmatchedTransferOutIsDisposition`:

```python
@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestUnmatchedTransferIsNeutralUntilTwoAccountModel:
    """Until issue #29's two-account model lands, ALL crypto transfers are
    neutral — including unmatched one-sided moves (OKX Funding↔Trading internal
    transfers, which dominate the user's data and are NOT external withdrawals).
    The matched-vs-unmatched distinction (Task 12) is reverted because pre-#29
    we cannot distinguish internal moves from genuine external flows.
    """

    def test_unmatched_out_is_neutral_no_realized(self, user, account):
        btc = _make_btc(user)
        Transactions.objects.create(
            investor=user, account=account, security=btc, currency="USD",
            type="Crypto trade in",
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("1"), price=Decimal("60000"),
        )
        # Unmatched transfer out (no import_group_id sibling) — now neutral.
        Transactions.objects.create(
            investor=user, account=account, security=btc, currency="BTC",
            type="Crypto transfer out",
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            quantity=Decimal("-0.5"),
        )
        result = realized_gain_loss(btc, date(2026, 3, 1), investor=user)
        # No realized G/L from the transfer — neutral.
        assert result["all_time"]["total"] == Decimal("0")
```

(Adjust `_make_btc` to exist if it doesn't — it's already in this file from Task 12.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_realized_transfer_paths.py -v`
Expected: FAIL — the current code treats the unmatched transfer as a disposition (realizes G/L).

- [ ] **Step 3: Revert the transfer logic to all-neutral**

In `backend/services/realized.py`, find the neutral-transfer branch (around L912-930, modified by Task 12). Restore it to the simple all-neutral form, and remove the `is_unmatched_out`/`is_unmatched_in` extensions to `is_position_reducing`/`closing_quantity`. Add a module-level constant so #29 can reactivate later:

Near the top of `realized.py` (after imports), add:
```python
# Until issue #29's two-account model lands, ALL crypto transfers are neutral
# (position += quantity, no realized G/L). OKX Funding↔Trading internal moves
# dominate real data and are indistinguishable from external withdrawals
# pre-#29. Set True to reactivate the matched-vs-unmatched disposition logic
# (the _transfer_is_matched helper is retained for that future use).
TRANSFER_DISPOSITION_ENABLED = False
```

Then the neutral-transfer branch becomes:
```python
            if _transactions_is_neutral_transfer_transaction(transaction):
                # Pre-#29: all crypto transfers are neutral (internal wallet
                # moves cannot be distinguished from external flows). When
                # TRANSFER_DISPOSITION_ENABLED is True (#29), unmatched
                # transfers fall through to the disposal/entry branches below.
                if TRANSFER_DISPOSITION_ENABLED and not _transfer_is_matched(
                    transaction, investor, account_ids
                ):
                    logger.debug(
                        "Unmatched %s for asset %s: treating as disposition/entry.",
                        transaction.type, getattr(asset, "name", asset),
                    )
                    # fall through to is_position_reducing logic below
                else:
                    position += transaction.quantity
                    logger.debug(f"Position after neutral transfer: {position}")
                    continue
```

And restore `is_position_reducing` / `closing_quantity` to their original (pre-Task-12) form — remove the `is_unmatched_out`/`is_unmatched_in` branches, keeping only the original `is_disposal_transaction`/`is_paid_entry_transaction` checks. Keep the `tx_price = transaction.price if transaction.price is not None else Decimal(0)` guard at the G/L computation (it's harmless and defensive). Keep `_transfer_is_matched` defined (unused while the flag is False).

- [ ] **Step 4: Run the transfer tests + full calculations suite**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/ -v`
Expected: PASS. The existing `test_crypto_rewards.py::test_crypto_trade_out_realizes_gain_but_transfer_out_is_neutral` (modified in Task 12 to add a sibling leg) should now pass WITHOUT the sibling leg — but leave it as-is (the sibling makes it matched, which is also neutral; don't churn it).

- [ ] **Step 5: Run the FULL unit suite (regression gate)**

Run: `cd backend && uv run python -m pytest tests/unit/ --no-cov -q`
Expected: all pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add backend/services/realized.py backend/tests/unit/calculations/test_realized_transfer_paths.py
git commit -m "fix(realized): revert crypto-transfer disposition to all-neutral until #29

Task-12's matched-vs-unmatched distinction treated OKX Funding↔Trading
internal transfers as dispositions (realized G/L on wallet moves),
corrupting TRUMP/BTC IRR and producing spurious realized gains. Until
#29's two-account model can identify genuine external flows, ALL crypto
transfers are neutral again. The _transfer_is_matched helper is retained,
gated behind TRANSFER_DISPOSITION_ENABLED=False for #29 to reactivate."
```

---

## Task 2: Currency-aware rounding via `broker.cash_precision`

**Files:**
- Modify: `backend/services/realized.py` (L748, L1269, L1428-1430)
- Modify: `backend/services/accounts.py` (L109)
- Test: `backend/tests/unit/calculations/test_precision_paths.py` (new)

**Interfaces:**
- Produces: a module-level `_cash_precision_for(asset, account_ids) -> int` in `realized.py` (resolves broker precision, fallback 2). Used by the three realized rounding spots. `accounts.py:109` uses `account.broker.cash_precision` directly.

- [ ] **Step 1: Write the failing precision tests**

Create `backend/tests/unit/calculations/test_precision_paths.py`:

```python
"""Tests for currency-aware rounding via broker.cash_precision (sub-project 4 follow-up).

Crypto brokers (OKX/Bybit) have cash_precision=8; fiat brokers=2. Realized G/L
and basis for crypto-scale values (e.g. BTC option profit +0.00014322) must
display at full precision, not round to 0.00.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Transactions
from services.realized import realized_gain_loss


def _make_crypto_broker_account(user, name="Crypto Test Broker"):
    """Broker with cash_precision=8 (matches OKX/Bybit migration 0098)."""
    broker = Brokers.objects.create(investor=user, name=name, country="Crypto", cash_precision=8)
    return Accounts.objects.create(broker=broker, name="Crypto Acct")


def _make_option(user, strike=Decimal("80000"), opt_type="CALL", expiry=date(2026, 6, 5)):
    name = f"BTC-{expiry.strftime('%d%b%y').upper()}-{strike}-{opt_type[0]}"
    asset = Assets.objects.create(
        type="Option", ISIN=f"CRYPTO:OPT:{name}", name=name,
        currency="BTC", exposure="Derivatives",
    )
    asset.investors.add(user)
    OptionMetadata.objects.create(
        asset=asset, strike_price=strike, option_type=opt_type,
        expiration_date=expiry, contract_size=Decimal("0.01"),
    )
    return asset


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestCryptoPrecisionRealized:
    def test_crypto_option_realized_not_rounded_to_zero(self, user):
        """With cash_precision=8, the +0.00014322 BTC option profit must NOT
        round to 0.00 at the realized_gain_loss outer boundary."""
        account = _make_crypto_broker_account(user)
        opt = _make_option(user)
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, 0, 15, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"),
            cash_flow=Decimal("0.000154"),
            commission=Decimal("-0.00001078"), commission_currency="BTC",
        )
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Option settlement",
            date=datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc),
            quantity=Decimal("7"), price=Decimal("0"), cash_flow=Decimal("0"),
        )
        result = realized_gain_loss(opt, date(2026, 6, 6), investor=user, account_ids=[account.id])
        # Pre-fix: rounds to 0.00 (2dp). Post-fix: 0.00014322 (8dp).
        assert result["all_time"]["total"] == Decimal("0.00014322")

    def test_fiat_realized_still_2dp(self, user, account):
        """Fiat broker (cash_precision=2) keeps 2dp rounding — no behavior change."""
        from common.models import Assets as A, Transactions as T
        from constants import TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL
        stock = A.objects.create(type="Stock", ISIN="PRECTEST1", name="Prec Test", currency="USD")
        stock.investors.add(user)
        T.objects.create(investor=user, account=account, security=stock, currency="USD",
            type=TRANSACTION_TYPE_BUY, date=datetime(2023, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("10"), price=Decimal("100"))
        T.objects.create(investor=user, account=account, security=stock, currency="USD",
            type=TRANSACTION_TYPE_SELL, date=datetime(2023, 6, 1, tzinfo=timezone.utc),
            quantity=Decimal("-10"), price=Decimal("150.005"))  # would be 500.05 at 2dp
        result = realized_gain_loss(stock, date(2023, 7, 1), investor=user, account_ids=[account.id])
        # Fiat: 2dp → 500.05 (the 0.005 rounds HALF_UP to 0.01 at 2dp of the per-unit, * 10)
        assert result["all_time"]["total"] == result["all_time"]["total"].quantize(Decimal("0.01"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_precision_paths.py -v`
Expected: FAIL — `test_crypto_option_realized_not_rounded_to_zero` fails (current code rounds to `0.00`).

- [ ] **Step 3: Add the `_cash_precision_for` helper to `realized.py`**

Near the top of `backend/services/realized.py` (after the imports, before the first function), add:

```python
def _cash_precision_for(asset, account_ids=None) -> int:
    """Resolve the broker's cash_precision for rounding financial outputs.

    Crypto brokers (OKX/Bybit) use 8 dp; fiat brokers use 2 (the model default).
    Falls back to 2 when account_ids is None/empty or the broker can't be
    resolved — matching the pre-fix behavior for call sites that don't pass
    account_ids.
    """
    if not account_ids:
        return 2
    try:
        from common.models import Accounts
        first_account = Accounts.objects.filter(id__in=account_ids).select_related("broker").first()
        if first_account and first_account.broker_id:
            return int(first_account.broker.cash_precision)
    except Exception:
        pass
    return 2
```

- [ ] **Step 4: Apply currency-aware rounding at the three realized spots**

In `backend/services/realized.py`:

**(a) `get_economic_basis` return (L748)** — change:
```python
    return basis.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```
to:
```python
    precision = _cash_precision_for(asset, account_ids)
    return basis.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
```

**(b) `realized_gain_loss` outer round (L1269)** — the loop:
```python
        for period in result:
            for component in result[period]:
                result[period][component] = round(result[period][component], 2)
```
Resolve precision ONCE before the loop (the function has `account_ids` in scope) and use `quantize`:
```python
        precision = _cash_precision_for(asset, account_ids)
        for period in result:
            for component in result[period]:
                result[period][component] = (
                    Decimal(result[period][component])
                    .quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
                )
```

**(c) `unrealized_gain_loss` return (L1428-1430)** — change:
```python
        "price_appreciation": round(Decimal(price_appreciation), 2),
        "fx_effect": round(Decimal(fx_effect), 2),
        "total": round(Decimal(unrealized_gain_loss), 2),
```
to (resolve precision from `asset`/`account_ids` in scope):
```python
        precision = _cash_precision_for(asset, account_ids)
        "price_appreciation": Decimal(price_appreciation).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP),
        "fx_effect": Decimal(fx_effect).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP),
        "total": Decimal(unrealized_gain_loss).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP),
```
(Place the `precision = ...` line before the return dict, not inside it.)

- [ ] **Step 5: Apply currency-aware rounding in `accounts.py:109`**

In `backend/services/accounts.py`, find the `balance()` rounding loop (~L109):
```python
    for key, value in balance_result.items():
        balance_result[key] = round(Decimal(value), 2)
```
Change to use `account.broker.cash_precision` (`account` is the function arg):
```python
    precision = getattr(getattr(account, "broker", None), "cash_precision", 2) or 2
    for key, value in balance_result.items():
        balance_result[key] = Decimal(value).quantize(
            Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP
        )
```

- [ ] **Step 6: Run the precision tests + full calculations suite**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/ -v`
Expected: PASS. The crypto option realized now shows `0.00014322`; fiat stays 2dp.

- [ ] **Step 7: Run the FULL unit suite (regression gate — critical, this touches protected rounding everywhere)**

Run: `cd backend && uv run python -m pytest tests/unit/ --no-cov -q`
Expected: all pass. **If existing tests assert 2dp values for crypto assets, they now get 8dp — update those assertions to the new precision.** (Most crypto realized tests already use `rounded=False` or helper-direct assertions per sub-project 4, so should be unaffected — but verify.)

- [ ] **Step 8: Commit**

```bash
git add backend/services/realized.py backend/services/accounts.py backend/tests/unit/calculations/test_precision_paths.py
git commit -m "fix(realized,accounts): currency-aware rounding via broker.cash_precision

Replace hardcoded 2dp rounding with broker.cash_precision (8 for crypto
brokers OKX/Bybit, 2 for fiat) at realized_gain_loss/get_economic_basis/
unrealized_gain_loss returns and accounts.balance(). Crypto-scale values
(e.g. BTC option profit +0.00014322) now display at full precision instead
of rounding to 0.00. Fiat outputs unchanged."
```

---

## Task 3: Fix importer transfer-leg currency (BTC in Cash column)

**Files:**
- Modify: `backend/services/crypto_exchange.py:475` (the `currency=` assignment in the non-cash persistence branch)
- Test: `backend/tests/unit/services/test_okx_csv_parser.py` (a transfer-currency test)

**Interfaces:**
- Produces: transfer legs get `currency = the coin` (e.g. BTC), not the missing `quote_currency`→`USD` default.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/services/test_okx_csv_parser.py`:

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_btc_transfer_row_currency_is_btc_not_usd(tmp_path, user, okx_account):
    """A non-stablecoin (BTC) transfer row must persist with currency=BTC,
    not the default USD (which leaks BTC into the Cash flows/balance column)."""
    rows = [{
        "id": "111", "Order id": "0", "Time": "2026-06-08 12:00:00",
        "Trade Type": "Transfer", "Symbol": "", "Action": "Transfer out",
        "Amount": "0", "Trading Unit": "BTC", "Filled Price": "",
        "PnL": "0", "Fee": "0", "Fee Unit": "", "Position Change": "-0.02",
        "Position Balance": "0", "Balance Change": "-0.02", "Balance": "0",
        "Balance Unit": "BTC",
    }]
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, rows)
    await _drain(parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False))
    txs = await _persisted_txs(user, okx_account)
    assert len(txs) == 1
    tx = txs[0]
    assert tx.type == "Crypto transfer out"
    assert tx.currency == "BTC"   # the coin, NOT USD
    assert tx.security.name == "BTC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/services/test_okx_csv_parser.py::test_btc_transfer_row_currency_is_btc_not_usd -v`
Expected: FAIL — `tx.currency == "USD"` (current bug).

- [ ] **Step 3: Fix the currency assignment**

In `backend/services/crypto_exchange.py`, find the non-cash persistence branch's `tx_kwargs = dict(...)` (~L456-470). The currency line (~L475):
```python
                    currency=str(leg.get("quote_currency") or "USD").upper(),
```
Transfer legs (built by `_single_leg`) have no `quote_currency`; they have `asset` (the coin). Change to prefer the leg's own asset for non-trade legs, falling back to `quote_currency` for spot trades and `USD` last:

```python
                    currency=str(
                        leg.get("quote_currency")
                        or leg.get("price_asset")
                        or leg.get("asset")
                        or "USD"
                    ).upper(),
```
Wait — for a transfer leg `_single_leg(ccy, amount, ccy)` sets `asset=ccy` and (per the leg builder) may not set `price_asset`. Verify by checking `_single_leg`: if it sets `price_asset`, prefer that; else `asset` is the coin. The robust form covers both:
```python
                    # Transfer legs have no quote_currency; use the coin itself
                    # (leg asset / price_asset) so the row's currency matches its
                    # quantity currency. Otherwise BTC transfers leak into the
                    # USD Cash column. Spot trades keep quote_currency.
                    currency=str(
                        leg.get("quote_currency")
                        or leg.get("price_asset")
                        or leg.get("asset")
                        or "USD"
                    ).upper(),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/services/test_okx_csv_parser.py::test_btc_transfer_row_currency_is_btc_not_usd -v`
Expected: PASS.

- [ ] **Step 5: Run the FULL unit suite**

Run: `cd backend && uv run python -m pytest tests/unit/ --no-cov -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/unit/services/test_okx_csv_parser.py
git commit -m "fix(crypto_exchange): transfer-leg currency = coin, not USD default

Transfer legs (built by _single_leg) have no quote_currency key, so the
persistence layer defaulted currency to USD — leaking BTC/TRUMP transfers
into the USD Cash flows/balance column. Now reads the coin from the leg's
price_asset/asset. Spot trades keep quote_currency."
```

---

## Task 4: Guard closed-positions builder against None prices (option missing)

**Files:**
- Modify: `backend/core/tables_utils.py:185` and `:198` (entry/exit value loops)
- Test: `backend/tests/unit/core/test_tables_option_closed.py` (new)

**Interfaces:**
- Produces: `get_price(transaction) or Decimal(0)` at both value-accumulation loops, so an OTM option settlement (price 0 → `get_price` returns None) doesn't crash the row.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/core/test_tables_option_closed.py`:

```python
"""Tests for the closed-positions table builder with option assets (sub-project 4 follow-up).

The BTC option's settlement row has price 0 (OTM terminal) — get_price returns
None for it, which previously caused None * Decimal TypeError at
tables_utils.py:198 and silently dropped the option from Closed positions.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Transactions
from core.tables_utils import _calculate_closed_table_output_for_api


@pytest.mark.django_db
class TestOptionInClosedPositions:
    def test_otm_option_appears_in_closed_table(self, user):
        broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        opt = Assets.objects.create(
            type="Option", ISIN="CRYPTO:OPT:BTC-05JUN26-80000-C",
            name="BTC-05JUN26-80000-C", currency="BTC", exposure="Derivatives",
        )
        opt.investors.add(user)
        OptionMetadata.objects.create(
            asset=opt, strike_price=Decimal("80000"), option_type="CALL",
            expiration_date=date(2026, 6, 5), contract_size=Decimal("0.01"),
        )
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
        rows, _ = _calculate_closed_table_output_for_api(
            user.id, [opt], date(2026, 8, 8),
            ["investment_date", "realized_gl", "exit_date"],
            True, "USD", [account.id], None,
        )
        assert len(rows) == 1, "option must appear in closed positions"
        assert rows[0]["exit_date"] == datetime(2026, 6, 5, 8, 0, 34, tzinfo=timezone.utc) or \
               rows[0]["exit_date"].date() == date(2026, 6, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/core/test_tables_option_closed.py -v`
Expected: FAIL — `TypeError: unsupported operand type(s) for *: 'NoneType' and 'decimal.Decimal'` (or the row is dropped).

- [ ] **Step 3: Guard the value loops**

In `backend/core/tables_utils.py`, find L185 (entry) and L198 (exit):
```python
                entry_value += get_price(transaction) * abs(transaction.quantity) * fx_rate
```
and
```python
                exit_value += get_price(transaction) * abs(transaction.quantity) * fx_rate
```
Change both to guard against None (an OTM option settlement has price 0 → `get_price` returns None):
```python
                entry_value += (get_price(transaction) or Decimal(0)) * abs(transaction.quantity) * fx_rate
```
```python
                exit_value += (get_price(transaction) or Decimal(0)) * abs(transaction.quantity) * fx_rate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/core/test_tables_option_closed.py -v`
Expected: PASS — the option appears in closed positions.

- [ ] **Step 5: Run the FULL unit suite**

Run: `cd backend && uv run python -m pytest tests/unit/ --no-cov -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/core/tables_utils.py backend/tests/unit/core/test_tables_option_closed.py
git commit -m "fix(tables): guard closed-positions value loops against None prices

The OTM option settlement row has price 0, for which get_price returns
None — causing None * Decimal TypeError at tables_utils.py:198 and silently
dropping the option from Closed positions. Guard with 'or Decimal(0)'.
Entry loop (L185) guarded symmetrically."
```

---

## Task 5: Verify against live re-imported data

**Files:** none (verification only)

- [ ] **Step 1: Delete the current OKX data and re-import fresh**

(Already done by the user in session — 35 okx_csv transactions + the option asset. If re-importing again, use the same delete-then-import flow from the session.)

- [ ] **Step 2: Verify all four issues resolved via Django shell**

Run (after re-import):
```bash
cd backend && uv run python manage.py shell -c "
from common.models import Assets, Transactions, Accounts
from services.positions import position
from services.realized import realized_gain_loss
from datetime import date, datetime, timezone
inv=1; acc=[18]  # OKX Trading

# Issue 4: BTC position should be ~fee-dust only, NOT -0.0002 with spurious realized
btc = Assets.objects.get(name='BTC', type='Crypto')
print('BTC position:', position(btc, datetime(2026,8,8,tzinfo=timezone.utc), inv, acc))
print('BTC realized:', realized_gain_loss(btc, date(2026,8,8), investor=inv, account_ids=acc)['all_time']['total'])

# Issue 2: option in closed positions
from core.positions_utils import _filter_assets
opt = Assets.objects.get(name='BTC-05JUN26-80000-C', type='Option')
print('Option in closed:', opt in _filter_assets(Assets.objects.get(id=1).investors.first(), date(2026,8,8), acc, True, ''))
"
```
Expected: BTC position ≈ small fee dust (no -0.0002 artifact); BTC realized = 0 (no spurious gain from transfers); Option in closed = True.

- [ ] **Step 3: Final full-suite run**

Run: `cd backend && uv run python -m pytest --no-cov -q`
Expected: all pass.

- [ ] **Step 4: Commit any test adjustments + push**

```bash
git push origin feat/crypto-option-accounting
```
(Updates PR #40.)

---

## Self-Review

**1. Issue coverage:**
- Issue 1 (BTC in Cash column) → Task 3 (transfer-leg currency fix).
- Issue 2 (option missing from Closed) → Task 4 (None-price guard).
- Issue 3 (TRUMP IRR) → Task 1 (transfer neutrality revert).
- Issue 4 (BTC -0.0002, spurious realized, IRR N/R) → Task 1 (transfer revert fixes the spurious realized/IRR).
- Precision policy → Task 2 (currency-aware rounding).

**2. Placeholder scan:** No TBDs. Task 5 Step 2's verification commands are concrete. The `is_unmatched_out/in` removal in Task 1 Step 3 is described precisely (restore to pre-Task-12 form).

**3. Type consistency:** `_cash_precision_for(asset, account_ids) -> int` consistent across Task 2's call sites. The `TRANSFER_DISPOSITION_ENABLED` flag is referenced consistently. `get_price(transaction) or Decimal(0)` form matches at both tables_utils lines.

**4. Risk note:** Task 2 (precision) changes rounding for ALL assets, not just crypto. Existing fiat tests asserting exact 2dp realized values will still pass (fiat brokers have cash_precision=2). Existing crypto tests using `rounded=False` or helper-direct assertions (sub-project 4 pattern) are unaffected. The full-suite gate (Task 2 Step 7) catches any crypto test that asserted a 2dp value and now gets 8dp.
