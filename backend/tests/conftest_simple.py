"""Simplified conftest file for pytest with working fixtures."""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from common.models import Assets, Brokers

CustomUser = get_user_model()


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment with consistent encryption key and decimal context."""
    # Use the same SECRET_KEY for all tests to ensure consistent encryption
    test_settings = {"SECRET_KEY": "test-secret-key-for-consistent-encryption"}
    with override_settings(**test_settings):
        yield


# ========== USER FIXTURES ==========


@pytest.fixture
def user(db):
    """Create a basic test user."""
    return CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user for permission testing."""
    return CustomUser.objects.create_user(
        username="adminuser",
        email="admin@example.com",
        password="adminpass123",
        is_staff=True,
        is_superuser=True,
    )


# ========== BROKER FIXTURES ==========


@pytest.fixture
def broker(user):
    """Create a basic test broker."""
    return Brokers.objects.create(investor=user, name="Test Broker", country="US")


# ========== ASSET FIXTURES ==========


@pytest.fixture
def asset(user):
    """Create a basic USD stock asset."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="US1234567890",
        name="Test Stock Corp",
        currency="USD",
        exposure="Equity",
        data_source="YAHOO",
        yahoo_symbol="TEST",
    )
    asset.investors.add(user)
    return asset
