"""Tests for the shared securities resolve-or-create helper.

Spec: docs/superpowers/specs/2026-07-21-shared-securities-resolve-design.md
"""
import pytest

from common.models import Assets
from users.models import CustomUser

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
