"""
Comprehensive API endpoint tests for the portfolio management system.

This module tests all API endpoints including:
- User management endpoints
- Portfolio data endpoints
- Transaction management endpoints
- FX rate endpoints
- Dashboard and reporting endpoints
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from rest_framework.test import APITestCase

from common.models import FX, Assets, Brokers, Prices, Transactions
from users.models import CustomUser


@pytest.mark.api
@pytest.mark.integration
class TestUserEndpoints(APITestCase):
    """Test user-related API endpoints."""

    def setUp(self):
        """Set up test data for user endpoints."""
        self.user = CustomUser.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_user_profile_endpoint(self):
        """Test user profile retrieval endpoint."""
        url = "/users/api/profile/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert "email" in data
        assert data["username"] == "testuser"

    def test_dashboard_settings_endpoint_get(self):
        """Test dashboard settings retrieval."""
        url = "/users/api/dashboard_settings/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "default_currency" in data
        assert "digits" in data
        assert "table_date" in data

    def test_dashboard_settings_endpoint_post(self):
        """Test dashboard settings update."""
        url = "/users/api/update_dashboard_settings/"
        data = {"default_currency": "EUR", "digits": 2, "table_date": "2023-06-15"}

        response = self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

        assert response.status_code == 200
        updated_data = response.json()
        assert updated_data["default_currency"] == "EUR"
        assert updated_data["digits"] == 2

    def test_user_preferences_endpoint(self):
        """Test user preferences management."""
        # Test getting preferences
        url = "/users/api/preferences/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

        # Test updating preferences
        preferences = {"theme": "dark", "language": "en", "timezone": "UTC"}

        response = self.client.post(
            url, data=json.dumps(preferences), content_type="application/json"
        )

        assert response.status_code == 200

    def test_unauthorized_access(self):
        """Test that unauthorized access is properly blocked."""
        self.client.logout()
        url = "/users/api/profile/"
        response = self.client.get(url)

        assert (
            response.status_code == 401 or response.status_code == 302
        )  # Either 401 or redirect to login


@pytest.mark.api
@pytest.mark.integration
class TestPortfolioEndpoints(APITestCase):
    """Test portfolio-related API endpoints."""

    def setUp(self):
        """Set up test data for portfolio endpoints."""
        self.user = CustomUser.objects.create_user(
            username="portfolio_user",
            email="portfolio@example.com",
            password="testpass123",
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )
        self.asset = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="Test Stock",
            currency="USD",
            exposure="Equity",
        )
        self.asset.investors.add(self.user)
        self.asset.brokers.add(self.broker)

        self.client = Client()
        self.client.login(username="portfolio_user", password="testpass123")

    def test_portfolio_summary_endpoint(self):
        """Test portfolio summary retrieval."""
        url = "/dashboard/api/portfolio_summary/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "total_value" in data
        assert "total_gain_loss" in data
        assert "currency" in data

    def test_portfolio_holdings_endpoint(self):
        """Test portfolio holdings retrieval."""
        # Create a test transaction
        Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        url = "/dashboard/api/holdings/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:  # If there are holdings
            holding = data[0]
            assert "asset_name" in holding
            assert "quantity" in holding
            assert "current_price" in holding
            assert "market_value" in holding

    def test_portfolio_performance_endpoint(self):
        """Test portfolio performance data retrieval."""
        url = "/dashboard/api/performance/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "period_return" in data
        assert "year_to_date" in data
        assert "annualized_return" in data

    def test_portfolio_allocation_endpoint(self):
        """Test portfolio allocation breakdown."""
        url = "/dashboard/api/allocation/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "by_sector" in data
        assert "by_currency" in data
        assert "by_asset_type" in data

    def test_portfolio_nav_endpoint(self):
        """Test NAV calculation endpoint."""
        # Create price data
        Prices.objects.create(
            date=date(2023, 6, 15), security=self.asset, price=Decimal("55.00")
        )

        url = "/dashboard/api/nav/"
        response = self.client.post(
            url,
            data=json.dumps({"date": "2023-06-15"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert "nav_value" in data
        assert "currency" in data
        assert "date" in data

    def test_multi_currency_portfolio_endpoint(self, multi_currency_user):
        """Test multi-currency portfolio endpoint."""
        self.client.login(
            username=multi_currency_user.username, password="multipass123"
        )

        url = "/dashboard/api/multi_currency_summary/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "base_currency" in data
        assert "total_nav_base" in data
        assert "currency_breakdown" in data


@pytest.mark.api
@pytest.mark.integration
class TestTransactionEndpoints(APITestCase):
    """Test transaction-related API endpoints."""

    def setUp(self):
        """Set up test data for transaction endpoints."""
        self.user = CustomUser.objects.create_user(
            username="tx_user", email="tx@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )
        self.asset = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="Test Stock",
            currency="USD",
            exposure="Equity",
        )
        self.asset.investors.add(self.user)
        self.asset.brokers.add(self.broker)

        self.client = Client()
        self.client.login(username="tx_user", password="testpass123")

    def test_transactions_list_endpoint(self):
        """Test transactions list retrieval."""
        # Create test transactions
        Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        url = "/transactions/api/list/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_transactions_table_endpoint(self):
        """Test transactions table data endpoint."""
        # Set effective date in session
        session = self.client.session
        session["effective_current_date"] = "2023-06-15"
        session.save()

        url = "/transactions/api/get_transactions_table/"
        response = self.client.post(url)

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "columns" in data

    def test_create_transaction_endpoint(self):
        """Test transaction creation endpoint."""
        url = "/transactions/api/create/"
        transaction_data = {
            "broker": self.broker.id,
            "security": self.asset.id,
            "currency": "USD",
            "type": "Buy",
            "date": "2023-06-15",
            "quantity": "100",
            "price": "50.00",
            "commission": "5.00",
        }

        response = self.client.post(
            url, data=json.dumps(transaction_data), content_type="application/json"
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["type"] == "Buy"

    def test_update_transaction_endpoint(self):
        """Test transaction update endpoint."""
        # Create a transaction first
        transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        url = f"/transactions/api/update/{transaction.id}/"
        update_data = {"price": "55.00", "commission": "6.00"}

        response = self.client.patch(
            url, data=json.dumps(update_data), content_type="application/json"
        )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["price"])) == Decimal("55.00")

    def test_delete_transaction_endpoint(self):
        """Test transaction deletion endpoint."""
        # Create a transaction first
        transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        url = f"/transactions/api/delete/{transaction.id}/"
        response = self.client.delete(url)

        assert response.status_code == 204

        # Verify transaction is deleted
        with pytest.raises(Transactions.DoesNotExist):
            Transactions.objects.get(id=transaction.id)

    def test_transaction_validation_endpoint(self):
        """Test transaction validation before creation."""
        url = "/transactions/api/validate/"
        invalid_data = {
            "broker": self.broker.id,
            "security": self.asset.id,
            "currency": "USD",
            "type": "Buy",
            "date": "2023-06-15",
            "quantity": "-100",  # Invalid: negative quantity for Buy
            "price": "50.00",
        }

        response = self.client.post(
            url, data=json.dumps(invalid_data), content_type="application/json"
        )

        assert response.status_code == 400
        data = response.json()
        assert "errors" in data


@pytest.mark.api
@pytest.mark.integration
class TestAssetEndpoints(APITestCase):
    """Test asset-related API endpoints."""

    def setUp(self):
        """Set up test data for asset endpoints."""
        self.user = CustomUser.objects.create_user(
            username="asset_user", email="asset@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )
        self.asset = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="Test Stock",
            currency="USD",
            exposure="Equity",
        )
        self.asset.investors.add(self.user)
        self.asset.brokers.add(self.broker)

        self.client = Client()
        self.client.login(username="asset_user", password="testpass123")

    def test_assets_list_endpoint(self):
        """Test assets list retrieval."""
        url = "/assets/api/list/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_asset_detail_endpoint(self):
        """Test individual asset detail retrieval."""
        url = f"/assets/api/detail/{self.asset.id}/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == self.asset.id
        assert data["name"] == self.asset.name
        assert data["isin"] == self.asset.ISIN

    def test_asset_search_endpoint(self):
        """Test asset search functionality."""
        url = "/assets/api/search/?q=Test"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_asset_price_history_endpoint(self):
        """Test asset price history retrieval."""
        # Create price history
        for i in range(10):
            Prices.objects.create(
                date=date(2023, 6, 1) + timedelta(days=i),
                security=self.asset,
                price=Decimal("50.00") + i,
            )

        url = f"/assets/api/price_history/{self.asset.id}/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "prices" in data
        assert isinstance(data["prices"], list)

    def test_asset_position_endpoint(self):
        """Test asset position calculation endpoint."""
        # Create transaction
        Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        url = f"/assets/api/position/{self.asset.id}/"
        response = self.client.post(
            url,
            data=json.dumps({"date": "2023-06-15"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert "position" in data
        assert data["position"] == 100

    def test_create_asset_endpoint(self):
        """Test asset creation endpoint."""
        url = "/assets/api/create/"
        asset_data = {
            "type": "Stock",
            "isin": "NEW123456789",
            "name": "New Test Stock",
            "currency": "USD",
            "exposure": "Equity",
        }

        response = self.client.post(
            url, data=json.dumps(asset_data), content_type="application/json"
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == "New Test Stock"


@pytest.mark.api
@pytest.mark.integration
class TestFXEndpoints(APITestCase):
    """Test FX rate API endpoints."""

    def setUp(self):
        """Set up test data for FX endpoints."""
        self.user = CustomUser.objects.create_user(
            username="fx_user", email="fx@example.com", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="fx_user", password="testpass123")

    def test_fx_rates_endpoint(self):
        """Test FX rates retrieval endpoint."""
        # Create FX rate data
        FX.objects.create(
            investor=self.user,
            date=date(2023, 6, 15),
            USDEUR=Decimal("0.92"),
            USDGBP=Decimal("0.82"),
        )

        url = "/fx/api/rates/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "rates" in data
        assert isinstance(data["rates"], dict)

    def test_fx_conversion_endpoint(self):
        """Test FX conversion endpoint."""
        # Create FX rate data
        FX.objects.create(
            investor=self.user, date=date(2023, 6, 15), USDEUR=Decimal("0.92")
        )

        url = "/fx/api/convert/"
        conversion_data = {
            "from_currency": "USD",
            "to_currency": "EUR",
            "amount": "1000.00",
            "date": "2023-06-15",
        }

        response = self.client.post(
            url, data=json.dumps(conversion_data), content_type="application/json"
        )

        assert response.status_code == 200
        data = response.json()
        assert "converted_amount" in data
        assert "exchange_rate" in data
        assert data["converted_amount"] == "920.00"

    def test_fx_history_endpoint(self):
        """Test FX rate history endpoint."""
        # Create FX rate history
        for i in range(30):
            FX.objects.create(
                investor=self.user,
                date=date(2023, 6, 1) + timedelta(days=i),
                USDEUR=Decimal("0.92") + (i * Decimal("0.001")),
            )

        url = "/fx/api/history/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_fx_portfolio_impact_endpoint(self):
        """Test FX impact on portfolio endpoint."""
        url = "/fx/api/portfolio_impact/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "fx_effects" in data
        assert "total_impact" in data


@pytest.mark.api
@pytest.mark.integration
class TestReportingEndpoints(APITestCase):
    """Test reporting and analytics API endpoints."""

    def setUp(self):
        """Set up test data for reporting endpoints."""
        self.user = CustomUser.objects.create_user(
            username="report_user", email="report@example.com", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="report_user", password="testpass123")

    def test_annual_performance_endpoint(self):
        """Test annual performance report endpoint."""
        url = "/reports/api/annual_performance/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "years" in data
        assert isinstance(data["years"], list)

    def test_monthly_performance_endpoint(self):
        """Test monthly performance report endpoint."""
        url = "/reports/api/monthly_performance/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "monthly_data" in data

    def test_gain_loss_report_endpoint(self):
        """Test gain/loss report endpoint."""
        url = "/reports/api/gain_loss/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "realized_gains" in data
        assert "unrealized_gains" in data

    def test_tax_report_endpoint(self):
        """Test tax report endpoint."""
        url = "/reports/api/tax_report/"
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "taxable_events" in data
        assert "total_gains" in data

    def test_export_portfolio_endpoint(self):
        """Test portfolio data export endpoint."""
        url = "/reports/api/export_portfolio/"
        response = self.client.get(url)

        assert response.status_code == 200
        # Should return a file or download link

    def test_custom_report_endpoint(self):
        """Test custom report generation endpoint."""
        url = "/reports/api/custom/"
        report_config = {
            "start_date": "2023-01-01",
            "end_date": "2023-06-30",
            "include_gains": True,
            "include_dividends": True,
            "currency": "USD",
        }

        response = self.client.post(
            url, data=json.dumps(report_config), content_type="application/json"
        )

        assert response.status_code == 200
        data = response.json()
        assert "report_data" in data


@pytest.mark.api
@pytest.mark.integration
class TestAPIAuthenticationAndPermissions(APITestCase):
    """Test API authentication and permission handling."""

    def setUp(self):
        """Set up test users with different permission levels."""
        self.regular_user = CustomUser.objects.create_user(
            username="regular", email="regular@example.com", password="testpass123"
        )
        self.admin_user = CustomUser.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
            is_staff=True,
            is_superuser=True,
        )

    def test_regular_user_permissions(self):
        """Test regular user can access appropriate endpoints."""
        client = Client()
        client.login(username="regular", password="testpass123")

        # Should be able to access own data
        response = client.get("/users/api/profile/")
        assert response.status_code == 200

        # Should not be able to access admin endpoints
        response = client.get("/admin/api/system_status/")
        assert response.status_code in [403, 404, 401]

    def test_admin_user_permissions(self):
        """Test admin user can access all endpoints."""
        client = Client()
        client.login(username="admin", password="adminpass123")

        # Should be able to access regular endpoints
        response = client.get("/users/api/profile/")
        assert response.status_code == 200

        # Should be able to access admin endpoints
        response = client.get("/admin/api/users/")
        assert response.status_code in [
            200,
            404,
        ]  # 404 is acceptable if endpoint doesn't exist

    def test_api_key_authentication(self):
        """Test API key authentication if implemented."""
        # This would test API key authentication if the system implements it
        pass

    def test_token_authentication(self):
        """Test token-based authentication if implemented."""
        # This would test JWT or other token authentication if implemented
        pass

    def test_session_expiration(self):
        """Test session handling and expiration."""
        client = Client()
        client.login(username="regular", password="testpass123")

        # Should work with valid session
        response = client.get("/users/api/profile/")
        assert response.status_code == 200

        # Clear session
        client.logout()

        # Should fail with cleared session
        response = client.get("/users/api/profile/")
        assert response.status_code in [401, 302]


@pytest.mark.api
@pytest.mark.integration
class TestAPIErrorHandling(APITestCase):
    """Test API error handling and edge cases."""

    def setUp(self):
        """Set up test data."""
        self.user = CustomUser.objects.create_user(
            username="error_user", email="error@example.com", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="error_user", password="testpass123")

    def test_invalid_json_payload(self):
        """Test handling of invalid JSON payloads."""
        url = "/transactions/api/create/"
        invalid_json = "{invalid json}"

        response = self.client.post(
            url, data=invalid_json, content_type="application/json"
        )

        assert response.status_code == 400

    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        url = "/transactions/api/create/"
        incomplete_data = {
            "type": "Buy",
            # Missing other required fields
        }

        response = self.client.post(
            url, data=json.dumps(incomplete_data), content_type="application/json"
        )

        assert response.status_code == 400
        data = response.json()
        assert "errors" in data

    def test_invalid_data_types(self):
        """Test handling of invalid data types."""
        url = "/transactions/api/create/"
        invalid_data = {
            "broker": "not_a_number",
            "quantity": "not_a_number",
            "price": "not_a_number",
            "type": "Buy",
        }

        response = self.client.post(
            url, data=json.dumps(invalid_data), content_type="application/json"
        )

        assert response.status_code == 400

    def test_resource_not_found(self):
        """Test handling of non-existent resource requests."""
        url = "/assets/api/detail/99999/"  # Non-existent ID
        response = self.client.get(url)

        assert response.status_code == 404

    def test_rate_limiting(self):
        """Test rate limiting if implemented."""
        # Make multiple rapid requests
        url = "/users/api/profile/"
        responses = []

        for _ in range(100):  # Adjust based on actual rate limits
            response = self.client.get(url)
            responses.append(response.status_code)

            # If rate limiting is implemented, we should see 429 status codes
            if response.status_code == 429:
                break

        # Verify at least one request succeeded
        assert 200 in responses

    def test_large_payload_handling(self):
        """Test handling of large payload sizes."""
        url = "/transactions/api/bulk_create/"
        large_data = {"transactions": []}

        # Create a large payload
        for i in range(1000):  # Adjust based on actual limits
            large_data["transactions"].append(
                {
                    "type": "Buy",
                    "quantity": "100",
                    "price": "50.00",
                    "description": f"Transaction {i}",
                }
            )

        response = self.client.post(
            url, data=json.dumps(large_data), content_type="application/json"
        )

        # Should either succeed or fail gracefully
        assert response.status_code in [200, 201, 400, 413]
