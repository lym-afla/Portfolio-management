# Shared Securities Resolve-or-Create — Design

**Date:** 2026-07-21
**Status:** Approved (brainstorming complete; pending implementation plan)
**Scope:** Fix the multi-user "add security" crash + unify all security-resolve code paths behind one helper.

---

## 1. Problem

Users cannot add a security that another user has already added. The symptom is an
HTTP 500 from the backend surfacing in the frontend as a generic
"An unexpected error occurred." dialog.

### Root cause

`Assets` is already a **single shared securities table**. Migration `0046` removed
the old per-user `Assets.investor` FK and replaced it with
`Assets.investors = ManyToManyField(CustomUser)`. Migration `0085` added a **global**
unique constraint `unique_asset_currency_entry` on `(ISIN, currency)`.

Reads, updates, and deletes correctly scope via `investors=user` / `investors__id`
throughout the codebase. **Only the create path fails to honor the shared-table
design.** Specifically `SecuritySerializer.create`
(`backend/database/serializers.py:921-944`):

```python
asset = Assets.objects.create(**asset_fields)   # raises IntegrityError on dup (ISIN, currency)
if user is not None:
    asset.investors.add(user)                    # only runs if create succeeded
```

When user B submits a `(ISIN, currency)` that user A already created, the DB raises
`IntegrityError` on `unique_asset_currency_entry`. The exception is uncaught,
propagates as HTTP 500 with no JSON body, and the frontend's
`SecurityFormDialog.vue` falls into its generic catch-all.

The same latent bug exists at three other broker-importer call sites
(`backend/services/importer.py:1634`, `:1818`, `:2065`), which would crash
identically if two users imported the same instrument.

### Existing correct patterns (precedent)

Two call sites already implement the correct shared-table behavior and serve as the
template for this design:

- `backend/services/crypto_exchange.py:88-101` — `get_or_create(ISIN=..., currency=..., defaults={...})` then `investors.add(user)`.
- `backend/services/importer.py:2999-3018` — explicit two-step lookup: try `Assets.objects.get(ISIN=..., investors=investor)`; on `DoesNotExist`, fetch the shared asset and link it.

### Misleading test coverage

`backend/tests/integration/database/test_constraints.py:65-85`
(`test_asset_isin_different_users_allowed`) is named as if it tests the multi-user
create path, but it only calls `asset1.investors.add(user2)` — it never creates a
second `Assets` row. The actual conflict path was never regression-tested.

---

## 2. Goals & non-goals

### Goals

1. Eliminate the `IntegrityError` crash on multi-user security creation.
2. When user B adds a security that already exists, **link** it to B rather than
   recreating it — preserving the single-shared-table invariant.
3. Show user B a transparent field-diff dialog so they understand the security
   already exists and can choose to add it.
4. Fill empty fields on the shared record (only) when the user supplies values the
   record doesn't yet have.
5. Unify all 7 security-resolve call sites behind one helper so the bug class
   cannot be reintroduced.

### Non-goals

- **No schema change.** `makemigrations --check` must report "No changes".
- **No change to financial outputs.** NAV, positions, realized/unrealized gains,
  FX — all unchanged. Linking vs creating is an additive data operation.
- **No per-user fields on `Assets`.** The shared record stays shared; field-filling
  is the only way a second user can enrich it.
- **No overwrite of existing non-null fields.** Per the chosen policy, an existing
  value always wins.
- **No new audit trail.** Out of scope for this change; if audit becomes a
  requirement later it will be a separate spec.

---

## 3. User experience

### Manual "Add Security" (interactive)

1. User fills in the security form and clicks Save.
2. If the security is **new** to the global catalog: created normally, success
   toast, dialog closes. No change from today.
3. If the security **already exists** and the user **already has it**: success
   ("you already have this security"), dialog closes. No duplicate work.
4. If the security **already exists** and the user **does not have it**: dialog
   switches to a "conflict" sub-view showing:
   - The existing asset's identity (name, ISIN, currency).
   - A field-by-field diff: "existing vs your submission" for fields where they
     differ and the existing value is non-empty.
   - A list of **fillable** fields: fields the existing record doesn't have yet
     that the user's submission would supply ("your value will be added").
   - Buttons: **Add to my portfolio** (re-submits with confirmation) and
     **Cancel**.
5. On confirm: the security is linked to the user, fillable empty fields are
   populated, BondMetadata is upserted if relevant, success toast, dialog closes.

### Broker importer (silent)

No UX change. When an importer encounters an instrument that already exists in the
catalog, it silently links the user and fills empty fields. This is the existing
behavior of the two correct call sites; the four buggy sites gain the same
robustness.

---

## 4. Architecture

### 4.1 New module: `backend/services/asset_resolver.py`

A new file in the existing `services/` package (which already contains
`securities.py`, `crypto_exchange.py`, `importer.py`). It is deliberately outside
the protected-code globs defined in `AGENTS.md`.

#### Public API

```python
from dataclasses import dataclass
from typing import Literal

# Bond-metadata field names. These are not columns on Assets — they map to
# BondMetadata rows. The helper owns this list so it does not depend on the
# serializer for field separation.
BOND_FIELDS: frozenset[str] = frozenset({
    "initial_notional",
    "nominal_currency",
    "issue_date",
    "maturity_date",
    "coupon_rate",
    "coupon_frequency",
    "is_amortizing",
    "bond_type",
    "credit_rating",
})

@dataclass
class ResolveResult:
    asset: Assets
    created: bool          # True only if a brand-new Assets row was inserted
    linked: bool           # True if an existing asset was newly linked to this user
    field_diff: dict       # {field_name: {"existing": <val>, "submitted": <val>}}
                           # empty unless an existing record was found with differing non-empty values

class AssetConflict(Exception):
    """Raised by resolve_or_create_asset in interactive mode when an existing
    asset is found that the user does not yet have linked."""
    def __init__(self, asset, field_diff, fillable):
        self.asset = asset
        self.field_diff = field_diff
        self.fillable = fillable
        super().__init__(f"Asset already exists: {asset.ISIN}/{asset.currency}")

def resolve_or_create_asset(
    *,
    user: CustomUser,
    isin: str,
    currency: str,
    submitted_fields: dict,        # full set of submitted Asset fields + bond fields
    mode: Literal["silent", "interactive"],
    confirm: bool = False,         # interactive mode only — True on the second (confirming) call
) -> ResolveResult: ...
```

`BOND_FIELDS` is exported as the single source of truth for what counts as bond
metadata. `SecuritySerializer._save_bond_metadata` is updated to import it rather
than redefining its own tuple, so the two cannot drift.

#### Behavior

The function performs a lookup on `Assets.objects.get(ISIN=isin, currency=currency)`
(wrapped in `try/except Assets.DoesNotExist`) and branches:

**A. No existing asset (both modes):**
- Create a new `Assets` row with the non-bond fields from `submitted_fields`.
- Link `user` via `investors.add(user)`.
- Upsert BondMetadata if `type == "Bond"` and bond fields were supplied.
- Return `ResolveResult(created=True, linked=False, field_diff={})`.

**B. Existing asset found — silent mode (importers):**
- If user not yet linked: `investors.add(user)`, set `linked=True`.
- Fill empty fields: for each submitted field where the existing value is null/empty,
  set it to the submitted value. Existing non-null values are **never** overwritten.
- Upsert BondMetadata (idempotent via `update_or_create`).
- Return `ResolveResult(created=False, linked=<bool>, field_diff={})`.

**C. Existing asset found — interactive mode, `confirm=False`:**
- If user already linked: fill empty fields on the shared record (same as silent
  mode B), then return `ResolveResult(created=False, linked=False, field_diff={})`
  — treat as a no-op success ("you already have this"). No conflict is raised
  because there is nothing to ask; empty-field enrichment still happens so the
  behavior matches silent mode.
- Otherwise (user not yet linked):
  - Compute `field_diff`: for each submitted non-empty field where the existing
    value differs **and the existing value is non-empty**, record
    `{"existing": <val>, "submitted": <val>}`.
  - Compute `fillable`: list of field names where the existing value is null/empty
    and the user supplied a non-empty value.
  - Raise `AssetConflict(asset=existing, field_diff=..., fillable=...)`.

**D. Existing asset found — interactive mode, `confirm=True`:**
- Behave like silent mode (B): link the user, fill empty fields, upsert bond
  metadata, return `ResolveResult(created=False, linked=True, field_diff={})`.

#### Race safety

Two race scenarios are handled so that no `IntegrityError` can escape:

1. **Interactive confirm race:** between the 409 response and the `confirm=True`
   call, another user inserts the same `(ISIN, currency)`. The confirm path wraps
   its final write in `transaction.atomic()` and re-performs the lookup; if the
   row now exists, it falls through to branch D rather than calling `create()`.
2. **Concurrent importer calls:** two importer calls racing to create the same
   instrument. The silent-mode create branch uses
   `transaction.atomic()` + `Assets.objects.get_or_create(ISIN=..., currency=...,
   defaults={...})`, so concurrent calls converge to a single linked asset.

For the fill-empty-fields writes, the existing row is read inside the transaction
and only null/empty fields are written back. The M2M `investors.add()` is itself
idempotent.

#### BondMetadata handling

Reuses the existing `update_or_create(asset=asset, defaults=bond_data)` pattern
from `SecuritySerializer._save_bond_metadata`. For non-bond submissions (the case
for all 6 importer call sites today) this is a no-op.

### 4.2 Backend API changes

`POST /database/api/create-security/` (`backend/database/views.py:310-328`) gains
conflict handling:

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_security(request):
    serializer = SecuritySerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"success": False, "errors": serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST)

    confirm = request.data.get("confirm", False) is True
    try:
        result = resolve_or_create_asset(
            user=request.user,
            isin=serializer.validated_data["ISIN"],
            currency=serializer.validated_data["currency"],
            submitted_fields=serializer.validated_data,
            mode="interactive",
            confirm=confirm,
        )
    except AssetConflict as e:
        return Response(
            {
                "success": False,
                "conflict": True,
                "existing_asset": {
                    "id": e.asset.id,
                    "name": e.asset.name,
                    "ISIN": e.asset.ISIN,
                    "currency": e.asset.currency,
                },
                "field_diff": e.field_diff,
                "fillable": e.fillable,
            },
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "success": True,
            "message": "Security created" if result.created else "Security linked to your portfolio",
            "id": result.asset.id,
            "name": result.asset.name,
            "created": result.created,
            "linked": result.linked,
        },
        status=status.HTTP_201_CREATED,
    )
```

`SecuritySerializer.create` is rewired to delegate to
`resolve_or_create_asset(mode="interactive")`. Validation logic
(`SecuritySerializer.validate`, `_save_bond_metadata`) is unchanged.

**HTTP semantics:**

| Status | Meaning |
|---|---|
| 201 | Security created or linked successfully. |
| 409 | Existing asset found; user must confirm before linking. Body carries `field_diff` + `fillable`. |
| 400 | Validation error (DRF serializer errors). Unchanged from today. |

### 4.3 Frontend changes — `SecurityFormDialog.vue`

The dialog's submit handler currently calls `createSecurity(form.value)` once and
branches on success (close) vs 400 (per-field errors). The new flow:

1. On submit, call `createSecurity({ ...form.value, confirm: false })`.
2. **201:** unchanged — success toast, close dialog, refresh securities list.
3. **400 with `errors`:** unchanged — per-field errors rendered inline.
4. **409 with `conflict: true`:** switch the dialog to a new **conflict sub-view**:
   - Show the existing asset's identity (name, ISIN, currency).
   - Render the `field_diff` as a two-column table: "Catalog value" vs "Your
     submission", one row per differing field.
   - Render the `fillable` list: "These fields will be added from your
     submission:" with each field name and the value to be added.
   - Buttons: **Add to my portfolio** and **Cancel**.
   - On "Add to my portfolio": re-call `createSecurity({ ...form.value, confirm: true })`.
     Expect 201 → close dialog, refresh list, success toast "Linked existing
     security".
5. The generic "An unexpected error occurred" catch-all remains only as a
   last-resort fallback for true network failures; the 409 path is now explicit.

**API service** (`frontend/src/services/api.ts:463-473`): the existing
`throw error.response ? error.response.data : error.message` behavior already
surfaces `conflict`, `field_diff`, and `fillable` on the thrown object. Add a
typed return type for the 409 payload to make the dialog code clearer.

### 4.4 Importer unification

All 6 importer call sites are replaced with a single call to
`resolve_or_create_asset(mode="silent", ...)`.

**Buggy sites** (currently `Assets.objects.create(...)` + `investors.add(user)`,
crash on conflict):

| File:line | Context |
|---|---|
| `backend/database/serializers.py:940` | Manual "Add Security" via `SecuritySerializer.create`. Rewired to call helper in interactive mode (see §4.1/§4.2). |
| `backend/services/importer.py:1634` | T-Bank importer create call. Replace with silent helper call. Drop manual `investors.add`. |
| `backend/services/importer.py:1818` | T-Bank importer create call. Same treatment. |
| `backend/services/importer.py:2065` | T-Bank importer create call. Same treatment. |

**Already-correct sites** (work today but duplicate logic being centralized):

| File:line | Context |
|---|---|
| `backend/services/crypto_exchange.py:88-101` | `resolve_crypto_asset` — replace local `get_or_create` + `investors.add` with silent helper call. |
| `backend/services/importer.py:2999-3018` | Two-step "asset exists but not for this investor" lookup — collapse into single silent helper call. |

**Uniform call shape:**

```python
result = resolve_or_create_asset(
    user=investor,
    isin=sec.isin,
    currency=sec.currency,
    submitted_fields={
        "name": sec.name,
        "ticker": sec.ticker,
        "type": sec.type,
        "data_source": "TBANK",
        "tbank_instrument_uid": sec.figi,
        # ...all fields the site currently passes to create()
    },
    mode="silent",
)
asset = result.asset
```

**Async wrappers preserved:** all importer sites run inside async WebSocket
consumers. The helper is synchronous ORM code, so each call site continues to wrap
it in `database_sync_to_async(resolve_or_create_asset)(...)`. No change to async
structure.

**BondMetadata in importers:** none of the 6 importer sites currently create
BondMetadata. The helper's bond upsert is a no-op for non-bond submissions, so it
is safe to call uniformly.

**Behavior preservation contract:** the unification changes only the
resolve/create path. Transaction-import logic, dedup keys, downstream processing
— all untouched. Existing importer tests are the regression contract; any failure
signals a behavior change that must be investigated, not papered over.

---

## 5. Protected-code policy

Per `AGENTS.md`, the protected globs are `**/models.py`, `backend/core/*_utils.py`,
and a short list of specific functions. Files touched by this design:

- `backend/database/serializers.py` — **not protected**.
- `backend/database/views.py` — **not protected**.
- `backend/services/asset_resolver.py` — **new file, outside protected globs.** The `services/**` glob in older policy docs is explicitly documented in `AGENTS.md` as aspirational and not yet in force.
- `backend/services/importer.py`, `backend/services/crypto_exchange.py` — **not protected**.
- `frontend/**` — not protected.

**Conclusion:** no protected-code policy applies. This ships as a normal PR (no
`needs-approval` label) **provided** the change preserves financial outputs and
ships with the regression tests in §6. Both conditions hold by construction.

---

## 6. Testing

### New test file: `backend/tests/integration/database/test_asset_resolver.py`

All tests use `Decimal` for monetary fields per project convention.

| # | Test | Asserts |
|---|---|---|
| 1 | `test_resolve_creates_new_asset_for_first_user` | First call creates `Assets` row, links user, `result.created=True`. |
| 2 | `test_resolve_links_existing_asset_to_second_user_silent` | User B's silent-mode call on existing `(ISIN, currency)` links B without creating a new row; `result.created=False, linked=True`. |
| 3 | `test_resolve_second_user_same_security_no_duplicate_rows` | After both users add, exactly **one** `Assets` row exists for that `(ISIN, currency)`. (Direct regression for the original bug.) |
| 4 | `test_resolve_silent_fills_empty_fields_only` | Existing row has `ticker=None`; user B submits `ticker="AAPL"`; after silent resolve, row has `ticker="AAPL"`. |
| 5 | `test_resolve_silent_does_not_overwrite_existing_field` | Existing row has `ticker="OLD"`; user B submits `ticker="NEW"`; after silent resolve, row still has `ticker="OLD"`. |
| 6 | `test_resolve_interactive_first_user_creates_no_conflict` | First user's interactive call has no conflict, behaves like create. |
| 7 | `test_resolve_interactive_raises_conflict_for_second_user` | User B's interactive call with `confirm=False` raises `AssetConflict` with correct `field_diff` and `fillable` payload. |
| 8 | `test_resolve_interactive_confirm_links_and_fills` | After 409, user B's `confirm=True` call links B and fills empty fields. |
| 9 | `test_resolve_confirm_race_falls_back_to_existing` | Simulate: confirm path called when another transaction has already inserted the same key. Must not raise `IntegrityError`; must link the existing row. |
| 10 | `test_resolve_already_linked_user_returns_noop` | User A re-adds a security A already has → success, `created=False, linked=False`, no error. |
| 11 | `test_resolve_bond_metadata_upsert_idempotent` | Two users adding the same bond → exactly one `BondMetadata` row, correctly populated. |
| 12 | `test_api_create_security_returns_409_on_conflict` | View-level: POST twice with same `(ISIN, currency)` from different users → second gets 409 with `field_diff`. |
| 13 | `test_api_create_security_confirm_returns_201` | Follow-up POST with `confirm: true` → 201. |

### Existing test cleanup

`backend/tests/integration/database/test_constraints.py:65-85`
(`test_asset_isin_different_users_allowed`) is **renamed to
`test_asset_investors_m2m_link_allowed`** with a comment clarifying it exercises
the M2M link, not the create path. The multi-user create regression is now test #3
above.

### Existing importer tests

Run unchanged. If any break, the unification introduced a behavior change and the
failure must be investigated, not papered over by tweaking the test.

### Numeric safety

The helper uses `Decimal` for monetary fields (`initial_notional`, `coupon_rate`,
etc.) and never coerces to float. Existing `Decimal` discipline in the serializers
is preserved.

### CI gates

- `uv run python -m pytest` must pass.
- `uv run python manage.py makemigrations --check` must report "No changes".

---

## 7. Out of scope (explicit)

- Per-user fields on `Assets` (e.g., user-specific tickers or comments).
- Audit trail / change history on the shared `Assets` record.
- ISIN-less matching (e.g., for cash or crypto entries that may lack an ISIN). The
  match key stays `(ISIN, currency)`.
- Relaxing or removing the `unique_asset_currency_entry` constraint.
- Any change to NAV, positions, realized/unrealized, or FX logic.
- Frontend modernization (covered by separate Phase 2/3 specs).

---

## 8. Open questions

None. All design decisions resolved during brainstorming:

- Match key: `(ISIN, currency)` (existing constraint preserved).
- Duplicate behavior: notify with field diff + confirmation.
- Overwrite scope: fill empty fields only.
- Fix scope: all 7 sites unified behind one helper.
- Approach: HTTP 409 + confirm round-trip for manual add; silent link+fill for importers.
