# Sub-Project 4 Follow-Ups Round 2: Option Pricing, Basis/Transfer Sync, Premium Leak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 bugs found after restarting the dev server against fresh OKX re-imported data: (A) TRUMP realized `+11.21` (should be a loss) from `get_economic_basis`/realized-walker transfer inconsistency; (B) option entry value `$85,117,877` from missing `contract_size` in the closed-positions table builder; (C) BTC option premium leaking into the cash balance; (D) option SELL row `price=163.558` (underlying USD) instead of `0.0022` (per-contract BTC premium) from `_leg_fiat_price` FX-converting the option premium.

**Architecture:** Four targeted fixes on `feat/crypto-option-accounting`. (A) Make `get_economic_basis` treat unmatched crypto transfers as neutral (skip basis-carry) when `TRANSFER_DISPOSITION_ENABLED=False`, so basis and the realized-walker position stay in sync. (B) Apply `contract_size` in `tables_utils.py`'s entry/exit value loops for option assets. (C) Exclude option-premium `cash_flow` from `balance()` (a premium is offset by the option liability, not a cash balance). (D) Skip the `_leg_fiat_price` FX conversion for option legs so the stored `price` stays the per-contract premium in the settle coin. After code fixes, the user re-imports (the existing DB rows have the wrong `price` from bug D).

**Tech Stack:** Python 3, Django 4, `Decimal` (`ROUND_HALF_UP`), pytest, uv project mode. All commands from `backend/` via `uv run`.

**Spec context:** Round-2 follow-ups to `docs/superpowers/specs/2026-08-07-crypto-option-accounting-and-realized-gain-design.md` (sub-project 4), found via live re-import after the round-1 follow-ups (`docs/superpowers/plans/2026-08-08-sub4-followups-transfers-precision-currency-closed.md`).

## Global Constraints

- **Numeric safety:** Always `Decimal`, never `float`. `ROUND_HALF_UP`.
- **Protected logic (PR with `needs-approval`):** `realized.py` (`get_economic_basis`), `accounts.py` (`balance`), `crypto_exchange.py` (`_leg_fiat_price`), `core/tables_utils.py`. No `models.py` schema change, no migrations.
- **Transfer policy:** `TRANSFER_DISPOSITION_ENABLED = False` — all crypto transfers neutral until #29. `get_economic_basis` must match the realized walker (neutral for transfers while the flag is off).
- **Option pricing:** the stored `price` on an option row is the **per-contract premium in the settle coin** (e.g. `0.0022` BTC). Value math (NAV, tables, realized) applies `contract_size` (0.01 BTC) and the settle-coin→target FX. The premium `cash_flow` is an option economic event, NOT a cash balance.
- **Branch:** `feat/crypto-option-accounting` (appends to PR #40).
- **Commands:** `cd backend && uv run python -m pytest ...`. Run BOTH `tests/unit/` AND `tests/integration/` per task (lesson from round-1: scoped runs miss cross-dir regressions).

---

## File Structure

**Modified files:**
- `backend/services/realized.py` — `get_economic_basis` transfer-out/in branches: skip basis-carry when `TRANSFER_DISPOSITION_ENABLED=False` (treat as pure position moves, like the realized walker).
- `backend/core/tables_utils.py` — entry/exit value loops (L185, L198): apply `contract_size` for option assets.
- `backend/services/accounts.py` — `balance()`: exclude option rows whose `cash_flow` is a premium (not a cash movement).
- `backend/services/crypto_exchange.py` — `_leg_fiat_price` (or its caller): skip FX conversion for option legs so the stored price stays the per-contract premium.

**New/updated tests:**
- `backend/tests/unit/calculations/test_realized_option_paths.py` — add a TRUMP-style test (buy, neutral transfer-out, neutral transfer-in, sell) asserting correct realized (a loss, not `+11.21`).
- `backend/tests/unit/core/test_tables_option_closed.py` — extend to assert entry value applies contract_size (not `$85M`).
- `backend/tests/unit/services/test_accounts_balance.py` (or extend an existing accounts test) — assert option premium excluded from balance.
- `backend/tests/unit/services/test_okx_csv_parser.py` — assert option SELL row `price == 0.0022` (per-contract BTC), not FX-converted.

---

## Task Interfaces

- **`realized.py` `get_economic_basis`** (Task 1): the transfer-out/in branches in the `replay` closure (~L639-670) gain a guard `if TRANSFER_DISPOSITION_ENABLED:` around the basis-carry; else `position += quantity; continue` (neutral, matching the realized walker). The `add_group_carry`/`allocate_group_carry`/`lookup_group_transfer_basis` machinery is retained (gated off).
- **`tables_utils.py`** (Task 2): `options.contract_size_for_asset(asset)` (from `services/options.py`, added in sub-project 4) is applied as a multiplier in both value loops for option assets.
- **`accounts.py` `balance()`** (Task 3): skips transactions where `security.type == "Option"` (their `cash_flow` is a premium, not a cash balance). Uses `options.is_option_asset` or an asset-type check.
- **`crypto_exchange.py`** (Task 4): option legs skip `_leg_fiat_price` — the leg's raw `price` (per-contract premium) is stored directly. The existing option branch in `persist_crypto_exchange_event` (~L445-478) already detects `instrument == "option"`; route around `_leg_fiat_price` there.

---

## Task 1: Sync `get_economic_basis` transfers with the realized walker (fixes TRUMP)

**Files:**
- Modify: `backend/services/realized.py` — the `replay` closure's transfer-out (~L639) and transfer-in (~L658) branches inside `get_economic_basis`.
- Test: `backend/tests/unit/calculations/test_realized_option_paths.py` — add a crypto-transfer-neutrality basis test (the TRUMP pattern).

**Interfaces:**
- Consumes: `TRANSFER_DISPOSITION_ENABLED` (the constant added in round-1 Task 1, ~L103).
- Produces: `get_economic_basis` returns correct basis when transfers are present and neutral (basis preserved across the transfer, not carried away).

- [ ] **Step 1: Write the failing test (the TRUMP pattern)**

Add to `backend/tests/unit/calculations/test_realized_option_paths.py`:

```python
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
        from common.models import Assets, Transactions
        from services.realized import get_economic_basis
        from datetime import datetime, timezone
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
        # Neutral transfer out / in (unmatched, no import_group_id partner in scope)
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="NEO",
            type="Crypto transfer out",
            date=datetime(2025, 1, 20, tzinfo=timezone.utc),
            quantity=Decimal("-1"),
        )
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="NEO",
            type="Crypto transfer in",
            date=datetime(2025, 2, 9, tzinfo=timezone.utc),
            quantity=Decimal("1"),
        )
        # Basis after the cycle should still reflect the buy (73.21), NOT be
        # carried away by the transfer-out into carried_basis_by_group.
        basis = get_economic_basis(coin, datetime(2025, 2, 10, tzinfo=timezone.utc),
                                   investor=user, account_ids=[account.id], rounded=False)
        assert basis == Decimal("73.21")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_realized_option_paths.py::TestCryptoTransferNeutralityInBasis -v`
Expected: FAIL — `basis` is ~0 (or a tiny residual) because the transfer-out carried the basis away.

- [ ] **Step 3: Make `get_economic_basis` transfers neutral when the flag is off**

In `backend/services/realized.py`, find the `replay` closure inside `get_economic_basis`. The transfer-out branch (~L639) currently debits basis and calls `add_group_carry`. The transfer-in branch (~L658) calls `allocate_group_carry`/`lookup_group_transfer_basis`. Gate BOTH behind `TRANSFER_DISPOSITION_ENABLED` so that when the flag is False (the current default), transfers are pure position moves with no basis effect.

For the **transfer-out branch**, wrap the basis-carry logic in the flag; always advance position:

```python
            elif transaction.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT:
                if TRANSFER_DISPOSITION_ENABLED:
                    transferred_quantity = (
                        min(abs(quantity), position) if position > 0 else Decimal(0)
                    )
                    transferred_basis = average_basis * transferred_quantity
                    basis -= transferred_basis
                    group_key = transfer_group_key(transaction)
                    add_group_carry(
                        carried_basis_by_group, group_key,
                        transfer_source_key(transaction),
                        transferred_basis, transferred_quantity,
                    )
                position += quantity
                if position <= 0:
                    basis = Decimal(0)
                    average_basis = Decimal(0)
                    continue
```

For the **transfer-in branch**, similarly gate the group-carry allocation; always advance position:

```python
            elif transaction.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_IN:
                if TRANSFER_DISPOSITION_ENABLED:
                    group_key = transfer_group_key(transaction)
                    if group_key:
                        carried_basis = allocate_group_carry(
                            carried_basis_by_group, group_key, quantity,
                        )
                        basis += carried_basis
                        if allow_group_lookup and carried_basis == 0:
                            basis += lookup_group_transfer_basis(
                                transaction, target, visited_transfer_ids,
                            )
                position += quantity
```

(Read the current branches first; preserve the exact variable names and the `average_basis` recompute that follows the loop. The only change is wrapping the basis-affecting lines in `if TRANSFER_DISPOSITION_ENABLED:` and keeping `position += quantity` unconditional.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_realized_option_paths.py::TestCryptoTransferNeutralityInBasis -v`
Expected: PASS — basis preserved at `73.21` across the neutral transfers.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. (The round-1 transfer tests already expect neutrality; this makes `get_economic_basis` consistent with them.)

- [ ] **Step 6: Commit**

```bash
git add backend/services/realized.py backend/tests/unit/calculations/test_realized_option_paths.py
git commit -m "fix(realized): make get_economic_basis transfers neutral when disposition disabled

get_economic_basis carried basis away on transfer-out (into carried_basis_by_group)
while the realized_gain_loss walker treated transfers as neutral position moves.
The mismatch produced a nonsense buy-in for assets with unmatched transfers
(the TRUMP bug: buy@73 -> neutral transfer out/in -> sell@16 realized as
+11.21 instead of a loss). Gate the basis-carry behind TRANSFER_DISPOSITION_ENABLED
so basis and the walker's position stay in sync while transfers are neutral."
```

---

## Task 2: Apply `contract_size` in the closed-positions table builder (fixes $85M entry value)

**Files:**
- Modify: `backend/core/tables_utils.py:185` and `:198` (entry/exit value loops).
- Test: `backend/tests/unit/core/test_tables_option_closed.py` — extend with an entry-value assertion.

**Interfaces:**
- Consumes: `options.contract_size_for_asset(asset)` (from `services/options.py`, returns the metadata's `contract_size` for option assets, `Decimal(1)` otherwise) and `options.is_option_asset(asset)`.

- [ ] **Step 1: Extend the failing test with an entry-value assertion**

In `backend/tests/unit/core/test_tables_option_closed.py`, the existing `test_otm_option_appears_in_closed_table` asserts `len(rows) == 1`. Add an entry-value assertion that proves `contract_size` is applied:

```python
        # Entry value must apply contract_size (0.01): qty 7 × price 0.0022 BTC
        # × contract_size 0.01 × FX(BTC->USD). Without contract_size it'd be
        # 100x too large (the $85M bug). Use a pinned BTC-USD price for determinism.
        # (Add a Prices row for BTC at e.g. 60000 in the test setup, and pin the
        #  option's currency to BTC. entry_value = 7 × 0.0022 × 0.01 × 60000 = 9.24.)
        assert rows[0]["entry_value"] == Decimal("9.24")
```

To make this deterministic, the test must seed a `Prices` row for the BTC underlying at a known USD price (e.g. `60000`) on/before the entry date, and set the option asset's `currency="BTC"`. Mirror the fixture pattern from `test_nav_option_paths.py` (which pins BTC-USD at 60000). Read that file's `_make_btc_underlying`/`Prices` setup and replicate.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/core/test_tables_option_closed.py -v`
Expected: FAIL — entry_value is `924.0` (100× too large, missing contract_size) or `85M`-style.

- [ ] **Step 3: Apply `contract_size` in the value loops**

In `backend/core/tables_utils.py`, the entry loop (~L185) and exit loop (~L198). Add an import at the top:
```python
from services import options
```
Then in BOTH loops, multiply by `contract_size` for option assets. At the top of the function (or once before the loops), resolve the contract size:
```python
        contract_size = options.contract_size_for_asset(asset)
```
Then change both value-accumulation lines from:
```python
                entry_value += (get_price(transaction) or Decimal(0)) * abs(transaction.quantity) * fx_rate
```
to:
```python
                entry_value += (get_price(transaction) or Decimal(0)) * abs(transaction.quantity) * contract_size * fx_rate
```
and identically for `exit_value` at L198. For non-option assets `contract_size` is `Decimal(1)`, so the math is unchanged for stocks/bonds/crypto.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/core/test_tables_option_closed.py -v`
Expected: PASS — entry_value == `9.24`.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. (Existing closed-position tests for stocks/bonds unaffected — `contract_size` is 1.0 for them.)

- [ ] **Step 6: Commit**

```bash
git add backend/core/tables_utils.py backend/tests/unit/core/test_tables_option_closed.py
git commit -m "fix(tables): apply contract_size to option entry/exit values

The closed-positions table builder priced options as get_price × quantity
with no contract_size, producing 100x-too-large values (BTC option entry
showed \$85M instead of the premium). Multiply by options.contract_size_for_asset
(0.01 for BTC options, 1.0 for non-options)."
```

---

## Task 3: Exclude option-premium `cash_flow` from `balance()` (fixes BTC in Cash balances)

**Files:**
- Modify: `backend/services/accounts.py` — `balance()` loop (~L78-90).
- Test: `backend/tests/unit/services/test_accounts_balance.py` (create or extend).

**Interfaces:**
- Consumes: `options.is_option_asset` (or an asset-type check on `transaction.security`).

- [ ] **Step 1: Write the failing test**

Create or extend `backend/tests/unit/services/test_accounts_balance.py`:

```python
"""Tests for services/accounts.py balance() — option premium exclusion."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Transactions
from services.accounts import balance


@pytest.mark.django_db
class TestBalanceExcludesOptionPremium:
    def test_option_sell_premium_not_in_cash_balance(self, user):
        broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        opt = Assets.objects.create(type="Option", ISIN="CRYPTO:OPT:X", name="BTC-X-C",
                                    currency="BTC", exposure="Derivatives")
        opt.investors.add(user)
        OptionMetadata.objects.create(asset=opt, strike_price=Decimal("80000"), option_type="CALL",
                                      expiration_date=date(2026, 6, 5), contract_size=Decimal("0.01"))
        # Option SELL: cash_flow +0.000154 BTC (the premium). This is an option
        # economic event offset by the option liability, NOT a BTC cash balance.
        Transactions.objects.create(
            investor=user, account=account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("0.000154"),
        )
        result = balance(account, date(2026, 6, 1))
        # The premium must NOT appear as a BTC cash balance.
        assert "BTC" not in result or result.get("BTC") == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/services/test_accounts_balance.py -v`
Expected: FAIL — `result["BTC"] == 0.00015400` (the premium leaking in).

- [ ] **Step 3: Exclude option-security transactions from `balance()`**

In `backend/services/accounts.py`, `balance()` loop (~L78). Add a guard skipping transactions whose security is an option (their `cash_flow` is a premium, not a cash movement). After the `for transaction in transactions:` line and before `cash_flow = total_cash_flow(transaction):`:

```python
        # Option rows' cash_flow is the premium (an option economic event offset
        # by the option liability), NOT a cash balance. Exclude them so the BTC
        # premium doesn't leak into the Cash balances card / cash column.
        if transaction.security is not None and transaction.security.type == "Option":
            continue
```

(Use the direct `.type == "Option"` check rather than importing `options.is_option_asset` — `balance()` already accesses `transaction.security`, and a string compare is the lightest touch. The constant `ASSET_TYPE_OPTION = "Option"` exists in `constants.py`; import it if you prefer the named constant.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/services/test_accounts_balance.py -v`
Expected: PASS — BTC not in result (or `Decimal("0")`).

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/accounts.py backend/tests/unit/services/test_accounts_balance.py
git commit -m "fix(accounts): exclude option premium cash_flow from balance()

Option rows' cash_flow is the premium (offset by the option liability),
not a BTC cash balance. balance() was aggregating it into balance_result,
leaking the +0.000154 BTC premium into the Cash balances card and the
transactions-page Cash flow column. Skip option-security transactions."
```

---

## Task 4: Store the option per-contract premium as the row `price` (fixes price=163.558)

**Files:**
- Modify: `backend/services/crypto_exchange.py` — route option legs around `_leg_fiat_price` in `persist_crypto_exchange_event` (~L395-404).
- Test: `backend/tests/unit/services/test_okx_csv_parser.py` — assert option SELL row `price == 0.0022`.

**Interfaces:**
- Consumes: the option leg's `instrument == "option"` flag (already used at ~L447 to resolve the option asset).
- Produces: option rows persist `price = leg["price"]` (the raw per-contract premium, e.g. `0.0022` BTC), NOT the FX-converted value.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/services/test_okx_csv_parser.py`:

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_option_sell_row_stores_per_contract_premium_not_fx_converted(tmp_path, user, okx_account):
    """The option SELL row's price must be the per-contract premium in the settle
    coin (0.0022 BTC), NOT FX-converted to the underlying USD price (163.55).
    FX conversion is applied later by value math (NAV/tables) via contract_size."""
    rows = [{
        "id": "3604219617540087810", "Order id": "3604219617506533376",
        "Time": "2026-05-28 00:15:14", "Trade Type": "Option",
        "Symbol": "BTC-USD-260605-80000-C", "Action": "Sell", "Amount": "7",
        "Trading Unit": "cont", "Filled Price": "0.002200", "PnL": "0",
        "Fee": "-0.00001078", "Fee Unit": "BTC", "Position Change": "0.00716211",
        "Position Balance": "0", "Balance Change": "-0.00701889",
        "Balance": "0.05975468", "Balance Unit": "BTC",
    }]
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, rows)
    await _drain(parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False))
    txs = await _persisted_txs(user, okx_account)
    sell = next(t for t in txs if t.type == "Crypto trade out")
    # Per-contract premium in BTC, NOT FX-converted to USD.
    assert sell.price == Decimal("0.0022")
    assert sell.currency == "BTC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/unit/services/test_okx_csv_parser.py::test_option_sell_row_stores_per_contract_premium_not_fx_converted -v`
Expected: FAIL — `sell.price == 163.558...` (FX-converted).

- [ ] **Step 3: Route option legs around `_leg_fiat_price`**

In `backend/services/crypto_exchange.py`, `persist_crypto_exchange_event` computes `price` for each leg (~L395-404). Currently:
```python
                try:
                    price = _leg_fiat_price(leg, user, event_time)
                except ...:
                    price = None
```
This FX-converts the option premium (0.0022 BTC × BTC-USD = 163.55). For option legs, store the RAW per-contract premium instead. Detect option legs via `leg.get("instrument") == "option"`:

```python
                if leg.get("instrument") == "option":
                    # Option legs: store the raw per-contract premium in the
                    # settle coin (e.g. 0.0022 BTC). FX conversion + contract_size
                    # are applied by value math (NAV/tables/realized), not here.
                    price = leg.get("price")
                else:
                    try:
                        price = _leg_fiat_price(leg, user, event_time)
                    except (ValueError, TypeError):
                        price = None
```

(Read the current structure around L395-404; preserve the existing try/except and any surrounding logic. The change is: option legs take the `price` branch; everything else keeps `_leg_fiat_price`. The option leg's `price` is set by the normalizer — `decompose_option_fill` returns `"price": Decimal(fill_price)`, which is `0.0022`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/unit/services/test_okx_csv_parser.py::test_option_sell_row_stores_per_contract_premium_not_fx_converted -v`
Expected: PASS — `sell.price == 0.0022`.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && uv run python -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. (Existing option-import tests that asserted on `cash_flow`/`currency` are unaffected; any that asserted on the FX-converted price would need updating — fix them to assert `0.0022`.)

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/unit/services/test_okx_csv_parser.py
git commit -m "fix(crypto_exchange): store option per-contract premium as row price

_leg_fiat_price FX-converted the option premium (0.0022 BTC × BTC-USD =
163.55), storing the underlying USD price as the row's price. Option legs
must keep the raw per-contract premium in the settle coin (0.0022 BTC);
FX conversion + contract_size are applied by value math (NAV/tables). Route
option legs around _leg_fiat_price."
```

---

## Task 5: Verify against live re-imported data

**Files:** none (verification only)

- [ ] **Step 1: Delete existing OKX data (Transactions + FXTransaction + orphan option)**

```bash
cd backend && uv run python manage.py shell -c "
from common.models import Transactions, FXTransaction, Assets, OptionMetadata
from services.importer import OKX_CSV_IMPORT_PROVIDER
from django.db import transaction
txns = Transactions.objects.filter(import_provider=OKX_CSV_IMPORT_PROVIDER)
ab = set(txns.values_list('security_id', flat=True))
txns.delete()
FXTransaction.objects.filter(import_provider=OKX_CSV_IMPORT_PROVIDER).delete()
with transaction.atomic():
    for a in Assets.objects.filter(id__in=ab, type='Option'):
        if Transactions.objects.filter(security=a).count() == 0:
            om = OptionMetadata.objects.filter(asset=a).first()
            if om: om.delete()
            a.investors.clear(); a.delete()
print('OKX data purged (Transactions + FXTransaction + option asset).')
"
```

- [ ] **Step 2: Re-import on the fixed branch**

Use the same CSV via the app's import UI, OR via the `parse_okx_trading_csv` shell path used in round-1 verification. Expect 35 transactions, 2 FX, 0 errors.

- [ ] **Step 3: Verify all 4 bugs resolved via Django shell**

```bash
cd backend && uv run python manage.py shell -c "
import logging; logging.disable(logging.CRITICAL)
from common.models import Assets, Transactions
from services.realized import realized_gain_loss, get_economic_basis
from services.accounts import balance
from datetime import date, datetime
inv=1; acc=[18]
# A: TRUMP realized (should be a LOSS now, not +11.21)
trump = Assets.objects.get(name='TRUMP', type='Crypto')
r = realized_gain_loss(trump, date(2026,8,8), investor=inv, account_ids=acc)
print('TRUMP realized:', r['all_time']['total'], '(should be negative — bought 73, sold 16)')
# B+D: option SELL row price + entry value
opt = Assets.objects.get(name='BTC-05JUN26-80000-C', type='Option')
sell = opt.transactions.get(type='Crypto trade out')
print('Option SELL price:', sell.price, '(should be 0.0022, not 163.55)')
# C: BTC not in account balance (premium excluded)
from common.models import Accounts
b = balance(Accounts.objects.get(id=18), date(2026,8,8))
print('Account balance keys:', list(b.keys()), '(BTC should be absent or 0)')
logging.disable(logging.NOTSET)
"
```
Expected: TRUMP realized negative; option SELL price `0.0022`; BTC absent from balance keys.

- [ ] **Step 4: Final full-suite run**

Run: `cd backend && uv run python -m pytest --no-cov -q`
Expected: all pass.

- [ ] **Step 5: Push to PR #40**

```bash
git push origin feat/crypto-option-accounting
```

---

## Self-Review

**1. Bug coverage:**
- Bug A (TRUMP realized +11.21) → Task 1 (`get_economic_basis` transfer neutrality).
- Bug B (option entry $85M) → Task 2 (tables_utils contract_size).
- Bug C (BTC premium in cash balance) → Task 3 (balance exclusion).
- Bug D (option price 163.558) → Task 4 (skip _leg_fiat_price for options).

**2. Placeholder scan:** Task 2 Step 1 references the existing `test_nav_option_paths.py` fixture pattern for pinning BTC-USD — the implementer must read it (explicitly stated). Task 5's shell commands are concrete.

**3. Type/consistency:** `options.contract_size_for_asset(asset)` used in Task 2 (exists in `services/options.py` from sub-project 4 Task 13). `TRANSFER_DISPOSITION_ENABLED` used in Task 1 (exists from round-1 Task 1). `transaction.security.type == "Option"` in Task 3 (the asset-type string; `ASSET_TYPE_OPTION` constant exists if preferred).

**4. Re-import requirement:** Bugs B and D corrupt the *stored* row data (wrong price), so the existing DB rows won't self-heal — the user must re-import after Tasks 1-4. Bug A and C are read-path fixes that take effect immediately on existing rows. Task 5 covers the re-import.
