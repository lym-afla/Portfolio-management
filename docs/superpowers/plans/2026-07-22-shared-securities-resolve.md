# Shared Securities Resolve-or-Create Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the multi-user "add security" crash by routing all 7 security-resolve call sites through a single `resolve_or_create_asset` helper that links existing securities instead of recreating them.

**Architecture:** A new `backend/services/asset_resolver.py` owns the lookup→link→create flow. Two modes: `interactive` (manual "Add Security" UI — raises `AssetConflict` → HTTP 409 → frontend diff dialog → confirm round-trip) and `silent` (broker importers — just link + fill empties). No schema change, no financial-output change.

**Tech Stack:** Django 4.x / DRF (backend), Vue 3 + Vuetify 3 Composition API (frontend), pytest (tests). All commands run from `backend/` via `uv run`.

## Global Constraints

- **No schema change.** `uv run python manage.py makemigrations --check` must report "No changes".
- **No protected-code policy applies** (all touched files are outside the globs in `AGENTS.md`).
- **Numeric safety:** use `Decimal` for all monetary fields (`initial_notional`, `coupon_rate`); never `float`. Existing serializer `Decimal` discipline preserved.
- **Match key:** `(ISIN, currency)` — the existing `unique_asset_currency_entry` global constraint. Never overwritten.
- **Fill-empty-only policy:** an existing non-null field is never overwritten by a second user's submission.
- **Import path convention:** `from common.models import Assets, BondMetadata` (absolute, confirmed across codebase).
- **Test invocation:** `cd backend && uv run python -m pytest <path> -v --no-cov` for single files; `uv run python -m pytest` for the full suite.
- **Spec:** `docs/superpowers/specs/2026-07-21-shared-securities-resolve-design.md`

---

## File Structure

**Create:**
- `backend/services/asset_resolver.py` — the resolve-or-create helper + `ResolveResult` dataclass + `AssetConflict` exception + `BOND_FIELDS` constant. Single responsibility: own the shared-asset lookup→link→create flow.
- `backend/tests/integration/database/test_asset_resolver.py` — 13 tests covering all helper branches, races, bond metadata, and the API 409/201 flow.

**Modify:**
- `backend/database/serializers.py` — rewire `SecuritySerializer.create` to delegate to the helper; add `confirm` write-only field; replace local `bond_fields` tuple with imported `BOND_FIELDS`.
- `backend/database/views.py` — `api_create_security` catches `AssetConflict` → HTTP 409.
- `backend/services/importer.py` — 4 call sites unified (lines ~1634, ~1818, ~2065, ~2999). Convert `BondMetadata.objects.create` at ~1690, ~2156 to use the helper's upsert.
- `backend/services/crypto_exchange.py` — 2 already-correct call sites unified (`resolve_crypto_asset` ~88, `resolve_crypto_option_asset` ~104).
- `backend/tests/integration/database/test_constraints.py` — rename misleading test.
- `frontend/src/services/api.ts` — add typed return for 409 conflict payload.
- `frontend/src/components/dialogs/SecurityFormDialog.vue` — conflict sub-view + confirm round-trip.

---

## Task 1: Scaffold asset_resolver.py — types, constants, exception, empty function

**Files:**
- Create: `backend/services/asset_resolver.py`
- Test: `backend/tests/integration/database/test_asset_resolver.py`

**Interfaces:**
- Produces: `BOND_FIELDS` (frozenset[str]), `ResolveResult` (dataclass), `AssetConflict` (Exception), `resolve_or_create_asset(*, user, isin, currency, submitted_fields, mode, confirm=False) -> ResolveResult`.

- [ ] **Step 1: Write the failing import test**

```python
# backend/tests/integration/database/test_asset_resolver.py
"""Tests for the shared securities resolve-or-create helper.

Spec: docs/superpowers/specs/2026-07-21-shared-securities-resolve-design.md
"""
import pytest

from services.asset_resolver import (
    BOND_FIELDS,
    AssetConflict,
    ResolveResult,
    resolve_or_create_asset,
)


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestAssetResolverScaffold:
    """Smoke tests that the module's public surface is importable."""

    def test_bond_fields_is_frozenset(self) -> None:
        assert isinstance(BOND_FIELDS, frozenset)
        assert "initial_notional" in BOND_FIELDS
        assert "coupon_rate" in BOND_FIELDS

    def test_resolve_result_is_dataclass(self) -> None:
        r = ResolveResult(asset=None, created=False, linked=False)
        assert r.created is False
        assert r.linked is False
        assert r.field_diff == {}

    def test_asset_conflict_carries_payload(self) -> None:
        conflict = AssetConflict(asset="fake", field_diff={"x": 1}, fillable=["y"])
        assert conflict.asset == "fake"
        assert conflict.field_diff == {"x": 1}
        assert conflict.fillable == ["y"]
```

- [ ] **Step 2: Run test to verify it fails (module not found)**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.asset_resolver'`

- [ ] **Step 3: Create the module with types, constant, exception, and a `NotImplementedError` stub**

```python
# backend/services/asset_resolver.py
"""Resolve-or-create shared Assets (securities).

Single source of truth for the multi-user securities lookup→link→create flow.
The Assets table is a shared global catalog (unique on ISIN+currency); users
opt into securities via the Assets.investors M2M rather than creating duplicates.

See docs/superpowers/specs/2026-07-21-shared-securities-resolve-design.md.
"""
from dataclasses import dataclass, field
from typing import Literal

from common.models import Assets, BondMetadata
from users.models import CustomUser

# Bond-metadata field names. These map to BondMetadata rows, not Assets columns.
# The helper owns this list so it doesn't depend on the serializer's private tuple.
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
    """Outcome of a resolve-or-create call."""
    asset: Assets
    created: bool          # True only if a brand-new Assets row was inserted
    linked: bool           # True if an existing asset was newly linked to this user
    field_diff: dict = field(default_factory=dict)


class AssetConflict(Exception):
    """Raised in interactive mode (confirm=False) when an existing asset is found
    that the requesting user does not yet have linked.

    The caller (view) catches this and returns HTTP 409 with the diff payload so
    the frontend can prompt the user for confirmation.
    """

    def __init__(self, asset: Assets, field_diff: dict, fillable: list):
        self.asset = asset
        self.field_diff = field_diff
        self.fillable = fillable
        super().__init__(f"Asset already exists: {asset.ISIN}/{asset.currency}")


def resolve_or_create_asset(
    *,
    user: CustomUser,
    isin: str,
    currency: str,
    submitted_fields: dict,
    mode: Literal["silent", "interactive"],
    confirm: bool = False,
) -> ResolveResult:
    """Look up an existing Assets row by (ISIN, currency); link the user and/or
    create the row according to mode. See module docstring and spec for details.
    """
    raise NotImplementedError("Implemented in later tasks")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/asset_resolver.py backend/tests/integration/database/test_asset_resolver.py
git commit -m "feat: scaffold asset_resolver module with types and stub"
```

---

## Task 2: Implement internal helpers + create branch (no existing asset)

Implements: `_is_empty`, `_split_bond_fields`, `_upsert_bond_metadata`, `_fill_empty_fields` (used later), and branch A of `resolve_or_create_asset` (no existing asset → create + link).

**Files:**
- Modify: `backend/services/asset_resolver.py`
- Test: `backend/tests/integration/database/test_asset_resolver.py`

**Interfaces:**
- Consumes: `Assets`, `BondMetadata` from `common.models`.
- Produces: working `resolve_or_create_asset` for the create branch (existing=None case).

- [ ] **Step 1: Add the failing test for the create branch**

Append to `TestAssetResolverScaffold` or add a new class in `test_asset_resolver.py`:

```python
from common.models import Assets
from users.models import CustomUser


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveCreateBranch:
    """Branch A: no existing asset → create + link."""

    def test_resolve_creates_new_asset_for_first_user(self, user: CustomUser) -> None:
        result = resolve_or_create_asset(
            user=user,
            isin="US9999999999",
            currency="USD",
            submitted_fields={
                "name": "Test Stock",
                "type": "Stock",
                "exposure": "Equity",
            },
            mode="silent",
        )
        assert result.created is True
        assert result.linked is False  # first user linked during create, not "linked to existing"
        assert result.asset.pk is not None
        assert result.asset.ISIN == "US9999999999"
        assert result.asset.currency == "USD"
        assert result.asset.name == "Test Stock"
        assert list(result.asset.investors.all()) == [user]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py::TestResolveCreateBranch -v --no-cov`
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Implement internal helpers and the create branch**

Replace the `resolve_or_create_asset` stub (and add helpers above it) in `backend/services/asset_resolver.py`:

```python
from django.db import IntegrityError, transaction


def _is_empty(value) -> bool:
    """True if a model field value counts as 'unset'."""
    return value is None or value == ""


def _split_bond_fields(submitted_fields: dict) -> tuple[dict, dict]:
    """Separate Assets column fields from BondMetadata fields.

    Returns (asset_fields, bond_fields).
    """
    asset_fields = {k: v for k, v in submitted_fields.items() if k not in BOND_FIELDS}
    bond_fields = {k: v for k, v in submitted_fields.items() if k in BOND_FIELDS}
    return asset_fields, bond_fields


def _upsert_bond_metadata(asset: Assets, bond_fields: dict) -> None:
    """Idempotent BondMetadata upsert. No-op for non-bonds or empty data."""
    if not bond_fields or asset.type != "Bond":
        return
    BondMetadata.objects.update_or_create(asset=asset, defaults=bond_fields)


def _fill_empty_fields(asset: Assets, asset_fields: dict) -> list:
    """Set asset columns only where the existing value is null/empty.

    ISIN and currency (the match key) are never overwritten. Returns the list
    of field names actually changed (for save(update_fields=...)).
    """
    changed = []
    for field_name, value in asset_fields.items():
        if field_name in ("ISIN", "currency"):
            continue
        if _is_empty(value):
            continue
        if _is_empty(getattr(asset, field_name, None)):
            setattr(asset, field_name, value)
            changed.append(field_name)
    if changed:
        asset.save(update_fields=changed)
    return changed


def resolve_or_create_asset(
    *,
    user: CustomUser,
    isin: str,
    currency: str,
    submitted_fields: dict,
    mode: Literal["silent", "interactive"],
    confirm: bool = False,
) -> ResolveResult:
    asset_fields, bond_fields = _split_bond_fields(submitted_fields)
    # Always use the lookup keys as the authoritative ISIN/currency on the row.
    asset_fields["ISIN"] = isin
    asset_fields["currency"] = currency

    try:
        existing = Assets.objects.get(ISIN=isin, currency=currency)
    except Assets.DoesNotExist:
        existing = None

    # Branch A: no existing asset → create (both modes).
    if existing is None:
        with transaction.atomic():
            try:
                asset = Assets.objects.create(**asset_fields)
                created = True
            except IntegrityError:
                # Race: another transaction inserted the same (ISIN, currency)
                # between our get() and create(). Re-fetch and treat as existing.
                asset = Assets.objects.get(ISIN=isin, currency=currency)
                created = False
            linked = False
            if user is not None and not asset.investors.filter(pk=user.pk).exists():
                asset.investors.add(user)
                linked = True
            _upsert_bond_metadata(asset, bond_fields)
        return ResolveResult(asset=asset, created=created, linked=linked, field_diff={})

    raise NotImplementedError("Existing-asset branches implemented in Task 3-4")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: PASS (4 tests — 3 scaffold + 1 create)

- [ ] **Step 5: Commit**

```bash
git add backend/services/asset_resolver.py backend/tests/integration/database/test_asset_resolver.py
git commit -m "feat: implement create branch + internal helpers in asset_resolver"
```

---

## Task 3: Implement silent mode (existing asset → link + fill empties)

Implements branch B: existing asset found, `mode="silent"` → link user if not linked, fill empty fields, upsert bond metadata.

**Files:**
- Modify: `backend/services/asset_resolver.py`
- Test: `backend/tests/integration/database/test_asset_resolver.py`

- [ ] **Step 1: Add the failing tests for silent mode**

Append to `test_asset_resolver.py`:

```python
@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveSilentMode:
    """Branch B: existing asset + silent mode → link + fill empties."""

    def _create_existing(self, user, **overrides):
        """Helper: create an asset owned by user with optional field overrides."""
        defaults = {
            "type": "Stock",
            "ISIN": "US8888888888",
            "name": "Existing Stock",
            "currency": "USD",
            "exposure": "Equity",
        }
        defaults.update(overrides)
        asset = Assets.objects.create(**defaults)
        asset.investors.add(user)
        return asset

    def test_resolve_links_existing_asset_to_second_user_silent(
        self, user: CustomUser
    ) -> None:
        from users.models import CustomUser as User

        user_a = User.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        user_b = User.objects.create_user(
            username="userb", email="b@example.com", password="pass123"
        )
        self._create_existing(user_a)

        result = resolve_or_create_asset(
            user=user_b,
            isin="US8888888888",
            currency="USD",
            submitted_fields={"name": "Existing Stock", "type": "Stock"},
            mode="silent",
        )
        assert result.created is False
        assert result.linked is True
        assert list(result.asset.investors.all()) == [user_a, user_b]

    def test_resolve_second_user_same_security_no_duplicate_rows(
        self, user: CustomUser
    ) -> None:
        """Direct regression for the original IntegrityError bug."""
        from users.models import CustomUser as User

        user_a = User.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        user_b = User.objects.create_user(
            username="userb", email="b@example.com", password="pass123"
        )
        resolve_or_create_asset(
            user=user_a,
            isin="US7777777777",
            currency="USD",
            submitted_fields={"name": "Shared Stock", "type": "Stock"},
            mode="silent",
        )
        resolve_or_create_asset(
            user=user_b,
            isin="US7777777777",
            currency="USD",
            submitted_fields={"name": "Shared Stock", "type": "Stock"},
            mode="silent",
        )
        assert Assets.objects.filter(ISIN="US7777777777", currency="USD").count() == 1

    def test_resolve_silent_fills_empty_fields_only(self, user: CustomUser) -> None:
        existing = Assets.objects.create(
            type="Stock",
            ISIN="US6666666666",
            name="Has Gap",
            currency="USD",
            exposure="Equity",
            ticker=None,  # empty — should be filled
        )
        existing.investors.add(user)

        resolve_or_create_asset(
            user=user,
            isin="US6666666666",
            currency="USD",
            submitted_fields={"ticker": "GAP", "name": "Has Gap", "type": "Stock"},
            mode="silent",
        )
        existing.refresh_from_db()
        assert existing.ticker == "GAP"

    def test_resolve_silent_does_not_overwrite_existing_field(
        self, user: CustomUser
    ) -> None:
        existing = Assets.objects.create(
            type="Stock",
            ISIN="US5555555555",
            name="Has Ticker",
            currency="USD",
            exposure="Equity",
            ticker="OLD",
        )
        existing.investors.add(user)

        resolve_or_create_asset(
            user=user,
            isin="US5555555555",
            currency="USD",
            submitted_fields={"ticker": "NEW", "name": "Has Ticker", "type": "Stock"},
            mode="silent",
        )
        existing.refresh_from_db()
        assert existing.ticker == "OLD"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py::TestResolveSilentMode -v --no-cov`
Expected: FAIL — `NotImplementedError` (existing-asset branch not yet implemented)

- [ ] **Step 3: Implement silent mode**

Replace the `raise NotImplementedError(...)` line at the end of `resolve_or_create_asset` with:

```python
    # Branches B/C/D: existing asset found.
    already_linked = (
        existing.investors.filter(pk=user.pk).exists() if user is not None else True
    )

    if mode == "silent":
        # Branch B: link + fill empties + upsert bond metadata. No conflict.
        with transaction.atomic():
            linked = False
            if user is not None and not already_linked:
                existing.investors.add(user)
                linked = True
            _fill_empty_fields(existing, asset_fields)
            _upsert_bond_metadata(existing, bond_fields)
        return ResolveResult(
            asset=existing, created=False, linked=linked, field_diff={}
        )

    raise NotImplementedError("Interactive branches implemented in Task 4")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/asset_resolver.py backend/tests/integration/database/test_asset_resolver.py
git commit -m "feat: implement silent mode (link + fill empties) in asset_resolver"
```

---

## Task 4: Implement interactive mode + AssetConflict (branches C and D)

Implements: `_compute_diff` helper, branch C (interactive, `confirm=False`, not already linked → raise `AssetConflict`), branch D (interactive, `confirm=True` OR already linked → link + fill + return success).

**Files:**
- Modify: `backend/services/asset_resolver.py`
- Test: `backend/tests/integration/database/test_asset_resolver.py`

- [ ] **Step 1: Add the failing tests for interactive mode**

Append to `test_asset_resolver.py`:

```python
@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveInteractiveMode:
    """Branches C (raise conflict) and D (confirm → link + fill)."""

    def _create_existing_for_other_user(self):
        from users.models import CustomUser as User

        user_a = User.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        asset = Assets.objects.create(
            type="Stock",
            ISIN="US4444444444",
            name="User A Stock",
            currency="USD",
            exposure="Equity",
            ticker="OLD",
        )
        asset.investors.add(user_a)
        return user_a, asset

    def test_resolve_interactive_first_user_creates_no_conflict(
        self, user: CustomUser
    ) -> None:
        """First user's interactive call has no existing asset → create."""
        result = resolve_or_create_asset(
            user=user,
            isin="US3333333333",
            currency="USD",
            submitted_fields={"name": "Brand New", "type": "Stock"},
            mode="interactive",
        )
        assert result.created is True

    def test_resolve_interactive_raises_conflict_for_second_user(
        self, user: CustomUser
    ) -> None:
        _user_a, _asset = self._create_existing_for_other_user()

        with pytest.raises(AssetConflict) as exc_info:
            resolve_or_create_asset(
                user=user,
                isin="US4444444444",
                currency="USD",
                submitted_fields={
                    "name": "My Name",
                    "type": "Stock",
                    "ticker": "NEW",
                },
                mode="interactive",
                confirm=False,
            )
        conflict = exc_info.value
        assert conflict.asset.ISIN == "US4444444444"
        # ticker differs (OLD vs NEW) and existing is non-empty → in field_diff
        assert "ticker" in conflict.field_diff
        assert conflict.field_diff["ticker"]["existing"] == "OLD"
        assert conflict.field_diff["ticker"]["submitted"] == "NEW"

    def test_resolve_interactive_confirm_links_and_fills(
        self, user: CustomUser
    ) -> None:
        _user_a, asset = self._create_existing_for_other_user()

        result = resolve_or_create_asset(
            user=user,
            isin="US4444444444",
            currency="USD",
            submitted_fields={
                "name": "User A Stock",
                "type": "Stock",
                "comment": "added by second user",
            },
            mode="interactive",
            confirm=True,
        )
        assert result.created is False
        assert result.linked is True
        asset.refresh_from_db()
        assert user in list(asset.investors.all())
        # comment was empty → filled
        assert asset.comment == "added by second user"

    def test_resolve_already_linked_user_returns_noop(
        self, user: CustomUser
    ) -> None:
        """User re-adds a security they already have → success, no conflict."""
        asset = Assets.objects.create(
            type="Stock",
            ISIN="US2222222222",
            name="My Stock",
            currency="USD",
            exposure="Equity",
        )
        asset.investors.add(user)

        result = resolve_or_create_asset(
            user=user,
            isin="US2222222222",
            currency="USD",
            submitted_fields={"name": "My Stock", "type": "Stock"},
            mode="interactive",
            confirm=False,
        )
        assert result.created is False
        assert result.linked is False  # already linked → no change
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py::TestResolveInteractiveMode -v --no-cov`
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Implement `_compute_diff` and interactive branches**

Add `_compute_diff` above `resolve_or_create_asset`, and replace the trailing `raise NotImplementedError(...)` with the interactive logic:

```python
def _compute_diff(asset: Assets, asset_fields: dict) -> tuple[dict, list]:
    """Compute the (field_diff, fillable) payload for an AssetConflict.

    field_diff: {field: {"existing": <val>, "submitted": <val>}} for fields where
                the existing value is non-empty AND differs from the submission.
    fillable:   [field, ...] where the existing value is empty and the submission
                has a value to contribute.
    """
    field_diff = {}
    fillable = []
    for field_name, submitted in asset_fields.items():
        if field_name in ("ISIN", "currency"):
            continue
        if _is_empty(submitted):
            continue
        existing_val = getattr(asset, field_name, None)
        if _is_empty(existing_val):
            fillable.append(field_name)
        elif existing_val != submitted:
            field_diff[field_name] = {
                "existing": existing_val,
                "submitted": submitted,
            }
    return field_diff, fillable
```

Then the final branch of `resolve_or_create_asset` (replacing the last `raise NotImplementedError`):

```python
    # mode == "interactive"
    if confirm or already_linked:
        # Branch D (confirm=True) or already-linked no-op:
        # link if needed, fill empties, upsert bond metadata. No conflict raised.
        with transaction.atomic():
            linked = False
            if user is not None and not already_linked:
                existing.investors.add(user)
                linked = True
            _fill_empty_fields(existing, asset_fields)
            _upsert_bond_metadata(existing, bond_fields)
        return ResolveResult(
            asset=existing, created=False, linked=linked, field_diff={}
        )

    # Branch C: interactive, confirm=False, not already linked → raise conflict.
    field_diff, fillable = _compute_diff(existing, asset_fields)
    raise AssetConflict(asset=existing, field_diff=field_diff, fillable=fillable)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/asset_resolver.py backend/tests/integration/database/test_asset_resolver.py
git commit -m "feat: implement interactive mode + AssetConflict in asset_resolver"
```

---

## Task 5: Race-safety regression test for the create branch

Verifies the `IntegrityError` catch in branch A: when a concurrent insert happens between the `get()` and `create()`, the helper re-fetches instead of crashing.

**Files:**
- Modify: `backend/tests/integration/database/test_asset_resolver.py`

- [ ] **Step 1: Add the failing race test**

Append to `test_asset_resolver.py`:

```python
from unittest.mock import patch
from django.db import IntegrityError


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveRaceSafety:
    """The create branch must survive a concurrent insert (IntegrityError)."""

    def test_resolve_confirm_race_falls_back_to_existing(
        self, user: CustomUser
    ) -> None:
        """Simulate: another transaction inserts the same (ISIN, currency)
        between our get() and create(). The helper must re-fetch and link,
        not raise IntegrityError."""
        isin = "US1111111111"
        currency = "USD"

        # Pre-create the asset *after* the helper's initial get() returns DoesNotExist
        # but *before* its create() runs. We do this by patching Assets.objects.create
        # to first insert the row, then raise IntegrityError (simulating a real race).
        real_create = Assets.objects.create

        def rigged_create(**kwargs):
            # Simulate the race: insert the row now, then raise as if we lost the race
            real_create(**kwargs)
            raise IntegrityError("simulated concurrent insert")

        with patch.object(Assets.objects, "create", side_effect=rigged_create):
            result = resolve_or_create_asset(
                user=user,
                isin=isin,
                currency=currency,
                submitted_fields={"name": "Raced Stock", "type": "Stock"},
                mode="silent",
            )

        # The helper recovered: it re-fetched the existing row and linked the user.
        assert result.created is False
        assert result.asset.ISIN == isin
        assert user in list(result.asset.investors.all())
        assert Assets.objects.filter(ISIN=isin, currency=currency).count() == 1
```

- [ ] **Step 2: Run test to verify it passes (race handling already implemented in Task 2)**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py::TestResolveRaceSafety -v --no-cov`
Expected: PASS — the `try/except IntegrityError` in branch A (Task 2) already handles this.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/database/test_asset_resolver.py
git commit -m "test: add race-safety regression for asset_resolver create branch"
```

---

## Task 6: BondMetadata idempotency across users

Verifies that two users adding the same bond results in exactly one `BondMetadata` row, correctly populated.

**Files:**
- Modify: `backend/tests/integration/database/test_asset_resolver.py`

- [ ] **Step 1: Add the failing bond metadata test**

Append to `test_asset_resolver.py`:

```python
from common.models import BondMetadata
from decimal import Decimal


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveBondMetadata:
    """BondMetadata upsert must be idempotent across users."""

    def test_resolve_bond_metadata_upsert_idempotent(
        self, user: CustomUser
    ) -> None:
        from users.models import CustomUser as User

        user_a = User.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        user_b = User.objects.create_user(
            username="userb", email="b@example.com", password="pass123"
        )
        bond_fields = {
            "name": "Govt Bond 2030",
            "type": "Bond",
            "currency": "USD",
            "exposure": "Fixed Income",
            "initial_notional": Decimal("1000.00"),
            "coupon_rate": Decimal("5.25"),
            "coupon_frequency": 2,
        }

        # User A creates the bond.
        resolve_or_create_asset(
            user=user_a,
            isin="USBOND000001",
            currency="USD",
            submitted_fields=bond_fields,
            mode="silent",
        )
        # User B adds the same bond.
        resolve_or_create_asset(
            user=user_b,
            isin="USBOND000001",
            currency="USD",
            submitted_fields=bond_fields,
            mode="silent",
        )

        asset = Assets.objects.get(ISIN="USBOND000001", currency="USD")
        assert BondMetadata.objects.filter(asset=asset).count() == 1
        meta = asset.bondmetadata_metadata
        assert meta.initial_notional == Decimal("1000.00")
        assert meta.coupon_rate == Decimal("5.25")
        assert meta.coupon_frequency == 2
```

- [ ] **Step 2: Run test to verify it passes (upsert already implemented in Task 2)**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py::TestResolveBondMetadata -v --no-cov`
Expected: PASS — `_upsert_bond_metadata` uses `update_or_create` (Task 2).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/database/test_asset_resolver.py
git commit -m "test: add bond metadata idempotency test for asset_resolver"
```

---

## Task 7: Rewire SecuritySerializer.create + api_create_security view

Wires the manual "Add Security" endpoint to use the helper in interactive mode. Adds the `confirm` write-only field to the serializer and the HTTP 409 conflict response to the view.

**Files:**
- Modify: `backend/database/serializers.py:798-967` (`SecuritySerializer`)
- Modify: `backend/database/views.py:310-328` (`api_create_security`)
- Test: `backend/tests/integration/database/test_asset_resolver.py`

**Interfaces:**
- Consumes: `resolve_or_create_asset`, `AssetConflict` from `services.asset_resolver`; `BOND_FIELDS` from `services.asset_resolver`.

- [ ] **Step 1: Add the failing API-level tests**

Append to `test_asset_resolver.py`:

```python
from rest_framework.test import APIClient


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestApiCreateSecurityConflict:
    """View-level: POST /database/api/create-security/ returns 409 on conflict."""

    def _client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _security_payload(self, **overrides):
        payload = {
            "name": "API Test Stock",
            "ISIN": "USAPITEST001",
            "type": "Stock",
            "currency": "USD",
            "exposure": "Equity",
        }
        payload.update(overrides)
        return payload

    def test_api_create_security_returns_409_on_conflict(
        self, user: CustomUser
    ) -> None:
        from users.models import CustomUser as User

        user_a = User.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        client_a = self._client_for(user_a)
        client_b = self._client_for(user)

        # User A creates the security.
        resp_a = client_a.post(
            "/database/api/create-security/", self._security_payload()
        )
        assert resp_a.status_code == 201

        # User B submits the same (ISIN, currency) with a differing field.
        resp_b = client_b.post(
            "/database/api/create-security/",
            self._security_payload(name="Different Name"),
        )
        assert resp_b.status_code == 409
        body = resp_b.json()
        assert body["success"] is False
        assert body["conflict"] is True
        assert body["existing_asset"]["ISIN"] == "USAPITEST001"
        # name differs → in field_diff
        assert "name" in body["field_diff"]

    def test_api_create_security_confirm_returns_201(
        self, user: CustomUser
    ) -> None:
        from users.models import CustomUser as User

        user_a = User.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        client_a = self._client_for(user_a)
        client_b = self._client_for(user)

        client_a.post("/database/api/create-security/", self._security_payload())

        # User B confirms after seeing the conflict.
        resp = client_b.post(
            "/database/api/create-security/",
            {**self._security_payload(), "confirm": True},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["created"] is False
        assert body["linked"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py::TestApiCreateSecurityConflict -v --no-cov`
Expected: FAIL — the view still calls `serializer.save()` which calls the old `Assets.objects.create`; second user gets 500 (not 409).

- [ ] **Step 3: Rewire `SecuritySerializer.create`**

In `backend/database/serializers.py`, first add the import at the top (after the existing `from common.models import ...` block, around line 20):

```python
from services.asset_resolver import BOND_FIELDS, AssetConflict, resolve_or_create_asset
```

Then add a `confirm` write-only field to `SecuritySerializer` (inside the class, near the other field declarations around line 833):

```python
    confirm = serializers.BooleanField(required=False, default=False, write_only=True)
```

Add `"confirm"` to the `Meta.fields` list (after `"comment"`, the last entry around line 863):

```python
            "comment",
            "confirm",
        ]
```

Replace the `create` method (lines 921-944) entirely:

```python
    def create(self, validated_data):
        """Delegate to resolve_or_create_asset in interactive mode.

        May raise AssetConflict if the security already exists and the user has
        not confirmed. The view catches this and returns HTTP 409.
        """
        user = validated_data.pop("user", None)
        confirm = validated_data.pop("confirm", False)
        result = resolve_or_create_asset(
            user=user,
            isin=validated_data["ISIN"],
            currency=validated_data["currency"],
            submitted_fields=validated_data,
            mode="interactive",
            confirm=confirm,
        )
        return result.asset
```

Replace the local `bond_fields` tuple in `update` (lines 949-958) with the imported constant. The `update` method should now start:

```python
    def update(self, instance, validated_data):
        """Update the Asset fields and upsert bond metadata."""
        user = validated_data.pop("user", None)
        validated_data.pop("confirm", False)  # write-only, not used on update
        for field, value in validated_data.items():
            if field not in BOND_FIELDS:
                setattr(instance, field, value)
        instance.save()
        if user is not None and not instance.investors.filter(pk=user.pk).exists():
            instance.investors.add(user)
        self._save_bond_metadata(instance)
        return instance
```

And update `_save_bond_metadata` (lines 899-919) to use `BOND_FIELDS` instead of the hardcoded tuple:

```python
    def _save_bond_metadata(self, asset):
        """Upsert BondMetadata for a bond asset. No-op for non-bonds."""
        if asset.type != "Bond":
            return
        bond_data = {}
        for field in BOND_FIELDS:
            value = self.validated_data.get(field)
            if value is not None:
                bond_data[field] = value
        if bond_data:
            BondMetadata.objects.update_or_create(asset=asset, defaults=bond_data)
```

- [ ] **Step 4: Rewire `api_create_security` view**

In `backend/database/views.py`, add the import near the top (after the existing model/utility imports):

```python
from services.asset_resolver import AssetConflict
```

Replace the `api_create_security` function (lines 310-328):

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_security(request):
    """Create security via SecuritySerializer → resolve_or_create_asset."""
    serializer = SecuritySerializer(data=request.data)
    if serializer.is_valid():
        try:
            security = serializer.save(user=request.user)
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
                "message": "Security created successfully",
                "id": security.id,
                "name": security.name,
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(
        {"success": False, "errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: PASS (all tests including the two new API tests)

- [ ] **Step 6: Run the existing serializer tests to check for regressions**

Run: `cd backend && uv run python -m pytest tests/unit/test_security_serializer.py -v --no-cov`
Expected: PASS — if any fail, investigate before proceeding (do not tweak tests to mask failures).

- [ ] **Step 7: Commit**

```bash
git add backend/database/serializers.py backend/database/views.py backend/tests/integration/database/test_asset_resolver.py
git commit -m "feat: wire SecuritySerializer + view to resolve_or_create_asset (HTTP 409)"
```

---

## Task 8: Rename the misleading existing test

`test_asset_isin_different_users_allowed` in `test_constraints.py` only does `investors.add`, never creates a second asset. Rename it to reflect what it actually tests, and add a comment.

**Files:**
- Modify: `backend/tests/integration/database/test_constraints.py:65-85`

- [ ] **Step 1: Rename the test and update its docstring**

In `backend/tests/integration/database/test_constraints.py`, rename the method at line 71 and update its docstring:

Change:
```python
    def test_asset_isin_different_users_allowed(self) -> None:
        """Test that same ISIN can be used by different users."""
```

To:
```python
    def test_asset_investors_m2m_link_allowed(self) -> None:
        """Test that multiple users can be linked to the same Assets row via the
        investors M2M. (Does NOT test the create path — for that, see
        TestResolveSilentMode.test_resolve_second_user_same_security_no_duplicate_rows
        in test_asset_resolver.py.)"""
```

- [ ] **Step 2: Run the test to verify it still passes under the new name**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_constraints.py::TestAssetModelConstraints::test_asset_investors_m2m_link_allowed -v --no-cov`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/database/test_constraints.py
git commit -m "test: rename misleading test to reflect M2M-link coverage"
```

---

## Task 9: Unify the 3 buggy T-Bank/MICEX importer create call sites

Replaces `Assets.objects.create(...)` + `asset.investors.add(user)` + (separate) `BondMetadata.objects.create(...)` at three sites in `importer.py` with a single `resolve_or_create_asset(mode="silent", ...)` call. This also fixes the inconsistent `BondMetadata.objects.create` (non-idempotent) at lines ~1690 and ~2156 — the helper's `_upsert_bond_metadata` uses `update_or_create`.

**Files:**
- Modify: `backend/services/importer.py` — sites at ~1633-1690, ~1818-1829, ~2065-2080

**Interfaces:**
- Consumes: `resolve_or_create_asset` from `services.asset_resolver`.

- [ ] **Step 1: Add the import**

At the top of `backend/services/importer.py`, near the existing `from common.models import ...` (around line 70), add:

```python
from services.asset_resolver import resolve_or_create_asset
```

- [ ] **Step 2: Replace call site A — `create_asset_with_metadata` (~line 1633)**

Find the inner function `create_asset_with_metadata` inside `create_security_from_tinkoff` (around line 1611). Replace the body that does `Assets.objects.create(...)` + `asset.investors.add(user)` + `BondMetadata.objects.create(...)` with a single helper call. The current code (~lines 1633-1690) looks like:

```python
asset = Assets.objects.create(
    type=asset_type,
    ISIN=isin if isin else instrument_data.isin,
    name=instrument_data.name,
    currency=instrument_data.currency,
    exposure=exposure,
    restricted=False,
    data_source="TBANK",
    secid=instrument_data.ticker if hasattr(instrument_data, "ticker") else None,
    tbank_instrument_uid=instrument_uid,
)
asset.investors.add(user)
# ... BondMetadata.objects.create(asset=asset, **bond_data) if bond_data ...
```

Replace with:

```python
resolved_isin = isin if isin else instrument_data.isin
bond_kwargs = bond_data if bond_data else {}
result = resolve_or_create_asset(
    user=user,
    isin=resolved_isin,
    currency=instrument_data.currency,
    submitted_fields={
        "type": asset_type,
        "name": instrument_data.name,
        "exposure": exposure,
        "restricted": False,
        "data_source": "TBANK",
        "secid": instrument_data.ticker if hasattr(instrument_data, "ticker") else None,
        "tbank_instrument_uid": instrument_uid,
        **bond_kwargs,
    },
    mode="silent",
)
asset = result.asset
```

Remove the now-redundant `asset.investors.add(user)` and `BondMetadata.objects.create(...)` lines — the helper handles both.

- [ ] **Step 3: Replace call site B — `create_basic_asset` (~line 1818)**

Find the inner function `create_basic_asset` inside `_create_basic_tbank_asset` (around line 1797). The current code (~lines 1818-1829):

```python
asset = Assets.objects.create(
    type=asset_type,
    ISIN=isin,
    ticker=ticker,
    name=security_name,
    currency="RUB",
    exposure=exposure,
    restricted=False,
    data_source="TBANK",
    secid=None,
    tbank_instrument_uid=instrument_uid,
)
asset.investors.add(user)
return asset
```

Replace with:

```python
result = resolve_or_create_asset(
    user=user,
    isin=isin,
    currency="RUB",
    submitted_fields={
        "type": asset_type,
        "ticker": ticker,
        "name": security_name,
        "exposure": exposure,
        "restricted": False,
        "data_source": "TBANK",
        "secid": None,
        "tbank_instrument_uid": instrument_uid,
    },
    mode="silent",
)
return result.asset
```

- [ ] **Step 4: Replace call site C — `create_asset_and_metadata` (~line 2065)**

Find the inner function `create_asset_and_metadata` inside `create_security_from_micex` (around line 2062). The current code (~lines 2065-2080):

```python
asset = Assets.objects.create(
    type=asset_type,
    ISIN=security_data["isin"] or isin,
    name=security_data["name"],
    ticker=ticker,
    currency=security_data["currency"],
    exposure=exposure,
    restricted=False,
    data_source="MICEX",
    secid=security_data["secid"],
)
asset.investors.add(user)
# ... BondMetadata.objects.create(asset=asset, **bond_data) if bond_data ...
```

Replace with:

```python
resolved_isin = security_data["isin"] or isin
bond_kwargs = bond_data if bond_data else {}
result = resolve_or_create_asset(
    user=user,
    isin=resolved_isin,
    currency=security_data["currency"],
    submitted_fields={
        "type": asset_type,
        "name": security_data["name"],
        "ticker": ticker,
        "exposure": exposure,
        "restricted": False,
        "data_source": "MICEX",
        "secid": security_data["secid"],
        **bond_kwargs,
    },
    mode="silent",
)
asset = result.asset
```

Remove the now-redundant `asset.investors.add(user)` and `BondMetadata.objects.create(...)` lines.

- [ ] **Step 5: Run existing importer tests to verify no regressions**

Run: `cd backend && uv run python -m pytest tests/ -k "import" -v --no-cov`
Expected: PASS — all importer tests pass unchanged. If any fail, investigate the behavior change (do not tweak tests to mask it).

- [ ] **Step 6: Commit**

```bash
git add backend/services/importer.py
git commit -m "refactor: unify 3 T-Bank/MICEX importer create sites via resolve_or_create_asset"
```

---

## Task 10: Unify the 2 already-correct call sites (crypto + importer two-step)

Replaces the local `get_or_create` + `investors.add` patterns in `crypto_exchange.py` (2 sites) and the two-step ISIN lookup in `importer.py:_find_or_create_security` (1 site) with calls to the shared helper.

**Files:**
- Modify: `backend/services/crypto_exchange.py:88-127`
- Modify: `backend/services/importer.py:2999-3018`

- [ ] **Step 1: Add the import to `crypto_exchange.py`**

At the top of `backend/services/crypto_exchange.py`, add:

```python
from services.asset_resolver import resolve_or_create_asset
```

- [ ] **Step 2: Replace `resolve_crypto_asset` (~line 88)**

Current code (lines 88-101):

```python
def resolve_crypto_asset(symbol, user):
    normalized_symbol = str(symbol).upper()
    asset, _ = Assets.objects.get_or_create(
        ISIN=_crypto_asset_identifier(normalized_symbol),
        currency="USD",
        defaults={
            "type": ASSET_TYPE_CRYPTO,
            "name": normalized_symbol,
            "ticker": normalized_symbol[:10],
            "exposure": "FX" if normalized_symbol in STABLECOINS else "Commodity",
        },
    )
    asset.investors.add(user)
    return asset
```

Replace with:

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
        },
        mode="silent",
    )
    return result.asset
```

- [ ] **Step 3: Replace `resolve_crypto_option_asset` Assets-row portion (~line 113)**

In `resolve_crypto_option_asset`, the Assets-row `get_or_create` + `investors.add` (lines ~113-123) is replaced, but the `OptionMetadata.objects.get_or_create` block stays unchanged. Current code:

```python
    asset, _ = Assets.objects.get_or_create(
        ISIN=_crypto_asset_identifier(f"OPT:{option_symbol}"),
        currency=asset_currency,
        defaults={
            "type": "Option",
            "name": option_symbol,
            "ticker": option_symbol[:10],
            "exposure": "Derivatives",
        },
    )
    asset.investors.add(user)
```

Replace with:

```python
    result = resolve_or_create_asset(
        user=user,
        isin=_crypto_asset_identifier(f"OPT:{option_symbol}"),
        currency=asset_currency,
        submitted_fields={
            "type": "Option",
            "name": option_symbol,
            "ticker": option_symbol[:10],
            "exposure": "Derivatives",
        },
        mode="silent",
    )
    asset = result.asset
```

Leave the subsequent `OptionMetadata.objects.get_or_create(asset=asset, defaults={...})` block exactly as-is.

- [ ] **Step 4: Replace the two-step ISIN lookup in `_find_or_create_security` (~line 2999)**

In `backend/services/importer.py`, find `_find_or_create_security` (line 2979). The two loops at lines ~2999-3018 currently do:

1. Loop 1: `Assets.objects.get(ISIN=sec[1], investors=investor)` → return `"existing_with_relationships"`
2. Loop 2: `Assets.objects.get(ISIN=sec[1])` + `investors.add(investor)` → return `"existing_added_relationships"`

Replace both loops with a single loop that discovers the currency from any existing row, then delegates to the helper:

```python
    # Resolve existing securities: find by ISIN, then use the helper to link+fill.
    for sec in securities_found:
        candidate_isin = sec[1]
        existing = Assets.objects.filter(ISIN=candidate_isin).first()
        if existing is None:
            continue
        result = await database_sync_to_async(resolve_or_create_asset)(
            user=investor,
            isin=candidate_isin,
            currency=existing.currency,
            submitted_fields={},
            mode="silent",
        )
        status_str = (
            "existing_with_relationships"
            if not result.linked
            else "existing_added_relationships"
        )
        return result.asset, status_str
```

This preserves the status-string contract (`existing_with_relationships` / `existing_added_relationships`) that the caller relies on. The fall-through to `create_security_from_micex` (now itself using the helper from Task 9) remains unchanged.

- [ ] **Step 5: Run crypto and importer tests**

Run: `cd backend && uv run python -m pytest tests/ -k "crypto or import" -v --no-cov`
Expected: PASS — all tests pass unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/services/importer.py
git commit -m "refactor: unify crypto + importer two-step lookup via resolve_or_create_asset"
```

---

## Task 11: Frontend — typed conflict payload + conflict sub-view in SecurityFormDialog

Adds a typed return for the 409 payload in `api.ts` and a conflict sub-view (field-diff table + fillable list + confirm button) in `SecurityFormDialog.vue`.

**Files:**
- Modify: `frontend/src/services/api.ts:463-473`
- Modify: `frontend/src/components/dialogs/SecurityFormDialog.vue`

- [ ] **Step 1: Add typed conflict interfaces and update `createSecurity` in `api.ts`**

In `frontend/src/services/api.ts`, add types above the `createSecurity` function (around line 460):

```typescript
export interface SecurityFieldDiffEntry {
  existing: unknown
  submitted: unknown
}

export interface SecurityConflictPayload {
  success: false
  conflict: true
  existing_asset: {
    id: number
    name: string
    ISIN: string
    currency: string
  }
  field_diff: Record<string, SecurityFieldDiffEntry>
  fillable: string[]
}

export function isSecurityConflictPayload(
  data: unknown
): data is SecurityConflictPayload {
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as Record<string, unknown>).conflict === true
  )
}
```

The existing `createSecurity` function (lines 463-473) stays unchanged — it already throws `error.response.data`, which the dialog will now type-check using `isSecurityConflictPayload`.

- [ ] **Step 2: Add conflict state to `SecurityFormDialog.vue` script**

In `frontend/src/components/dialogs/SecurityFormDialog.vue`, add the import and state. First, update the import from `@/services/api` (around line 121):

```javascript
import {
  createSecurity,
  updateSecurity,
  getSecurityFormStructure,
  isSecurityConflictPayload,
} from '@/services/api'
import type { SecurityConflictPayload } from '@/services/api'
```

Then, near the other `ref` declarations (around line 149), add:

```javascript
const conflictData = ref<SecurityConflictPayload | null>(null)
```

- [ ] **Step 3: Update `submitForm` to handle the 409 conflict**

Replace the `catch` block in `submitForm` (the `} catch (error) { ... }` portion, lines ~207-227). The new version detects a conflict payload and stores it for the sub-view instead of showing a generic error:

```javascript
  } catch (error) {
    logger.error('Unknown', 'Error submitting security:', error)

    // Check for a 409 conflict payload from resolve_or_create_asset.
    if (isSecurityConflictPayload(error)) {
      conflictData.value = error
      return  // Don't close the dialog — show the conflict sub-view.
    }

    // Existing per-field error handling (HTTP 400 from DRF).
    if (error.errors) {
      Object.keys(error.errors).forEach((key) => {
        if (key === '__all__') {
          generalError.value = error.errors[key][0]
        } else {
          errorMessages.value[key] = Array.isArray(error.errors[key])
            ? error.errors[key]
            : [error.errors[key]]
        }
      })
    } else {
      generalError.value =
        error.message || 'An unexpected error occurred. Please try again.'
    }
  } finally {
```

- [ ] **Step 4: Add a `confirmConflict` handler**

Below `submitForm`, add:

```javascript
const confirmConflict = async () => {
  isSubmitting.value = true
  generalError.value = ''
  try {
    const response = await createSecurity({ ...form.value, confirm: true })
    emit('security-added', response)
    conflictData.value = null
    closeDialog()
  } catch (error) {
    logger.error('Unknown', 'Error confirming conflict:', error)
    generalError.value =
      error?.message || 'Failed to add security. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}

const cancelConflict = () => {
  conflictData.value = null
}
```

- [ ] **Step 5: Reset `conflictData` in `closeDialog`**

Find the existing `closeDialog` function and add `conflictData.value = null` inside it (next to the other resets like `generalError.value = ''`):

```javascript
const closeDialog = () => {
  // ... existing resets ...
  conflictData.value = null
  // ... emit('update:modelValue', false) etc. ...
}
```

- [ ] **Step 6: Add the conflict sub-view template**

In the `<template>` section, immediately after the existing `<v-alert v-if="generalError" ...>` block (around line 100-102), add the conflict panel. It must appear *before* the form fields so the user sees the diff context:

```html
      <!-- Conflict sub-view: security already exists in the shared catalog -->
      <v-alert
        v-if="conflictData"
        type="warning"
        variant="tonal"
        class="mt-3"
        prominent
      >
        <p class="font-weight-bold mb-2">
          This security already exists in the catalog:
          {{ conflictData.existing_asset.name }}
          ({{ conflictData.existing_asset.ISIN }} /
          {{ conflictData.existing_asset.currency }})
        </p>

        <v-table v-if="Object.keys(conflictData.field_diff).length > 0" density="compact" class="mb-3">
          <thead>
            <tr>
              <th>Field</th>
              <th>Catalog value</th>
              <th>Your submission</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(diff, field) in conflictData.field_diff"
              :key="field"
            >
              <td>{{ field }}</td>
              <td>{{ diff.existing }}</td>
              <td>{{ diff.submitted }}</td>
            </tr>
          </tbody>
        </v-table>

        <div v-if="conflictData.fillable.length > 0" class="mb-3">
          <p class="text-body-2 mb-1">Fields that will be added from your submission:</p>
          <v-chip
            v-for="field in conflictData.fillable"
            :key="field"
            size="small"
            class="mr-1 mb-1"
            color="success"
          >
            {{ field }}
          </v-chip>
        </div>

        <div class="d-flex gap-2 mt-2">
          <v-btn color="primary" variant="flat" @click="confirmConflict" :loading="isSubmitting">
            Add to my portfolio
          </v-btn>
          <v-btn variant="text" @click="cancelConflict">Cancel</v-btn>
        </div>
      </v-alert>
```

- [ ] **Step 7: Manually verify the frontend compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors. (If the project uses `npm run lint`, run that too.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/components/dialogs/SecurityFormDialog.vue
git commit -m "feat: add conflict sub-view + confirm round-trip to SecurityFormDialog"
```

---

## Task 12: Final verification — full test suite + migration check

Runs all tests and the migration guard to confirm no regressions and no schema change.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest --no-cov -q`
Expected: PASS — all tests green. Any failure must be investigated (do not tweak tests to mask failures).

- [ ] **Step 2: Verify no schema change**

Run: `cd backend && uv run python manage.py makemigrations --check`
Expected: output contains "No changes detected" (or "Your models in app(s): ... have changes..." — the latter would be a failure; the plan adds no model fields).

- [ ] **Step 3: Run the complete asset_resolver test file one more time**

Run: `cd backend && uv run python -m pytest tests/integration/database/test_asset_resolver.py -v --no-cov`
Expected: PASS — all 13+ tests green.

- [ ] **Step 4: Run the frontend build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: both succeed.

- [ ] **Step 5: Final commit (if any cleanup needed) — otherwise done**

If steps 1-4 all pass without changes, no commit is needed. The branch is ready for PR.

---

## Self-Review Checklist (completed by plan author)

**1. Spec coverage:**
- §1 (Problem): fixed by Tasks 2-4 (helper) + Task 7 (view) + Task 9-10 (importers). ✓
- §2 (Goals): G1 crash fix (Tasks 2-4), G2 link not recreate (Tasks 2-4), G3 diff dialog (Task 11), G4 fill empties (Task 3), G5 unify all sites (Tasks 9-10). ✓
- §3 (UX): manual flow (Task 11), silent importer (Tasks 9-10). ✓
- §4.1 (Helper): all branches A-D implemented (Tasks 2-4), race safety (Task 5), BondMetadata (Task 6). ✓
- §4.2 (API): view rewired (Task 7), 409 response (Task 7). ✓
- §4.3 (Frontend): conflict sub-view (Task 11). ✓
- §4.4 (Importer unification): 4 buggy + 2 correct sites unified (Tasks 9-10). ✓
- §5 (Protected code): no protected globs touched; confirmed in Global Constraints. ✓
- §6 (Testing): 13 tests across Tasks 2-7, rename in Task 8, existing importer tests unchanged. ✓
- §7 (Out of scope): respected — no schema change, no per-user fields, no ISIN relaxation. ✓

**2. Placeholder scan:** No "TBD", "TODO", "implement later", "add error handling", or "similar to Task N" found. All steps contain concrete code. ✓

**3. Type consistency:** `resolve_or_create_asset` signature consistent across all 7 call sites: `(*, user, isin, currency, submitted_fields, mode, confirm=False)`. `ResolveResult` fields (`asset`, `created`, `linked`, `field_diff`) consistent between definition (Task 1) and consumers (Tasks 2-7). `AssetConflict` attributes (`asset`, `field_diff`, `fillable`) consistent between definition (Task 1) and view catch (Task 7). `BOND_FIELDS` consistent between definition (Task 1) and serializer import (Task 7). ✓

**4. Cross-cutting concern — BondMetadata inconsistency:** The importer's `BondMetadata.objects.create` at lines ~1690 and ~2156 (non-idempotent) is eliminated in Task 9 — the helper's `_upsert_bond_metadata` uses `update_or_create`, so retry/linking is safe. ✓

**5. Cross-cutting concern — investor variable naming:** Call sites use `user` (sites A, B, C, crypto) and `investor` (site D, `_find_or_create_security`). The helper normalizes this — all sites pass the user as `user=` regardless of local variable name. ✓
