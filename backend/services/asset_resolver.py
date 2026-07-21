"""Resolve-or-create shared Assets (securities).

Single source of truth for the multi-user securities lookup->link->create flow.
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
        # Use repr so the message is safe for any object (the real Assets row in
        # production, or stand-ins in tests) without requiring ISIN/currency attrs.
        super().__init__(f"Asset already exists: {asset!r}")


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
