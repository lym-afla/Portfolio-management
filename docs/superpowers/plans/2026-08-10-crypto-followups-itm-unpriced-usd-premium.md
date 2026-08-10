# Crypto Follow-Ups: ITM Exit Value, USD Premium Routing, Unpriced-Coin Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three calc-layer edge cases surfaced by the crypto option feature: (1) ITM option `exit_value` double-applies `contract_size`; (2) USD-denominated option premiums reach neither Total NAV nor the cash balance; (3) unpriced crypto coins crash the realized/IRR/tables paths.

**Architecture:** Three independent fixes on `feat/crypto-option-accounting`. (1) A new `options.option_transaction_value` helper encapsulates the per-contract-vs-size-scaled price distinction; `tables_utils` calls it for options. (2) `balance()` becomes currency-aware (skip coin-settled premiums, include fiat-settled). (3) A three-tier price resolver in `crypto.py` (market → last-trade → None) plus `safe_crypto_fx_rate` returning None-with-warning; ~8 call sites in `realized.py`/`nav.py` wrap their FX calls and skip-on-None.

**Tech Stack:** Python 3, Django 4, `Decimal` (`ROUND_HALF_UP`), pytest, uv project mode. All commands from `backend/` via `uv run`.

**Spec:** `docs/superpowers/specs/2026-08-10-crypto-followups-itm-unpriced-usd-premium-design.md`

## Global Constraints

- **Numeric safety:** `Decimal` for all money/price — never `float`. `ROUND_HALF_UP`.
- **Protected code — requires PR with `needs-approval`:** `realized.py` (`realized_gain_loss`, `get_economic_basis`, `calculate_buy_in_price`, `_realized_option_close`), `nav.py` (`NAV_at_date`, `IRR`), `accounts.py` (`balance`). No `models.py` schema change, no migrations.
- **Branch:** `feat/crypto-option-accounting` (appends to PR #40).
- **Shell note:** the Bash tool may run `cmd.exe` with a stripped PATH (no `git`/`uv`). Use the venv python directly for pytest: `cd backend && .venv\Scripts\python.exe -m pytest ...`. Git: `"D:\Program Files (x86)\Git\cmd\git.exe" ...`.
- **Commands:** Run BOTH `tests/unit/` AND `tests/integration/` per task (lesson from earlier rounds: scoped runs miss cross-dir regressions).
- **Currency source:** `CASH_CURRENCIES = {code.upper() for code, _ in ALL_CURRENCY_CHOICES}` (= USD/EUR/GBP/RUB/CHF/CNY/USDT/USDC) — the authoritative cash-currency set, defined in `constants.py`.

---

## File Structure

**New helpers (no behavior change until wired):**
- `backend/services/options.py` — add `option_transaction_value(transaction, contract_size, fx_rate) -> Decimal`.
- `backend/services/crypto.py` — add `crypto_usd_price_with_fallback(code, date_as_of, investor) -> Optional[Decimal]` and `safe_crypto_fx_rate(code, target, date_as_of, investor) -> Optional[Decimal]`.
- `backend/constants.py` — add `CASH_CURRENCIES`.

**Modified (wiring the helpers):**
- `backend/core/tables_utils.py` — entry/exit value loops call `option_transaction_value` for options.
- `backend/services/accounts.py` — `balance()`: currency-aware option skip.
- `backend/core/balance_tracker.py` — import shared `CASH_CURRENCIES` (replace local `_CASH_CURRENCIES`).
- `backend/services/realized.py` — wrap FX calls in `safe_crypto_fx_rate`; skip-on-None at `transaction_fx_rate` (L528), `calculate_buy_in_price` (L428, L461), `_realized_option_close` (L195), crypto closing-long FX (L1120).
- `backend/services/nav.py` — wrap FX calls in `safe_crypto_fx_rate` at `IRR` (L540), `calculate_portfolio_cash` (L446), option-liability loop (L257).

**Tests:** `test_options.py`, `test_realized_option_paths.py`, `test_nav_option_paths.py`, `test_accounts_balance.py`, `test_tables_option_closed.py`, `test_crypto_class.py` (or new `test_crypto_pricing.py`).

---

## Task Interfaces

- **`options.option_transaction_value(transaction, contract_size, fx_rate) -> Decimal`** (Task 1): opening fills → `price × |qty| × contract_size × fx`; settlements → `price × |qty| × fx` (price already size-scaled). Used by `tables_utils`.
- **`CASH_CURRENCIES`** (Task 2): `{code.upper() for code, _ in ALL_CURRENCY_CHOICES}`. Used by `accounts.py balance()` and `balance_tracker.py`.
- **`crypto.crypto_usd_price_with_fallback(code, date_as_of, investor) -> Optional[Decimal]`** (Task 3): tier 1 market price → tier 2 last-trade price → None.
- **`crypto.safe_crypto_fx_rate(code, target, date_as_of, investor) -> Optional[Decimal]`** (Task 3): wraps `crypto_fx_rate`, returns None+warning when unpriced. Used by Tasks 4-5.

---

## Phase A: Follow-up 1 — ITM exit_value (low-risk, isolated)

### Task 1: `options.option_transaction_value` helper + tables_utils wiring

**Files:**
- Modify: `backend/services/options.py` (add helper)
- Modify: `backend/core/tables_utils.py` (~L185-205 entry/exit value loops)
- Test: `backend/tests/unit/services/test_options.py`, `backend/tests/unit/core/test_tables_option_closed.py`

**Interfaces:**
- Produces: `option_transaction_value(transaction, contract_size, fx_rate) -> Decimal`.

- [ ] **Step 1: Write failing tests for `option_transaction_value`**

Add to `backend/tests/unit/services/test_options.py`:

```python
@pytest.mark.unit
class TestOptionTransactionValue:
    def _tx(self, type_, price, quantity):
        from common.models import Transactions
        from datetime import datetime, timezone
        return Transactions(
            type=type_, price=Decimal(price), quantity=Decimal(quantity),
            currency="BTC", date=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )

    def test_opening_fill_applies_contract_size(self):
        from constants import TRANSACTION_TYPE_CRYPTO_TRADE_OUT
        from services.options import option_transaction_value
        # Opening SELL: price 0.0022 (raw per-contract) × qty 7 × size 0.01 × fx 1
        tx = self._tx(TRANSACTION_TYPE_CRYPTO_TRADE_OUT, "0.0022", "-7")
        assert option_transaction_value(tx, Decimal("0.01"), Decimal("1")) == Decimal("0.000154")

    def test_settlement_otm_is_zero(self):
        from constants import TRANSACTION_TYPE_OPTION_SETTLEMENT
        from services.options import option_transaction_value
        tx = self._tx(TRANSACTION_TYPE_OPTION_SETTLEMENT, "0", "7")
        assert option_transaction_value(tx, Decimal("0.01"), Decimal("1")) == Decimal("0")

    def test_settlement_itm_no_double_contract_size(self):
        """Settlement price is ALREADY size-scaled (from intrinsic_price).
        The helper must NOT multiply by contract_size again."""
        from constants import TRANSACTION_TYPE_OPTION_SETTLEMENT
        from services.options import option_transaction_value
        # intrinsic_q = 0.01 * (85000-80000) / 85000 = 0.00058824 (already scaled)
        tx = self._tx(TRANSACTION_TYPE_OPTION_SETTLEMENT, "0.00058824", "7")
        # Correct: 0.00058824 * 7 * 1 = 0.00411768 (NOT * 0.01 again = 0.00004118)
        assert option_transaction_value(tx, Decimal("0.01"), Decimal("1")) == Decimal("0.00411768")

    def test_fx_rate_applied(self):
        from constants import TRANSACTION_TYPE_CRYPTO_TRADE_OUT
        from services.options import option_transaction_value
        tx = self._tx(TRANSACTION_TYPE_CRYPTO_TRADE_OUT, "0.0022", "-7")
        # 0.0022 * 7 * 0.01 * 60000 = 9.24
        assert option_transaction_value(tx, Decimal("0.01"), Decimal("60000")) == Decimal("9.24")
```

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/services/test_options.py::TestOptionTransactionValue -v`
Expected: FAIL — `ImportError: cannot import name 'option_transaction_value'`.

- [ ] **Step 3: Add the helper to `services/options.py`**

Append to `backend/services/options.py`:

```python
def option_transaction_value(transaction, contract_size: Decimal, fx_rate: Decimal) -> Decimal:
    """Effective value contribution of an option transaction row.

    Opening fills (Crypto trade in/out): the stored price is the raw per-contract
    premium (e.g. 0.0022 BTC) from decompose_option_fill — NOT size-scaled.
      value = price * |qty| * contract_size * fx_rate
    Settlements (Option settlement): the stored price for ITM is the intrinsic
    per-contract value from intrinsic_price, which ALREADY incorporates
    contract_size (returns size * max(spot-strike,0)/spot).
      value = price * |qty| * fx_rate  (no second contract_size)
    OTM settlements have price 0 -> value 0 regardless.
    """
    from constants import TRANSACTION_TYPE_OPTION_SETTLEMENT
    price = Decimal(transaction.price) if transaction.price is not None else Decimal(0)
    qty = abs(Decimal(transaction.quantity)) if transaction.quantity is not None else Decimal(0)
    csize = Decimal(contract_size)
    fx = Decimal(fx_rate)
    if transaction.type == TRANSACTION_TYPE_OPTION_SETTLEMENT:
        return price * qty * fx
    return price * qty * csize * fx
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/services/test_options.py::TestOptionTransactionValue -v`
Expected: 4 PASS.

- [ ] **Step 5: Wire into `tables_utils.py`**

In `backend/core/tables_utils.py`, the entry loop (~L192) and exit loop (~L205) currently both use:
```python
                entry_value += (get_price(transaction) or Decimal(0)) * abs(transaction.quantity) * contract_size * fx_rate
```
Replace both with calls to `option_transaction_value` for option assets. Read the current code structure — the loops are inside a `for asset in portfolio:` block where `contract_size` is already resolved (~L108). For option assets, replace the inline formula:

```python
                if options.is_option_asset(asset):
                    entry_value += options.option_transaction_value(transaction, contract_size, fx_rate)
                else:
                    entry_value += (get_price(transaction) or Decimal(0)) * abs(transaction.quantity) * fx_rate
```

Apply the same pattern to the exit loop (~L205). Non-option assets keep the inline formula (no `contract_size`, which is `Decimal(1)` for them anyway).

- [ ] **Step 6: Add an ITM exit_value assertion to the closed-positions test**

In `backend/tests/unit/core/test_tables_option_closed.py`, the existing `test_otm_option_appears_in_closed_table` asserts entry_value. Add a separate test for the ITM case (or extend the class) asserting exit_value applies no double-contract_size:

```python
    def test_itm_option_exit_value_no_double_contract_size(self, user):
        """ITM settlement exit_value must not double-apply contract_size.
        The settlement price is already size-scaled (intrinsic_price)."""
        # Setup: option SELL + ITM settlement (spot 85000 > strike 80000).
        # intrinsic_q = 0.01 * (85000-80000) / 85000 = 0.00058824 (8dp)
        # Pin BTC-USD at 60000 for deterministic FX.
        # ... (mirror the existing test's fixture: broker cash_precision=8,
        #      BTC Prices row at 60000, option with contract_size 0.01,
        #      SELL qty -7 price 0.0022, ITM settlement qty 7 price 0.00058824)
        # exit_value = intrinsic_q * qty * fx = 0.00058824 * 7 * 60000 = 247.06
        # (NOT * contract_size again = 2.47)
        rows, _ = _calculate_closed_table_output_for_api(...)
        assert rows[0]["exit_value"] == Decimal("247.06080000")  # or the exact 8dp value
```

(Concretize the fixture setup mirroring the existing test's `_make_btc_underlying` + pinned Prices row. The key assertion: exit_value is `intrinsic_q × qty × fx`, NOT `× contract_size` again.)

- [ ] **Step 7: Run the full unit + integration suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. Existing option closed-position tests unaffected (OTM exit_value is 0 regardless).

- [ ] **Step 8: Commit**

```bash
"D:\Program Files (x86)\Git\cmd\git.exe" add backend/services/options.py backend/core/tables_utils.py backend/tests/unit/services/test_options.py backend/tests/unit/core/test_tables_option_closed.py
"D:\Program Files (x86)\Git\cmd\git.exe" commit -m "feat(options): option_transaction_value helper — fixes ITM exit_value double-contract_size

intrinsic_price already incorporates contract_size, so the settlement leg's
stored price is size-scaled. tables_utils multiplied by contract_size again,
making ITM exit_value 100x too small. New option_transaction_value helper
knows the distinction (fills need x contract_size; settlements don't)."
```

---

## Phase B: Follow-up 3 — USD option premium routing (low-risk, isolated)

### Task 2: `CASH_CURRENCIES` constant + currency-aware `balance()`

**Files:**
- Modify: `backend/constants.py` (add `CASH_CURRENCIES`)
- Modify: `backend/services/accounts.py` (`balance()` ~L83)
- Modify: `backend/core/balance_tracker.py` (import shared constant)
- Test: `backend/tests/unit/services/test_accounts_balance.py`

**Interfaces:**
- Produces: `CASH_CURRENCIES` in `constants.py`; `balance()` includes fiat-denominated option premiums.

- [ ] **Step 1: Add `CASH_CURRENCIES` to `constants.py`**

In `backend/constants.py`, after `ALL_CURRENCY_CHOICES`:

```python
CASH_CURRENCIES = {code.upper() for code, _ in ALL_CURRENCY_CHOICES}
# = {"USD", "EUR", "GBP", "RUB", "CHF", "CNY", "USDT", "USDC"}
```

- [ ] **Step 2: Write failing tests**

Add to `backend/tests/unit/services/test_accounts_balance.py`:

```python
    def test_usd_option_premium_included_in_cash_balance(self, user):
        """A USD-denominated option premium IS a cash movement — include it."""
        from datetime import datetime, timezone
        from common.models import Assets, OptionMetadata
        opt = Assets.objects.create(type="Option", ISIN="CRYPTO:OPT:USDX", name="USD-OPT",
                                    currency="USD", exposure="Derivatives")
        opt.investors.add(user)
        OptionMetadata.objects.create(asset=opt, strike_price=Decimal("80000"), option_type="CALL",
                                      expiration_date=date(2026, 6, 5), contract_size=Decimal("0.01"))
        Transactions.objects.create(
            investor=user, account=self.crypto_account, security=opt, currency="USD",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("100"),
        )
        result = balance(self.crypto_account, date(2026, 6, 1))
        assert result.get("USD") == Decimal("100")

    def test_btc_option_premium_excluded_from_cash_balance(self, user):
        """A BTC-denominated option premium is NOT cash — exclude it (regression)."""
        from datetime import datetime, timezone
        from common.models import Assets, OptionMetadata
        opt = Assets.objects.create(type="Option", ISIN="CRYPTO:OPT:BTCX", name="BTC-OPT",
                                    currency="BTC", exposure="Derivatives")
        opt.investors.add(user)
        OptionMetadata.objects.create(asset=opt, strike_price=Decimal("80000"), option_type="CALL",
                                      expiration_date=date(2026, 6, 5), contract_size=Decimal("0.01"))
        Transactions.objects.create(
            investor=user, account=self.crypto_account, security=opt, currency="BTC",
            type="Crypto trade out",
            date=datetime(2026, 5, 28, tzinfo=timezone.utc),
            quantity=Decimal("-7"), price=Decimal("0.0022"), cash_flow=Decimal("0.000154"),
        )
        result = balance(self.crypto_account, date(2026, 6, 1))
        assert "BTC" not in result or result.get("BTC") == Decimal("0")
```

(If the existing `TestBalanceExcludesOptionPremium` class uses `self.crypto_account`, mirror that setup. If not, create the broker/account inline like round-2 Task 3.)

- [ ] **Step 3: Run to verify fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/services/test_accounts_balance.py -v`
Expected: FAIL — the USD test gets no "USD" key (balance skips all options).

- [ ] **Step 4: Make `balance()` currency-aware**

In `backend/services/accounts.py`, replace the blanket option skip (~L83):
```python
        if transaction.security is not None and transaction.security.type == ASSET_TYPE_OPTION:
            continue
```
with the currency-aware version:
```python
        from constants import CASH_CURRENCIES
        if (
            transaction.security is not None
            and transaction.security.type == ASSET_TYPE_OPTION
            and (transaction.currency or "").upper() not in CASH_CURRENCIES
        ):
            # Coin-settled premium (BTC) — Crypto-bucket movement, not cash. Skip.
            # Fiat/stablecoin-settled premium (USD) — IS a cash movement. Include.
            continue
```
(Move `from constants import CASH_CURRENCIES` to the top-of-file imports if cleaner.)

- [ ] **Step 5: Update `balance_tracker.py` to use the shared constant**

In `backend/core/balance_tracker.py`, replace the local `_CASH_CURRENCIES` derivation with the shared import:
```python
from constants import CASH_CURRENCIES as _CASH_CURRENCIES
```
Remove the local `_CASH_CURRENCIES = {code.upper() for code, _ in ALL_CURRENCY_CHOICES}` line and the `ALL_CURRENCY_CHOICES` import (now only needed indirectly).

- [ ] **Step 6: Run to verify pass + full suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. The round-2 BTC-exclusion test still passes (BTC is not in CASH_CURRENCIES).

- [ ] **Step 7: Commit**

```bash
"D:\Program Files (x86)\Git\cmd\git.exe" add backend/constants.py backend/services/accounts.py backend/core/balance_tracker.py backend/tests/unit/services/test_accounts_balance.py
"D:\Program Files (x86)\Git\cmd\git.exe" commit -m "fix(accounts): currency-aware option premium in balance()

balance() skipped ALL option rows, but fiat-settled premiums (USD/EUR) ARE
cash movements. Now skips only coin-settled premiums (BTC -> Crypto bucket);
fiat-settled premiums enter the cash balance. Shared CASH_CURRENCIES constant."
```

---

## Phase C: Follow-up 2 — Unpriced-coin resilience (broadest)

### Task 3: Three-tier price resolver in `crypto.py`

**Files:**
- Modify: `backend/services/crypto.py` (add `crypto_usd_price_with_fallback`, `safe_crypto_fx_rate`)
- Test: `backend/tests/unit/services/test_crypto_class.py` or new `test_crypto_pricing.py`

**Interfaces:**
- Produces: `crypto_usd_price_with_fallback(code, date_as_of, investor) -> Optional[Decimal]` and `safe_crypto_fx_rate(code, target, date_as_of, investor) -> Optional[Decimal]`.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/unit/services/test_crypto_class.py` (or create `test_crypto_pricing.py`):

```python
@pytest.mark.django_db
class TestCryptoUsdPriceWithFallback:
    def test_tier1_market_price(self, user):
        """When a Prices row exists, return it (tier 1)."""
        from common.models import Assets, Prices
        from datetime import datetime, timezone
        from services.crypto import crypto_usd_price_with_fallback
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:FB1", name="FB1",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Prices.objects.create(security=coin, date=datetime(2026, 1, 1, tzinfo=timezone.utc), price=Decimal("100"))
        result = crypto_usd_price_with_fallback("FB1", datetime(2026, 6, 1).date(), investor=user)
        assert result == Decimal("100")

    def test_tier2_last_trade_price(self, user):
        """When no Prices row exists but a trade does, return the last-trade price."""
        from common.models import Assets, Transactions
        from datetime import datetime, timezone
        from services.crypto import crypto_usd_price_with_fallback
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:FB2", name="FB2",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Transactions.objects.create(
            investor=user, account=Accounts.objects.create(broker=Brokers.objects.create(investor=user, name="T", country="X"), name="A"),
            security=coin, currency="USDT", type="Crypto trade out",
            date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            quantity=Decimal("-1"), price=Decimal("16.557"),
        )
        result = crypto_usd_price_with_fallback("FB2", datetime(2026, 6, 1).date(), investor=user)
        assert result == Decimal("16.557")

    def test_tier3_none_when_no_price_no_trade(self, user):
        """When no Prices row AND no trade, return None."""
        from common.models import Assets
        from services.crypto import crypto_usd_price_with_fallback
        Assets.objects.create(type="Crypto", ISIN="CRYPTO:FB3", name="FB3",
                              currency="USD", exposure="Commodity").investors.add(user)
        result = crypto_usd_price_with_fallback("FB3", datetime(2026, 6, 1).date(), investor=user)
        assert result is None


@pytest.mark.django_db
class TestSafeCryptoFxRate:
    def test_priced_returns_rate(self, user):
        from common.models import Assets, Prices
        from datetime import datetime, timezone
        from services.crypto import safe_crypto_fx_rate
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:SF1", name="SF1",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Prices.objects.create(security=coin, date=datetime(2026, 1, 1, tzinfo=timezone.utc), price=Decimal("50000"))
        result = safe_crypto_fx_rate("SF1", "USD", datetime(2026, 6, 1).date(), investor=user)
        assert result == Decimal("50000")

    def test_unpriced_returns_none(self, user):
        from common.models import Assets
        from services.crypto import safe_crypto_fx_rate
        Assets.objects.create(type="Crypto", ISIN="CRYPTO:SF2", name="SF2",
                              currency="USD", exposure="Commodity").investors.add(user)
        result = safe_crypto_fx_rate("SF2", "USD", datetime(2026, 6, 1).date(), investor=user)
        assert result is None
```

(Add `from common.models import Accounts, Brokers` and `from decimal import Decimal` to the test imports if not present. Adjust fixture details to match the file's existing style.)

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/services/test_crypto_class.py::TestCryptoUsdPriceWithFallback tests/unit/services/test_crypto_class.py::TestSafeCryptoFxRate -v`
Expected: FAIL — `ImportError: cannot import name 'crypto_usd_price_with_fallback'`.

- [ ] **Step 3: Add the helpers to `services/crypto.py`**

Append to `backend/services/crypto.py`:

```python
def crypto_usd_price_with_fallback(code: str, date_as_of, investor=None) -> Optional[Decimal]:
    """Resolve a coin's USD price, falling back to the last transaction price.

    Tier 1: latest Prices row on/before date_as_of (the live market price).
    Tier 2: the asset's most recent Crypto trade in/out price (as USD),
            if that trade's currency is USD/USDT/USDC, or convertible via FX.
    Tier 3: None (unpriced — caller skips with warning).
    """
    # Tier 1
    try:
        return crypto_usd_price(code, date_as_of, investor)
    except ValueError:
        pass
    # Tier 2: last transaction price
    from common.models import Assets, Transactions
    from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    asset = Assets.objects.filter(type="Crypto", name=code).first()
    if asset is None:
        return None
    last_trade = (
        Transactions.objects.filter(
            security=asset, investor=investor,
            type__in=[TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT],
            price__isnull=False,
            date__date__lte=date_as_of,
        ).order_by("-date", "-id").first()
    )
    if last_trade is None or last_trade.price in (None, 0):
        return None
    if (last_trade.currency or "").upper() in ("USD", "USDT", "USDC"):
        return Decimal(last_trade.price)
    try:
        return Decimal(last_trade.price) * get_rate(last_trade.currency, "USD", last_trade.date)["FX"]
    except ValueError:
        return None


def safe_crypto_fx_rate(code: str, target: str, date_as_of, investor=None) -> Optional[Decimal]:
    """Like crypto_fx_rate, but returns None (with a warning) when the coin is
    unpriced (both market and last-trade fallbacks miss), instead of raising.

    Callers that need graceful degradation (realized/IRR/tables) use this;
    strict callers (NAV spot-crypto, which has its own try/except) keep crypto_fx_rate.
    """
    try:
        return crypto_fx_rate(code, target, date_as_of, investor)
    except ValueError:
        usd_price = crypto_usd_price_with_fallback(code, date_as_of, investor)
        if usd_price is None:
            logger.warning(
                "No USD price for %s on or before %s (market + last-trade) — skipping",
                code, date_as_of,
            )
            return None
        logger.info("Using last-trade price for %s as of %s", code, date_as_of)
        if (target or "").upper() == "USD":
            return usd_price
        try:
            return usd_price * get_rate("USD", target, date_as_of)["FX"]
        except ValueError:
            return None
```

(`get_rate` is already imported in crypto.py via `from services.fx import get_rate` — verify; if not, lazy-import it to avoid circulars. `Optional` is already imported.)

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/services/test_crypto_class.py::TestCryptoUsdPriceWithFallback tests/unit/services/test_crypto_class.py::TestSafeCryptoFxRate -v`
Expected: 5 PASS.

- [ ] **Step 5: Run the full unit + integration suite (helpers are additive — should be green)**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass (no behavior change yet — helpers exist but aren't wired).

- [ ] **Step 6: Commit**

```bash
"D:\Program Files (x86)\Git\cmd\git.exe" add backend/services/crypto.py backend/tests/unit/services/test_crypto_class.py
"D:\Program Files (x86)\Git\cmd\git.exe" commit -m "feat(crypto): three-tier price resolver + safe_crypto_fx_rate

crypto_usd_price_with_fallback: tier 1 market price -> tier 2 last-trade price -> None.
safe_crypto_fx_rate: wraps crypto_fx_rate, returns None+warning when unpriced
instead of raising. Additive (not wired yet); callers in Tasks 4-5."
```

---

### Task 4: Wire `safe_crypto_fx_rate` into `realized.py` (skip-on-None)

**Files:**
- Modify: `backend/services/realized.py` — `transaction_fx_rate` (~L528), `calculate_buy_in_price` (~L428, L461), `_realized_option_close` (~L195), crypto closing-long FX (~L1120).
- Test: `backend/tests/unit/calculations/test_realized_option_paths.py` (unpriced skip), `test_gain_loss.py` or a new fixture.

**Interfaces:**
- Consumes: `safe_crypto_fx_rate` (Task 3).

- [ ] **Step 1: Write a failing test for unpriced-coin realized**

Add to `backend/tests/unit/calculations/test_realized_option_paths.py` (or `test_realized_transfer_paths.py`):

```python
@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestUnpricedCoinRealizedNoCrash:
    """A crypto coin with no Prices row (and no trades) must not crash
    realized_gain_loss. It returns {total: 0} and the position is tracked."""

    def test_unpriced_coin_realized_returns_zero(self, user, account):
        from common.models import Assets, Transactions
        from services.realized import realized_gain_loss
        # A coin with NO Prices row and NO trades -> fully unpriced.
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:UNP", name="UNP",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Transactions.objects.create(
            investor=user, account=account, security=coin, currency="USDT",
            type="Crypto trade in",
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            quantity=Decimal("1"), price=Decimal("10"),
        )
        # This used to crash with ValueError: No USD price for UNP.
        result = realized_gain_loss(coin, date(2026, 6, 1), investor=user, account_ids=[account.id])
        # Unpriced -> realized skips, returns 0 (not a crash).
        assert result["all_time"]["total"] == Decimal("0")
```

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/calculations/test_realized_option_paths.py::TestUnpricedCoinRealizedNoCrash -v`
Expected: FAIL — `ValueError: No USD price for UNP`.

- [ ] **Step 3: Wire `safe_crypto_fx_rate` into the crash sites**

In `backend/services/realized.py`, replace the FX calls that crash with `safe_crypto_fx_rate`. Add the import:
```python
from services.crypto import safe_crypto_fx_rate
```

**(a) `transaction_fx_rate` in `get_economic_basis` (~L528):**
```python
    def transaction_fx_rate(transaction, target):
        if target is not None and transaction.currency != target:
            rate = safe_crypto_fx_rate(transaction.currency, target, transaction.date)
            return rate if rate is not None else Decimal(0)
        return Decimal(1)
```
(When `safe_crypto_fx_rate` returns None, return `Decimal(0)` so the transaction contributes 0 to basis — effectively skipping it without crashing. The basis replay continues; the asset's basis comes from priced transactions only.)

**(b) `calculate_buy_in_price` (~L428, L461):** the two `_fx_get_rate(...)["FX"]` calls. Wrap each:
```python
            try:
                fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)["FX"]
            except ValueError:
                fx_rate = Decimal(0)
```
(OR use `safe_crypto_fx_rate` if `transaction.currency` is a crypto code — check the existing logic for whether `_fx_get_rate` is the right wrapper here. The goal: unpriced-coin transactions don't crash `calculate_buy_in_price`.)

**(c) `_realized_option_close` (~L195):** the FX-convert block. Wrap the `safe_crypto_fx_rate` call:
```python
        fx = safe_crypto_fx_rate(settle_ccy, target_currency, transaction.date)
        if fx is None:
            # Unpriced settle coin — return realized in native coin (no crash).
            return {"price_appreciation": realized_local, "fx_effect": Decimal(0), "total": realized_local}
        realized_target = realized_local * fx
```

**(d) crypto closing-long FX (~L1120):** the `_fx_get_rate(transaction.currency, currency, transaction.date)["FX"]` in `calculate_position_gain_loss`. Wrap with `safe_crypto_fx_rate`; if None, skip the transaction (the closing G/L can't be computed without a price — return 0 for that transaction's contribution).

Read each call site carefully before editing — preserve the surrounding logic. The unifying pattern: `safe_crypto_fx_rate` returns None → the transaction contributes 0 (skipped), not a crash.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/calculations/test_realized_option_paths.py::TestUnpricedCoinRealizedNoCrash -v`
Expected: PASS.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass. **Regression guard:** a fully-priced portfolio's realized unchanged (the None path never fires when prices exist).

- [ ] **Step 6: Commit**

```bash
"D:\Program Files (x86)\Git\cmd\git.exe" add backend/services/realized.py backend/tests/unit/calculations/test_realized_option_paths.py
"D:\Program Files (x86)\Git\cmd\git.exe" commit -m "fix(realized): safe_crypto_fx_rate guards — unpriced coins don't crash

An unpriced crypto coin (no Prices row, no trades) crashed realized_gain_loss
via transaction_fx_rate / calculate_buy_in_price / _realized_option_close.
Now wraps FX calls in safe_crypto_fx_rate (returns None+warning when unpriced);
None -> transaction contributes 0 (skipped), not a crash. Position still tracked."
```

---

### Task 5: Wire `safe_crypto_fx_rate` into `nav.py` (IRR, calculate_portfolio_cash, option-liability)

**Files:**
- Modify: `backend/services/nav.py` — `IRR` (~L540), `calculate_portfolio_cash` (~L446), option-liability loop (~L257).
- Test: `backend/tests/unit/calculations/test_nav_option_paths.py` or `test_irr_option_paths.py`.

**Interfaces:**
- Consumes: `safe_crypto_fx_rate` (Task 3).

- [ ] **Step 1: Write a failing test for unpriced-coin IRR**

Add to `backend/tests/unit/calculations/test_irr_option_paths.py`:

```python
@pytest.mark.nav
@pytest.mark.unit
class TestUnpricedCoinIRRNoCrash:
    """IRR over a portfolio containing an unpriced coin must not crash.
    It returns a Decimal or 'N/A' (the unpriced coin's flows are skipped)."""

    def test_irr_with_unpriced_coin_returns_decimal_or_na(self, user):
        from common.models import Accounts, Assets, Brokers, Transactions
        from services.nav import IRR
        from datetime import datetime, timezone
        broker = Brokers.objects.create(investor=user, name="OKX-UNP", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        # Fund the account
        Transactions.objects.create(investor=user, account=account, security=None, currency="USD",
            type="Cash in", date=datetime(2026, 1, 1, tzinfo=timezone.utc), cash_flow=Decimal("1000"))
        # An unpriced coin trade (no Prices row)
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:UNPIRR", name="UNPIRR",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Transactions.objects.create(investor=user, account=account, security=coin, currency="USDT",
            type="Crypto trade in", date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            quantity=Decimal("1"), price=Decimal("10"))
        # IRR must not crash on the unpriced coin.
        result = IRR(user.id, date(2026, 6, 1), account_ids=[account.id], cached_nav=Decimal("1000"))
        assert isinstance(result, (Decimal, str))  # Decimal rate or "N/A"/"N/R"
```

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/calculations/test_irr_option_paths.py::TestUnpricedCoinIRRNoCrash -v`
Expected: FAIL — `ValueError: No USD price for UNPIRR`.

- [ ] **Step 3: Wire `safe_crypto_fx_rate` into the nav.py crash sites**

Add the import to `backend/services/nav.py`:
```python
from services.crypto import safe_crypto_fx_rate
```

**(a) `IRR` (~L540):** the per-transaction FX call. Wrap with `safe_crypto_fx_rate`; if None, skip the transaction (contributes 0 to the cash-flow list). Read the current loop — it builds `cash_flows` / `transaction_dates` lists. The guard: if the FX rate is None, `continue` (skip this transaction).

**(b) `calculate_portfolio_cash` (~L446):** the per-currency FX call. If None, skip that currency (don't add to the portfolio cash total).

**(c) Option-liability loop (~L257):** the `get_fx_rate(security.currency, target_currency, date)` for the option's settle coin. If None, skip the option from the Securities breakdown (it's unvalued) with a warning — same as the spot-crypto loop pattern at ~L279.

Read each site carefully; the pattern is uniform: `safe_crypto_fx_rate` returns None → skip (continue), not crash.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/calculations/test_irr_option_paths.py::TestUnpricedCoinIRRNoCrash -v`
Expected: PASS.

- [ ] **Step 5: Run the full unit + integration suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
"D:\Program Files (x86)\Git\cmd\git.exe" add backend/services/nav.py backend/tests/unit/calculations/test_irr_option_paths.py
"D:\Program Files (x86)\Git\cmd\git.exe" commit -m "fix(nav): safe_crypto_fx_rate guards in IRR/portfolio-cash/option-liability

IRR, calculate_portfolio_cash, and the option-liability loop crashed on unpriced
coins (ValueError). Now wraps FX calls in safe_crypto_fx_rate; None -> skip the
transaction/currency/option (continue), not a crash. IRR returns Decimal/N/A."
```

---

## Task 6: Final verification + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest --no-cov -q`
Expected: all pass.

- [ ] **Step 2: Verify against live data (TRUMP unpriced; option ITM exit_value)**

Use the venv python to check:
- TRUMP `realized_gain_loss` returns `{total: ...}` (no crash; uses last-trade 16.557 fallback).
- TRUMP `IRR` returns a Decimal or "N/A" (no crash).
- An ITM option's closed-positions `exit_value` is correct (no double-contract_size) — construct a synthetic ITM if your data only has OTM.

- [ ] **Step 3: Push to PR #40**

```bash
"D:\Program Files (x86)\Git\cmd\git.exe" push origin feat/crypto-option-accounting
```

---

## Self-Review

**1. Spec coverage:**
- §3 (ITM exit_value) → Task 1 (`option_transaction_value` + tables_utils).
- §4 (unpriced resilience) → Tasks 3-5 (resolver + realized guards + nav guards).
- §5 (USD premium routing) → Task 2 (`CASH_CURRENCIES` + currency-aware `balance()`).

**2. Placeholder scan:** Task 1 Step 6 (ITM test fixture) says "mirror the existing test's fixture" — concrete enough (the existing test's `_make_btc_underlying` + pinned Prices row pattern is referenced). Task 4 Step 3 says "Read each call site carefully" — the exact guard pattern (`safe_crypto_fx_rate` returns None → 0/skip) is specified per site. No TBDs.

**3. Type consistency:** `option_transaction_value(transaction, contract_size, fx_rate) -> Decimal` consistent across Task 1. `CASH_CURRENCIES` used in Tasks 2 + balance_tracker. `crypto_usd_price_with_fallback` / `safe_crypto_fx_rate` consistent across Tasks 3-5. `Optional[Decimal]` return type for the None-on-unpriced path.

**4. Sequencing rationale:** Phase A (Task 1) and Phase B (Task 2) are independent and low-risk — ship first. Phase C (Tasks 3-5) is the broadest; the resolver (Task 3) is additive, then wired in Tasks 4-5. Each phase independently testable.
