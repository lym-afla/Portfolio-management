"""Tests for SecuritySerializer."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from common.models import Assets, BondMetadata
from database.serializers import SecuritySerializer

CustomUser = get_user_model()


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="serializertest", password="pw")


@pytest.fixture
def valid_security_data():
    return {
        "name": "Test Equity",
        "ISIN": "US0000000000",
        "type": "Stock",
        "currency": "USD",
        "exposure": "Equity",
    }


@pytest.mark.django_db
def test_security_serializer_creates_asset_and_links_investor(user, valid_security_data):
    """SecuritySerializer.create adds the requesting user as an investor."""
    serializer = SecuritySerializer(data=valid_security_data)
    assert serializer.is_valid(), serializer.errors

    asset = serializer.save(user=user)

    assert asset.id is not None
    assert asset.name == "Test Equity"
    assert asset.investors.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_security_serializer_creates_bond_metadata(user):
    """When type is Bond and bond fields are present, metadata is upserted."""
    data = {
        "name": "Test Bond",
        "ISIN": "US1111111111",
        "type": "Bond",
        "currency": "USD",
        "exposure": "FI",
        "initial_notional": "1000.00",
        "nominal_currency": "USD",
        "coupon_rate": "5.2500",
        "coupon_frequency": 2,
    }
    serializer = SecuritySerializer(data=data)
    assert serializer.is_valid(), serializer.errors

    asset = serializer.save(user=user)
    asset.refresh_from_db()

    bond_meta = BondMetadata.objects.get(asset=asset)
    assert bond_meta.initial_notional == Decimal("1000.00")
    assert bond_meta.coupon_rate == Decimal("5.2500")
    assert bond_meta.coupon_frequency == 2


@pytest.mark.django_db
def test_security_serializer_validates_data_source_requires_symbol(user):
    """data_source=YAHOO without yahoo_symbol is invalid."""
    data = {
        "name": "Bad Equity",
        "ISIN": "US2222222222",
        "type": "Stock",
        "currency": "USD",
        "exposure": "Equity",
        "data_source": "YAHOO",
    }
    serializer = SecuritySerializer(data=data)
    assert not serializer.is_valid()
    assert "yahoo_symbol" in serializer.errors


@pytest.mark.django_db
def test_security_serializer_update_preserves_investors(user, valid_security_data):
    """Updating an asset does not drop existing investors."""
    serializer = SecuritySerializer(data=valid_security_data)
    serializer.is_valid(raise_exception=True)
    asset = serializer.save(user=user)

    update_serializer = SecuritySerializer(asset, data={"name": "Renamed"}, partial=True)
    update_serializer.is_valid(raise_exception=True)
    updated = update_serializer.save(user=user)

    assert updated.name == "Renamed"
    assert updated.investors.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_security_serializer_update_upserts_bond_metadata(user):
    """Update on a bond asset upserts BondMetadata."""
    data = {
        "name": "Bond To Update",
        "ISIN": "US3333333333",
        "type": "Bond",
        "currency": "USD",
        "exposure": "FI",
    }
    serializer = SecuritySerializer(data=data)
    serializer.is_valid(raise_exception=True)
    asset = serializer.save(user=user)

    update_data = {
        "initial_notional": "2000.00",
        "coupon_rate": "3.0000",
        "coupon_frequency": 4,
    }
    update_serializer = SecuritySerializer(asset, data=update_data, partial=True)
    update_serializer.is_valid(raise_exception=True)
    update_serializer.save(user=user)

    bond_meta = BondMetadata.objects.get(asset=asset)
    assert bond_meta.initial_notional == Decimal("2000.00")
    assert bond_meta.coupon_rate == Decimal("3.0000")
    assert bond_meta.coupon_frequency == 4


@pytest.mark.django_db
def test_api_create_security_endpoint(user):
    """The api_create_security endpoint creates a security via the serializer."""
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/database/api/create-security/",
        {
            "name": "Endpoint Test",
            "ISIN": "US4444444444",
            "type": "Stock",
            "currency": "USD",
            "exposure": "Equity",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.data["success"] is True
    created = Assets.objects.get(name="Endpoint Test")
    assert created.investors.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_api_security_form_structure_returns_frontend_type_names(user):
    """The form-structure endpoint must return widget-style type names the
    frontend's SecurityFormDialog.vue switches on (textinput, numberinput,
    checkbox, select, dateinput, url, etc.) — not raw DRF class names.
    """
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/database/api/security-form-structure/")

    assert response.status_code == 200, response.content
    fields = {f["name"]: f for f in response.data["fields"]}

    # Spot-check: every field type must be one the frontend recognizes
    valid_frontend_types = {
        "textinput",
        "numberinput",
        "dateinput",
        "checkbox",
        "select",
        "selectmultiple",
        "textarea",
        "url",
    }
    for name, field in fields.items():
        assert field["type"] in valid_frontend_types, (
            f"Field '{name}' has type '{field['type']}' which the frontend "
            f"SecurityFormDialog.vue does not handle"
        )

    # Specific mappings that matter for form rendering
    assert fields["name"]["type"] == "textinput"
    assert fields["initial_notional"]["type"] == "numberinput"
    assert fields["restricted"]["type"] == "checkbox"
    assert fields["currency"]["type"] == "select"
    assert fields["issue_date"]["type"] == "dateinput"
    assert fields["update_link"]["type"] == "url"
