"""Test CORS and session cookie behavior between frontend and backend."""

import pytest
import requests


@pytest.mark.skip(
    reason="Requires live server running on localhost:8000. "
    "Run manually with: python -m pytest "
    "tests/integration/api/test_cors_session.py -v -s"
)
def test_cors_session_behavior() -> None:
    """Test session behavior with CORS headers."""
    print("=== Testing CORS Session Behavior ===")

    # Simulate frontend request from localhost:8080
    headers = {
        "Origin": "http://localhost:8080",
        "Content-Type": "application/json",
        "Referer": "http://localhost:8080/",
    }

    base_url = "http://localhost:8000"

    # Test 1: Unauthenticated request (simulating your issue)
    print("\n1. Testing unauthenticated request (your current issue)")
    response1 = requests.post(
        f"{base_url}/users/api/update_dashboard_settings/",
        json={"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"},
        headers=headers,
    )
    print(f"Status: {response1.status_code}")
    print(f"Set-Cookie headers: {response1.headers.get('Set-Cookie', 'None')}")
    print(
        "CORS headers: "
        f"{dict([(k, v) for k, v in response1.headers.items() if k.startswith('Access-Control')])}"  # noqa: E501
    )

    # Extract session cookie if set
    session_cookie = None
    if "Set-Cookie" in response1.headers:
        for cookie in response1.headers["Set-Cookie"].split(","):
            if "sessionid=" in cookie:
                session_cookie = cookie.split(";")[0].strip()
                break

    print(f"Session cookie extracted: {session_cookie}")

    # Test 2: Second request with session cookie
    if session_cookie:
        print("\n2. Testing second request with session cookie")
        headers_with_cookie = headers.copy()
        headers_with_cookie["Cookie"] = session_cookie

        response2 = requests.post(
            f"{base_url}/closed_positions/api/get_closed_positions_table/",
            json={},
            headers=headers_with_cookie,
        )
        print(f"Status: {response2.status_code}")
        print("Should have session now: Yes")
    else:
        print("\n2. No session cookie was set - this is the problem!")

    # Test 3: Test with proper JWT authentication
    print("\n3. Testing with proper JWT authentication")
    # First login to get tokens
    login_response = requests.post(
        f"{base_url}/users/api/login/",
        json={
            "username": "testuser",
            "password": "testpass123",
        },  # Use actual credentials
        headers=headers,
    )

    if login_response.status_code == 200:
        tokens = login_response.json()
        access_token = tokens.get("access")

        print(f"Got access token: {access_token[:20] if access_token else 'None'}...")

        # Test authenticated request
        auth_headers = headers.copy()
        auth_headers["Authorization"] = f"Bearer {access_token}"

        response3 = requests.post(
            f"{base_url}/users/api/update_dashboard_settings/",
            json={"default_currency": "RUB", "digits": 0, "table_date": "2021-04-04"},
            headers=auth_headers,
        )
        print(f"Authenticated request status: {response3.status_code}")
        print(f"Session cookie: {response3.headers.get('Set-Cookie', 'None')}")

        if response3.status_code == 200:
            print("✅ Authenticated request successful!")

            # Test second authenticated request
            response4 = requests.post(
                f"{base_url}/closed_positions/api/get_closed_positions_table/",
                json={},
                headers=auth_headers,
            )
            print(f"Second authenticated request status: {response4.status_code}")

            if response4.status_code == 200:
                print("✅ Session persistence working with proper authentication!")
            else:
                print("❌ Session persistence still broken")
    else:
        print(f"❌ Login failed: {login_response.status_code} - {login_response.text}")


if __name__ == "__main__":
    test_cors_session_behavior()
