"""Resolve-or-create shared Assets (securities).

Single source of truth for the multi-user securities lookup->link->create flow.
The Assets table is a shared global catalog (unique on ISIN+currency); users
opt into securities via the Assets.investors M2M rather than creating duplicates.

See docs/superpowers/specs/2026-07-21-shared-securities-resolve-design.md.
"""
from dataclasses import dataclass, field
from typing import Literal

from django.db import IntegrityError, transaction

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
        # Use repr so the message is safe for any object (the real Assets row in
        # production, or stand-ins in tests) without requiring ISIN/currency attrs.
        super().__init__(f"Asset already exists: {asset!r}")


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
    """Look up an existing Assets row by (ISIN, currency); link the user and/or
    create the row according to mode. See module docstring and spec for details.
    """
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
                with transaction.atomic():
                    asset = Assets.objects.create(**asset_fields)
                    created = True
            except IntegrityError:
                # Race: another transaction inserted the same (ISIN, currency)
                # between our get() and create(). Re-fetch and treat as existing.
                # The inner atomic() is a savepoint that rolls back on the error,
                # leaving the outer transaction usable for the get() below.
                asset = Assets.objects.get(ISIN=isin, currency=currency)
                created = False
            linked = False
            if user is not None and not asset.investors.filter(pk=user.pk).exists():
                asset.investors.add(user)
                # Only the race path (re-fetched existing asset) counts as
                # "linked to existing"; a brand-new asset's first investor is
                # the creator, not a newly-linked user.
                linked = not created
            _upsert_bond_metadata(asset, bond_fields)
        return ResolveResult(asset=asset, created=created, linked=linked, field_diff={})

    raise NotImplementedError("Existing-asset branches implemented in Task 3-4")
