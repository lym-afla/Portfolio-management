"""Pytest configuration and fixtures for the test suite.

This module provides common fixtures for testing including
user, broker, asset, and test environment setup.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from common.models import Assets, Brokers

CustomUser = get_user_model()


@pytest.fixture
def user():
    """Create a test user fixture.

    Returns:
        CustomUser: Test user instance.
    """
    return CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def broker(user):
    """Create a test broker fixture.

    Args:
        user: Test user fixture.

    Returns:
        Brokers: Test broker instance.
    """
    return Brokers.objects.create(
        investor=user, name="Test Broker", country="Test Country"
    )


@pytest.fixture
def asset(user, broker):
    """Create a test asset fixture.

    Args:
        user: Test user fixture.
        broker: Test broker fixture.

    Returns:
        Assets: Test asset instance.
    """
    asset = Assets.objects.create(
        type="Stock",
        ISIN="TEST123456789",
        name="Test Stock",
        currency="USD",
        exposure="Equity",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment with consistent encryption key."""
    # Use the same SECRET_KEY for all tests to ensure consistent encryption
    test_settings = {"SECRET_KEY": "test-secret-key-for-consistent-encryption"}
    with override_settings(**test_settings):
        yield
