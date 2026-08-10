"""Tests for the shared securities resolve-or-create helper.

Spec: docs/superpowers/specs/2026-07-21-shared-securities-resolve-design.md
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from common.models import Assets, BondMetadata
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
        # name also differs ("User A Stock" vs "My Name") and existing is
        # non-empty → also in field_diff (exercises the multi-field case).
        assert "name" in conflict.field_diff
        assert conflict.field_diff["name"]["existing"] == "User A Stock"
        assert conflict.field_diff["name"]["submitted"] == "My Name"

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


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveRaceSafety:
    """The create branch must survive a concurrent insert (IntegrityError).

    Models a real cross-transaction race: T1 has already committed the row; T2's
    initial lookup returns DoesNotExist (stale snapshot); T2's create() then hits
    the real unique constraint and raises IntegrityError; T2's recovery get() finds
    T1's committed row and links the user instead of crashing.
    """

    def test_resolve_confirm_race_falls_back_to_existing(
        self, user: CustomUser
    ) -> None:
        isin = "US1111111111"
        currency = "USD"

        # Pre-insert the asset — simulates T1 having already committed the row.
        # Do NOT link `user` here; the helper's recovery should link them.
        raced = Assets.objects.create(
            type="Stock",
            ISIN=isin,
            name="Raced Stock",
            currency=currency,
            exposure="Equity",
        )

        # Patch the FIRST lookup only to raise DoesNotExist (T2's stale snapshot
        # that doesn't yet see T1's committed row). The SECOND lookup (the
        # recovery get in the except clause) returns the pre-inserted row.
        # The create() between them runs for real and raises a real IntegrityError
        # against the unique_asset_currency_entry constraint.
        with patch.object(
            Assets.objects,
            "get",
            side_effect=[Assets.DoesNotExist, raced],
        ):
            result = resolve_or_create_asset(
                user=user,
                isin=isin,
                currency=currency,
                submitted_fields={"name": "Raced Stock", "type": "Stock"},
                mode="silent",
            )

        # The helper recovered: it re-fetched T1's existing row and linked the user.
        assert result.created is False
        assert result.asset.ISIN == isin
        assert result.asset.pk == raced.pk
        assert user in list(result.asset.investors.all())
        assert Assets.objects.filter(ISIN=isin, currency=currency).count() == 1


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.django_db
class TestResolveBondMetadata:
    """BondMetadata upsert must be idempotent across users."""

    def test_resolve_bond_metadata_upsert_idempotent(self) -> None:
        user_a = CustomUser.objects.create_user(
            username="usera", email="a@example.com", password="pass123"
        )
        user_b = CustomUser.objects.create_user(
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
