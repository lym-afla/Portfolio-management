"""Test API endpoints directly to understand why they're returning 400 errors."""

import json

import pytest
from django.test import Client
from rest_framework.test import APITestCase

from users.models import CustomUser


@pytest.mark.api
@pytest.mark.integration
class TestAPIEndpoints(APITestCase):
    """Test API endpoints for the portfolio management system."""

    def setUp(self):
        """Set up test data for API endpoints."""
        self.user = CustomUser.objects.create_user(
            username="testuser_api",
            email="test_api@example.com",
            password="testpass123",
        )
        self.client = Client()
        self.client.login(username="testuser_api", password="testpass123")

    def test_dashboard_settings_endpoint_get(self):
        """Test the dashboard settings GET endpoint."""
        print("=== Testing Dashboard Settings GET Endpoint ===")

        # Test GET request to dashboard settings
        print("1. Testing GET /users/api/dashboard_settings/")
        response = self.client.get("/users/api/dashboard_settings/")
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.content.decode()[:500]}...")

        if response.status_code != 200:
            print(f"Headers: {dict(response.headers)}")
            if hasattr(response, "context"):
                print(f"Context errors: {response.context}")

        # Check session after requests
        print(f"2. Session data after requests: {dict(self.client.session.items())}")
        print(f"Session ID: {self.client.session.session_key}")

    def test_dashboard_settings_endpoint_post(self):
        """Test the dashboard settings POST endpoint."""
        print("\n=== Testing Dashboard Settings POST Endpoint ===")

        # Test POST request to update dashboard settings
        print("1. Testing POST /users/api/update_dashboard_settings/")
        update_data = {
            "default_currency": "RUB",
            "digits": 0,
            "table_date": "2021-04-04",
        }

        # Try without JSON content type first
        response = self.client.post(
            "/users/api/update_dashboard_settings/", data=update_data
        )
        print(f"Response status (form data): {response.status_code}")
        print(f"Response content: {response.content.decode()[:500]}...")

        # Try with JSON content type
        response = self.client.post(
            "/users/api/update_dashboard_settings/",
            data=json.dumps(update_data),
            content_type="application/json",
        )
        print(f"Response status (JSON): {response.status_code}")
        print(f"Response content: {response.content.decode()[:500]}...")

        # Check session after requests
        print(f"2. Session data after requests: {dict(self.client.session.items())}")
        print(f"Session ID: {self.client.session.session_key}")

    def test_transactions_endpoint(self):
        """Test the transactions endpoint directly."""
        print("\n=== Testing Transactions Endpoint ===")

        # Set effective_current_date in session
        self.client.session["effective_current_date"] = "2021-04-04"
        self.client.session.save()

        # Test POST request to transactions table
        print("1. Testing POST /transactions/api/get_transactions_table/")
        response = self.client.post("/transactions/api/get_transactions_table/")
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.content.decode()[:500]}...")

        # Check session after request
        print(f"2. Session data after request: {dict(self.client.session.items())}")
        print(f"Session ID: {self.client.session.session_key}")


# Keep the standalone functions for debugging purposes
@pytest.mark.django_db
@pytest.mark.api
@pytest.mark.integration
def test_dashboard_settings_endpoint():
    """Test the dashboard settings endpoint directly."""
    print("=== Testing Dashboard Settings Endpoint ===")

    # Create or get a test user
    user, created = CustomUser.objects.get_or_create(
        username="testuser2",
        defaults={
            "email": "test2@example.com",
        },
    )
    if created:
        user.set_password("testpass123")
        user.save()

    # Create a test client
    client = Client()

    # Login the user
    client.login(username="testuser2", password="testpass123")

    # Test GET request to dashboard settings
    print("\n1. Testing GET /users/api/dashboard_settings/")
    response = client.get("/users/api/dashboard_settings/")
    print(f"Response status: {response.status_code}")
    print(f"Response content: {response.content.decode()[:500]}...")

    if response.status_code != 200:
        print(f"Headers: {dict(response.headers)}")
        if hasattr(response, "context"):
            print(f"Context errors: {response.context}")

    # Test POST request to update dashboard settings
    print("\n2. Testing POST /users/api/update_dashboard_settings/")
    update_data = {"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"}

    # Try without JSON content type first
    response = client.post("/users/api/update_dashboard_settings/", data=update_data)
    print(f"Response status (form data): {response.status_code}")
    print(f"Response content: {response.content.decode()[:500]}...")

    # Try with JSON content type
    response = client.post(
        "/users/api/update_dashboard_settings/",
        data=json.dumps(update_data),
        content_type="application/json",
    )
    print(f"Response status (JSON): {response.status_code}")
    print(f"Response content: {response.content.decode()[:500]}...")

    # Check session after requests
    print(f"\n3. Session data after requests: {dict(client.session.items())}")
    print(f"Session ID: {client.session.session_key}")

    # Cleanup (commented out for debugging)
    # user.delete()


@pytest.mark.django_db
@pytest.mark.api
@pytest.mark.integration
def test_transactions_endpoint():
    """Test the transactions endpoint directly."""
    print("\n=== Testing Transactions Endpoint ===")

    # Create or get a test user
    user, created = CustomUser.objects.get_or_create(
        username="testuser3",
        defaults={
            "email": "test3@example.com",
        },
    )
    if created:
        user.set_password("testpass123")
        user.save()

    # Create a test client
    client = Client()

    # Login the user
    client.login(username="testuser3", password="testpass123")

    # Set effective_current_date in session
    client.session["effective_current_date"] = "2021-04-04"
    client.session.save()

    # Test POST request to transactions table
    print("\n1. Testing POST /transactions/api/get_transactions_table/")
    response = client.post("/transactions/api/get_transactions_table/")
    print(f"Response status: {response.status_code}")
    print(f"Response content: {response.content.decode()[:500]}...")

    # Check session after request
    print(f"\n2. Session data after request: {dict(client.session.items())}")
    print(f"Session ID: {client.session.session_key}")

    # Cleanup (commented out for debugging)
    # user.delete()


if __name__ == "__main__":
    print("Starting API endpoint tests...")

    test_dashboard_settings_endpoint()
    test_transactions_endpoint()
