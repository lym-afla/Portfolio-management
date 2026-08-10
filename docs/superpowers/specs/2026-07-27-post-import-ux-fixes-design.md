# Post-Crypto-Import UX Fixes — Design

**Date:** 2026-07-27
**Status:** Approved (brainstorming complete)
**Trigger:** Real browser testing of the OKX import flow (PR #15) surfaced four issues across frontend auth, import UX, and backend portfolio math.

This spec covers four independent fixes, sequenced into four PRs by risk/urgency. Each PR is independently mergeable.

---

## PR 1 — Frontend: break the JWT refresh deadlock

### Problem
When both access AND refresh tokens are expired (e.g. user left the page open overnight), the page freezes on the current route with no redirect to /login. Backend logs show repeated `JWT Middleware invalid token` / `Unauthorized`.

### Root cause
`frontend/src/config/axiosConfig.ts:147-223` — the response interceptor's refresh flow deadlocks:
1. Original request → 401 (access token expired).
2. Interceptor sets `isRefreshing=true`, calls `refreshToken()` which POSTs `/users/api/refresh-token/`.
3. The refresh request also gets 401 (refresh token expired) → re-enters the interceptor.
4. The re-entry hits `if (isRefreshing)` (still true from step 2) → pushes onto `failedQueue`, returns a Promise that **waits forever**.
5. `processQueue` is never called for that entry; `await refreshToken()` never resolves or rejects; `isRefreshing` stays true forever.
6. The only redirect (`window.location.href = '/login'` at line 214, inside the refresh-failure catch) is **never reached**. All subsequent requests pile onto `failedQueue`.

### Fix
Treat a 401 from `/refresh-token/` itself as terminal — skip the retry/queue machinery, clear tokens, redirect immediately. Guard `error.config` against undefined. Use the auth store's `logout()` (which already clears tokens + `router.push('/login')`) instead of `window.location.href` for SPA consistency.

**Files:** `frontend/src/config/axiosConfig.ts` only. Test: jest unit test on the interceptor with a mocked 401-on-refresh scenario.

### Out of scope
- Token-refresh window tuning (separate concern).
- Moving tokens to httpOnly cookies (architectural).

---

## PR 2 — Backend: surface import partial_failures + OKX deposit client-side date filter

### Problem
Two UX gaps in the OKX import:
- User requested range 2020–2023 but got recent deposits/rewards (range "ignored").
- No options/spot trades appeared, with no error visible.

### Root cause
- **Range "ignored":** OKX's `/api/v5/asset/deposit-history` and `/withdrawal-history` **silently ignore `begin`/`end`** and return most-recent-N. Our code sends the params correctly; OKX doesn't honor them. (Documented OKX API behavior.)
- **Silent no-data:** (a) OKX's `/api/v5/trade/fills-history` only retains 3 months — a 2020–2023 range returns empty (no error). (b) When endpoints DO error (e.g. `bills-archive`'s 180-day cap), the `_safe` wrapper in `OKXAPI.get_transactions` (`services/broker_api.py`) catches the exception and appends to `self.partial_failures` — but **`partial_failures` is never read or surfaced to the user**. The frontend import-progress UI doesn't display it. So a hard error looks identical to "no data in window."

### Fix (two parts)

**Part A — Surface `partial_failures`.** After the unified-stream import completes, the consumer should send a warning to the frontend listing which endpoints failed (or which returned data outside the requested window). The frontend `TransactionImportDialog` already has an `import_update` message channel; add a `partial_failures` field or a new `import_warnings` message type that the dialog renders as a warning banner. This converts silent failures into visible diagnostics. The user can then tell "no options because the endpoint failed" from "no options because you have none."

**Part B — Client-side deposit/withdrawal date filtering.** Since OKX ignores `begin`/`end` on deposit/withdrawal-history, apply the requested date window **after** fetching by filtering rows on `ts` in Python (`iter_deposits`/`iter_withdrawals`). This honors the user's explicit range. Caveat: if the user's requested range is far in the past, this may paginate through many recent rows before reaching the window — acceptable for correctness; can add an early-exit once rows older than the window start are seen (deposits return newest-first, so once `ts < start_ms` we can stop).

**Files:** `backend/services/broker_api.py` (read `partial_failures` and include in import result), `backend/transactions/consumers.py` (forward to frontend), `backend/core/crypto_exchange_clients.py` (client-side `ts` filter in `iter_deposits`/`iter_withdrawals`), `frontend/src/components/dialogs/TransactionImportDialog.vue` (render warnings). Tests for the date-filter and the partial-failure surfacing.

### Out of scope / accepted limitation
- OKX's 3-month `fills-history` retention is an API limit we cannot work around in code. Document it in the import dialog UI ("OKX only retains 3 months of trade fills; older trades cannot be imported"). The `partial_failures` surfacing + this notice together give the user an honest picture.
- ByBit is unaffected (its endpoints honor windows and have a 2-year retention, both already handled).

---

## PR 3 — Backend: guard `entry_price` None in open-positions table

### Problem
`GET /open_positions/api/get_open_positions_table/` → `TypeError: unsupported operand type(s) for *: 'NoneType' and 'decimal.Decimal'` when the portfolio contains a crypto asset that has only transfer-in/reward transactions (no buy trade).

### Root cause
`core/tables_utils.py:399` — `position["entry_value"] = position["entry_price"] * position["current_position"]`. For the USDT crypto asset, `calculate_buy_in_price` returns `None` (no buy-in to derive a cost basis from — the position was built entirely from deposits/rewards). The multiplication then crashes.

### Fix
Guard the multiplication: if `entry_price` is None, set `entry_value` to a sensible default (None, or 0, or skip the entry-value category for that asset). The semantically correct choice: **entry_value = None** (display as "—" in the table), because "no cost basis" is not the same as "zero cost basis." Review the surrounding code for other unguarded arithmetic on `entry_price` (e.g. realized/unrealized G&L calculations) — they likely have the same issue and need the same guard.

**Files:** `core/tables_utils.py` (guard at line 399 + audit neighbors), tests with a crypto asset that has deposits-only. This touches calculation-adjacent code — per `AGENTS.md`, treat as protected-adjacent: unit tests with Decimal + edge cases, regression fixture.

### Out of scope
- Defining a cost-basis convention for crypto (FIFO vs average vs "deposits have zero basis"). The fix is "don't crash"; the convention decision is separate. (A reasonable default: deposits/rewards give the asset a basis of 0, so entry_price could be `Decimal('0')` rather than None — but that's a behavior choice the user should make. This PR treats it as "don't crash" and surfaces the missing-basis case as "—".)

---

## PR 4 — Backend: guard `account_balance()[currency]` KeyError on accounts page

### Problem
`GET /database/api/accounts/list_accounts/` → `KeyError: 'USD'` when computing cash balances for accounts that include crypto.

### Root cause
`core/accounts_utils.py:123` — `account_balance(account, effective_current_date)[currency]` where `currency = 'USD'`. The balance dict doesn't contain `'USD'` for some accounts (crypto accounts whose balance is keyed differently, or accounts with no USD holdings). Direct subscript instead of `.get()`.

### Fix
Use `.get(currency, Decimal('0'))` (or whatever the established default is — check neighboring code for the convention). Audit `_get_accounts_data` for other unguarded dict subscripts on balance/currency lookups. Add a test with a crypto account in the fixture.

**Files:** `core/accounts_utils.py` (line 123 + audit), tests. Same protected-adjacent care as PR 3.

---

## Sequencing & risk

| PR | Risk | Why this order |
|---|---|---|
| 1 (auth) | Low | Self-contained frontend; unblocks all further testing by keeping you logged in. |
| 2 (import UX) | Medium | Backend + frontend; surfaces honest diagnostics; client-side date filter. |
| 3 (open-positions guard) | Medium-High | Protected-adjacent calc code; needs careful edge-case tests. |
| 4 (accounts guard) | Medium-High | Same calc-adjacent layer; similar guard pattern. |

Each PR is small, focused, and independently revertable.

## Open implementation-only questions (non-blocking)
- Exact default for missing `entry_price` in tables_utils: None vs Decimal('0'). Recommend None + display "—"; confirm during PR 3.
- Whether to early-exit `iter_deposits` pagination when rows go older than the window (perf optimization, not correctness). Add in PR 2 if cheap.
- The `partial_failures` message format — extend `import_update` payload vs new `import_warnings` message type. Decide in PR 2 based on what the frontend dialog handler already supports.
