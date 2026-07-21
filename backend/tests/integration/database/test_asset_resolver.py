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
