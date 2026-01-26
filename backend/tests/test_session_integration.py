"""Integration tests to debug session persistence issues.

Tests session behavior across multiple requests.
"""

import json
import os
import sys

import django
from django.contrib.sessions.models import Session
from django.test import Client

from users.models import CustomUser

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings")

django.setup()


def test_session_persistence():
    """Test session persistence across multiple requests."""
    print("=== Testing Session Persistence ===")

    # Create a test client (simulates browser)
    client = Client()

    # Create a test user
    user = CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )

    # Login the user
    print("\n1. Testing login...")
    client.login(username="testuser", password="testpass123")

    # Check initial session state
    print(f"Initial session data: {dict(client.session.items())}")
    print(f"Session cookie: {client.cookies.get('sessionid', 'NOT_FOUND')}")

    # Test 1: Call dashboard settings endpoint
    print("\n2. Testing dashboard settings endpoint...")
    response1 = client.get("/users/api/dashboard_settings/")
    print(f"Response status: {response1.status_code}")
    print(f"Session data after dashboard settings: {dict(client.session.items())}")
    print(
        f"Session cookie after dashboard settings: {client.cookies.get('sessionid', 'NOT_FOUND')}"
    )

    # Test 2: Call update dashboard settings
    print("\n3. Testing update dashboard settings...")
    update_data = {"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"}
    response2 = client.post(
        "/users/api/update_dashboard_settings/",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    print(f"Response status: {response2.status_code}")
    print(f"Response data: {response2.json() if response2.status_code == 200 else 'Error'}")
    print(f"Session data after update: {dict(client.session.items())}")
    print(f"Session cookie after update: {client.cookies.get('sessionid', 'NOT_FOUND')}")

    # Test 3: Call transactions endpoint to check if session persists
    print("\n4. Testing transactions endpoint...")
    response3 = client.post("/transactions/api/get_transactions_table/")
    print(f"Response status: {response3.status_code}")
    print(f"Session data after transactions: {dict(client.session.items())}")
    print(f"Session cookie after transactions: {client.cookies.get('sessionid', 'NOT_FOUND')}")

    # Test 4: Check if effective_current_date persists
    effective_date = client.session.get("effective_current_date")
    print(f"\n5. Final effective_date in session: {effective_date}")
    print("Expected: 2021-04-04")
    print(f"Test {'PASSED' if effective_date == '2021-04-04' else 'FAILED'}")

    # Test database sessions
    print("\n6. Checking database sessions...")
    sessions = Session.objects.all()
    print(f"Total sessions in database: {sessions.count()}")
    for session in sessions:
        session_data = session.get_decoded()
        print(f"Session {session.session_key[:8]}...: {session_data}")

    # Test with new client to simulate new browser session
    print("\n7. Testing with new client (simulates new browser session)...")
    new_client = Client()
    new_client.login(username="testuser", password="testpass123")

    new_client.get("/users/api/dashboard_settings/")
    print(f"New client session data: {dict(new_client.session.items())}")
    print(
        "New client effective_date: "
        f"{new_client.session.get('effective_current_date', 'NOT_FOUND')}"
    )

    # Cleanup
    user.delete()
    Session.objects.all().delete()

    return effective_date == "2021-04-04"


def test_session_cookies_directly():
    """Test session cookie behavior directly."""
    print("\n=== Testing Session Cookies Directly ===")

    client = Client()

    # Test 1: Initial request
    print("\n1. Testing initial request...")
    client.get("/users/api/dashboard_settings/")

    # Check response cookies
    print(f"Response cookies: {dict(client.cookies)}")
    session_cookie = client.cookies.get("sessionid")
    print(f"Session cookie value: {session_cookie}")

    # Test 2: Second request with same client
    print("\n2. Testing second request with same client...")
    client.get("/users/api/dashboard_settings/")
    print(f"Session cookie on second request: {client.cookies.get('sessionid')}")

    return session_cookie is not None


if __name__ == "__main__":
    print("Starting session persistence tests...")

    # Test 1: Basic session persistence
    test1_passed = test_session_persistence()

    # Test 2: Cookie behavior
    test2_passed = test_session_cookies_directly()

    print("\n=== RESULTS ===")
    print(f"Session persistence test: {'PASSED' if test1_passed else 'FAILED'}")
    print(f"Cookie behavior test: {'PASSED' if test2_passed else 'FAILED'}")

    if not test1_passed or not test2_passed:
        print("\nSession issues detected. Analyzing...")

        # Check Django settings
        from django.conf import settings

        print(f"Session engine: {settings.SESSION_ENGINE}")
        print(f"Session cookie secure: {settings.SESSION_COOKIE_SECURE}")
        print(f"Session cookie samesite: {settings.SESSION_COOKIE_SAMESITE}")
        print(f"Session save every request: {settings.SESSION_SAVE_EVERY_REQUEST}")

        # Check CORS settings
        print(f"CORS allow credentials: {getattr(settings, 'CORS_ALLOW_CREDENTIALS', 'NOT_SET')}")
        print(f"CORS allowed origins: {getattr(settings, 'CORS_ALLOWED_ORIGINS', 'NOT_SET')}")
    else:
        print("\nAll tests passed! Session persistence is working correctly.")
