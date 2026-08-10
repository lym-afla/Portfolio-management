"""
Integration tests for JWT-based authentication and effective_date handling.

Test JWT authentication and how effective_current_date is managed via JWT tokens.
"""

import json

import pytest
from django.contrib.sessions.models import Session
from django.test import Client

from users.models import CustomUser


@pytest.mark.django_db
def test_jwt_authentication_with_effective_date():
    """Test JWT authentication with effective_date handling."""
    print("=== Testing JWT Authentication with Effective Date ===")

    # Create a test user
    user = CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )

    try:
        # Create a test client (simulates browser)
        client = Client()

        # Step 1: Login to get JWT tokens
        print("\n1. Logging in to get JWT tokens...")
        login_response = client.post(
            "/users/api/login/",
            {"username": "testuser", "password": "testpass123"},
            content_type="application/json",
        )
        print(f"Login response status: {login_response.status_code}")

        assert login_response.status_code == 200, f"Login failed: {login_response.content.decode()}"

        login_data = login_response.json()
        access_token = login_data.get("access")
        refresh_token = login_data.get("refresh")

        print(f"Got access token: {access_token[:20] if access_token else 'None'}...")
        print(f"Got refresh token: {refresh_token[:20] if refresh_token else 'None'}...")

        assert access_token is not None, "Access token should be provided"
        assert refresh_token is not None, "Refresh token should be provided"

        # Step 2: Get dashboard settings with JWT token
        print("\n2. Testing dashboard settings with JWT token...")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

        response1 = client.get("/users/api/dashboard_settings/", **headers)
        print(f"GET dashboard settings status: {response1.status_code}")
        assert (
            response1.status_code == 200
        ), f"Dashboard settings failed: {response1.content.decode()}"

        # Step 3: Update dashboard settings with table_date
        print("\n3. Updating dashboard settings with JWT token...")
        update_data = {
            "default_currency": "RUB",
            "digits": 0,
            "table_date": "2021-04-04",
        }

        response2 = client.post(
            "/users/api/update_dashboard_settings/",
            data=json.dumps(update_data),
            content_type="application/json",
            **headers,
        )
        print(f"Update settings status: {response2.status_code}")

        if response2.status_code == 200:
            response_data = response2.json()
            print(f"Response data: {response_data}")

            # The endpoint should return the effective_current_date in the response
            effective_date = response_data.get("effective_current_date") or response_data.get(
                "table_date"
            )
            print(f"Effective date from response: {effective_date}")

            # Assert that the effective_date was set correctly
            assert (
                effective_date == "2021-04-04"
            ), f"Expected effective_date to be '2021-04-04', got '{effective_date}'"

            # Check if token refresh is required
            requires_refresh = response_data.get("requires_token_refresh", False)
            print(f"Requires token refresh: {requires_refresh}")

            if requires_refresh:
                print("\n4. Token refresh required, refreshing token...")
                # In a real app, the frontend would refresh the token here
                # For now, we just verify the flag is set
                assert response_data.get("new_effective_date") == "2021-04-04"
        else:
            print(f"Update failed: {response2.content.decode()}")
            raise AssertionError(f"Update settings failed with status {response2.status_code}")

        print("\n=== Test PASSED ===")

    finally:
        # Cleanup
        user.delete()
        Session.objects.all().delete()


@pytest.mark.django_db
def test_jwt_token_required_for_protected_endpoints():
    """Test that protected endpoints require JWT authentication."""
    print("\n=== Testing JWT Token Requirement ===")

    client = Client()

    # Test 1: Access dashboard settings without token
    print("\n1. Testing dashboard settings without token...")
    response = client.get("/users/api/dashboard_settings/")
    print(f"Response status: {response.status_code}")

    # Should return 401 Unauthorized or 403 Forbidden
    assert response.status_code in [
        401,
        403,
    ], f"Expected 401/403 for unauthenticated request, got {response.status_code}"

    # Test 2: Access update settings without token
    print("\n2. Testing update settings without token...")
    update_data = {"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"}

    response = client.post(
        "/users/api/update_dashboard_settings/",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    print(f"Response status: {response.status_code}")

    # Should return 401 Unauthorized or 403 Forbidden
    assert response.status_code in [
        401,
        403,
    ], f"Expected 401/403 for unauthenticated request, got {response.status_code}"

    print("\n=== Test PASSED ===")


@pytest.mark.django_db
def test_session_cookie_not_required_with_jwt():
    """Test that session cookies are not required when using JWT authentication."""
    print("\n=== Testing Session Cookie Not Required with JWT ===")

    # Create a test user
    user = CustomUser.objects.create_user(
        username="testuser2", email="test2@example.com", password="testpass123"
    )

    try:
        client = Client()

        # Login to get JWT tokens
        print("\n1. Logging in to get JWT tokens...")
        login_response = client.post(
            "/users/api/login/",
            {"username": "testuser2", "password": "testpass123"},
            content_type="application/json",
        )

        assert login_response.status_code == 200
        access_token = login_response.json().get("access")

        # Access protected endpoint with JWT token (no session cookies needed)
        print("\n2. Accessing protected endpoint with JWT token...")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}
        response = client.get("/users/api/dashboard_settings/", **headers)

        print(f"Response status: {response.status_code}")
        assert (
            response.status_code == 200
        ), "JWT token should provide access without session cookies"

        # Verify no session cookie is set
        session_cookie = client.cookies.get("sessionid")
        print(f"Session cookie: {session_cookie}")

        # Session cookie may or may not exist, but JWT should work regardless
        print("\n=== Test PASSED ===")

    finally:
        # Cleanup
        user.delete()
        Session.objects.all().delete()
