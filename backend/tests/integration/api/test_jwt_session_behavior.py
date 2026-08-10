"""Test session behavior with JWT authentication like the frontend uses."""

import json
import os
import sys

import django
import pytest
from django.test import Client

from users.models import CustomUser

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings")

django.setup()


@pytest.mark.django_db
def test_jwt_authenticated_session():
    """Test session behavior when using JWT authentication like frontend."""
    print("=== Testing JWT Authenticated Session Behavior ===")

    # Create or get a test user
    user, created = CustomUser.objects.get_or_create(
        username="jwtuser",
        defaults={
            "email": "jwt@example.com",
        },
    )
    if created:
        user.set_password("testpass123")
        user.save()

    # Create a test client
    client = Client()

    # Step 1: Login to get JWT tokens (simulate frontend login)
    print("\n1. Logging in to get JWT tokens...")
    login_response = client.post(
        "/users/api/login/", {"username": "jwtuser", "password": "testpass123"}
    )

    print(f"Login response status: {login_response.status_code}")
    if login_response.status_code == 200:
        login_data = login_response.json()
        access_token = login_data.get("access")
        refresh_token = login_data.get("refresh")
        print(f"Got access token: {access_token[:20] if access_token else 'None'}...")
        print(
            f"Got refresh token: {refresh_token[:20] if refresh_token else 'None'}..."
        )
    else:
        print(f"Login failed: {login_response.content.decode()}")
        return

    # Step 2: Use JWT token to call dashboard settings endpoint
    print("\n2. Testing dashboard settings with JWT token...")
    headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

    response = client.get("/users/api/dashboard_settings/", **headers)
    print(f"GET dashboard settings status: {response.status_code}")
    print(f"Session data after GET: {dict(client.session.items())}")

    # Step 3: Update dashboard settings with JWT token
    print("\n3. Updating dashboard settings with JWT token...")
    update_data = {"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"}

    response = client.post(
        "/users/api/update_dashboard_settings/",
        data=json.dumps(update_data),
        content_type="application/json",
        **headers,
    )
    print(f"Update settings status: {response.status_code}")
    print(
        "Response data: "
        f"{response.json() if response.status_code == 200 else response.content.decode()[:200]}"  # noqa: E501
    )
    print(f"Session data after update: {dict(client.session.items())}")

    # Step 4: Call transactions endpoint with JWT token
    print("\n4. Testing transactions endpoint with JWT token...")
    response = client.post("/transactions/api/get_transactions_table/", **headers)
    print(f"Transactions endpoint status: {response.status_code}")
    print(f"Session data after transactions: {dict(client.session.items())}")

    # Step 5: Check if effective_current_date persisted
    effective_date = client.session.get("effective_current_date")
    print(f"\n5. Final effective_date in session: {effective_date}")
    print("Expected: 2021-04-04")
    print(f"Test {'PASSED' if effective_date == '2021-04-04' else 'FAILED'}")


@pytest.mark.django_db
def test_unauthenticated_session_behavior():
    """Test session behavior with unauthenticated requests (original problem)."""
    print("\n=== Testing Unauthenticated Session Behavior ===")

    # Create a test client without login
    client = Client()

    # Step 1: Call dashboard settings without authentication
    print("\n1. Testing dashboard settings without authentication...")
    response = client.get("/users/api/dashboard_settings/")
    print(f"Response status: {response.status_code}")
    print(f"Session data: {dict(client.session.items())}")

    # Step 2: Call update settings without authentication
    print("\n2. Testing update settings without authentication...")
    update_data = {"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"}

    response = client.post(
        "/users/api/update_dashboard_settings/",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    print(f"Response status: {response.status_code}")
    print(f"Session data after update attempt: {dict(client.session.items())}")

    # Step 3: Call transactions without authentication
    print("\n3. Testing transactions without authentication...")
    response = client.post("/transactions/api/get_transactions_table/")
    print(f"Response status: {response.status_code}")
    print(f"Session data after transactions: {dict(client.session.items())}")


if __name__ == "__main__":
    print("Testing session behavior with different authentication scenarios...")

    test_unauthenticated_session_behavior()
    test_jwt_authenticated_session()
