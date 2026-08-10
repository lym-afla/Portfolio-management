"""
Load testing configuration for Portfolio Management API endpoints.

This file defines load testing scenarios using Locust to simulate
various user loads on the API.
"""

import json
import random
from datetime import date, timedelta

from locust import HttpUser, between, task


class PortfolioUser(HttpUser):
    """Simulated user interacting with portfolio management API."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def on_start(self):
        """Called when a simulated user starts."""
        # Create a test portfolio for this user
        portfolio_data = {
            "name": f"Load Test Portfolio {random.randint(1000, 9999)}",
            "description": "Portfolio created during load testing",
            "base_currency": "USD",
        }

        response = self.client.post("/api/portfolios/", json=portfolio_data)
        if response.status_code == 201:
            self.portfolio_id = response.json()["id"]
            self.portfolio_name = response.json()["name"]
        else:
            self.portfolio_id = None
            self.portfolio_name = None

    @task(3)
    def list_portfolios(self):
        """List all portfolios."""
        self.client.get("/api/portfolios/")

    @task(5)
    def get_portfolio_details(self):
        """Get details of a specific portfolio."""
        if self.portfolio_id:
            self.client.get(f"/api/portfolios/{self.portfolio_id}/")
        else:
            # Fallback to listing portfolios
            self.client.get("/api/portfolios/")

    @task(2)
    def list_assets(self):
        """List all available assets."""
        self.client.get("/api/assets/")

    @task(4)
    def list_transactions(self):
        """List transactions for a portfolio."""
        if self.portfolio_id:
            self.client.get(f"/api/transactions/?portfolio={self.portfolio_id}")
        else:
            # Fallback to listing all transactions
            self.client.get("/api/transactions/")

    @task(1)
    def get_fx_rates(self):
        """Get current FX rates."""
        self.client.get("/api/fx-rates/")

    @task(1)
    def create_transaction(self):
        """Create a new transaction (lower frequency)."""
        if not self.portfolio_id:
            return

        # First, get an asset
        assets_response = self.client.get("/api/assets/")
        if assets_response.status_code != 200 or not assets_response.json().get(
            "results"
        ):
            return

        assets = assets_response.json()["results"]
        asset = random.choice(assets)

        # Create transaction data
        transaction_data = {
            "portfolio": self.portfolio_id,
            "asset": asset["id"],
            "type": random.choice(["Buy", "Sell"]),
            "quantity": random.randint(10, 1000),
            "price": round(random.uniform(10.0, 500.0), 2),
            "currency": asset.get("currency", "USD"),
            "date": (date.today() - timedelta(days=random.randint(0, 30))).isoformat(),
        }

        self.client.post("/api/transactions/", json=transaction_data)

    @task(1)
    def get_portfolio_performance(self):
        """Get portfolio performance metrics."""
        if self.portfolio_id:
            self.client.get(f"/api/portfolios/{self.portfolio_id}/performance/")

    @task(2)
    def get_portfolio_positions(self):
        """Get portfolio positions."""
        if self.portfolio_id:
            self.client.get(f"/api/portfolios/{self.portfolio_id}/positions/")

    @task(1)
    def get_portfolio_valuation(self):
        """Get portfolio valuation breakdown."""
        if self.portfolio_id:
            self.client.get(f"/api/portfolios/{self.portfolio_id}/valuation/")


class ReadOnlyUser(HttpUser):
    """Read-only user that only performs GET requests."""

    wait_time = between(0.5, 2)  # Faster wait time for read-only operations

    @task(5)
    def list_portfolios(self):
        """List all portfolios."""
        self.client.get("/api/portfolios/")

    @task(3)
    def list_assets(self):
        """List all available assets."""
        self.client.get("/api/assets/")

    @task(4)
    def list_transactions(self):
        """List transactions."""
        self.client.get("/api/transactions/")

    @task(2)
    def get_fx_rates(self):
        """Get current FX rates."""
        self.client.get("/api/fx-rates/")

    @task(1)
    def get_portfolio_details(self):
        """Get details of a random portfolio."""
        response = self.client.get("/api/portfolios/")
        if response.status_code == 200 and response.json().get("results"):
            portfolios = response.json()["results"]
            if portfolios:
                portfolio = random.choice(portfolios)
                self.client.get(f"/api/portfolios/{portfolio['id']}/")


class HeavyUser(HttpUser):
    """Heavy user that performs many operations quickly."""

    wait_time = between(0.1, 1)  # Very fast operations

    def on_start(self):
        """Create multiple portfolios for heavy testing."""
        self.portfolios = []

        for i in range(3):
            portfolio_data = {
                "name": f"Heavy Load Portfolio {random.randint(1000, 9999)}-{i}",
                "description": "Portfolio for heavy load testing",
                "base_currency": random.choice(["USD", "EUR", "GBP"]),
            }

            response = self.client.post("/api/portfolios/", json=portfolio_data)
            if response.status_code == 201:
                self.portfolios.append(response.json()["id"])

    @task(8)
    def rapid_portfolio_access(self):
        """Rapidly access portfolio data."""
        if self.portfolios:
            portfolio_id = random.choice(self.portfolios)

            # Multiple rapid requests for the same portfolio
            self.client.get(f"/api/portfolios/{portfolio_id}/")
            self.client.get(f"/api/portfolios/{portfolio_id}/positions/")
            self.client.get(f"/api/portfolios/{portfolio_id}/performance/")

    @task(3)
    def rapid_transaction_lists(self):
        """Rapidly list transactions."""
        if self.portfolios:
            portfolio_id = random.choice(self.portfolios)
            self.client.get(f"/api/transactions/?portfolio={portfolio_id}")

    @task(2)
    def create_rapid_transactions(self):
        """Create transactions rapidly."""
        if not self.portfolios:
            return

        # Get an asset
        assets_response = self.client.get("/api/assets/")
        if assets_response.status_code != 200:
            return

        assets = assets_response.json().get("results", [])
        if not assets:
            return

        asset = random.choice(assets)
        portfolio_id = random.choice(self.portfolios)

        transaction_data = {
            "portfolio": portfolio_id,
            "asset": asset["id"],
            "type": random.choice(["Buy", "Sell"]),
            "quantity": random.randint(10, 500),
            "price": round(random.uniform(10.0, 200.0), 2),
            "currency": asset.get("currency", "USD"),
            "date": date.today().isoformat(),
        }

        self.client.post("/api/transactions/", json=transaction_data)


# Performance test configuration
class PerformanceTestUser(HttpUser):
    """User specifically for performance benchmarking."""

    wait_time = between(0.05, 0.5)  # Very minimal wait time

    tasks = {
        # High-frequency operations
        "list_portfolios": 10,
        "get_portfolio_details": 15,
        "list_assets": 8,
        "list_transactions": 12,
        "get_portfolio_positions": 6,
        "get_portfolio_performance": 4,
        "create_transaction": 2,
        "get_fx_rates": 3,
    }

    def list_portfolios(self):
        """Benchmark portfolio listing."""
        self.client.get("/api/portfolios/")

    def get_portfolio_details(self):
        """Benchmark portfolio detail retrieval."""
        # Try to get the first portfolio
        response = self.client.get("/api/portfolios/?limit=1")
        if response.status_code == 200 and response.json().get("results"):
            portfolio_id = response.json()["results"][0]["id"]
            self.client.get(f"/api/portfolios/{portfolio_id}/")

    def list_assets(self):
        """Benchmark asset listing."""
        self.client.get("/api/assets/")

    def list_transactions(self):
        """Benchmark transaction listing."""
        self.client.get("/api/transactions/")

    def get_portfolio_positions(self):
        """Benchmark position retrieval."""
        response = self.client.get("/api/portfolios/?limit=1")
        if response.status_code == 200 and response.json().get("results"):
            portfolio_id = response.json()["results"][0]["id"]
            self.client.get(f"/api/portfolios/{portfolio_id}/positions/")

    def get_portfolio_performance(self):
        """Benchmark performance calculation."""
        response = self.client.get("/api/portfolios/?limit=1")
        if response.status_code == 200 and response.json().get("results"):
            portfolio_id = response.json()["results"][0]["id"]
            self.client.get(f"/api/portfolios/{portfolio_id}/performance/")

    def create_transaction(self):
        """Benchmark transaction creation."""
        # Get an asset and portfolio
        portfolio_response = self.client.get("/api/portfolios/?limit=1")
        asset_response = self.client.get("/api/assets/?limit=1")

        if (
            portfolio_response.status_code == 200
            and asset_response.status_code == 200
            and portfolio_response.json().get("results")
            and asset_response.json().get("results")
        ):
            portfolio_id = portfolio_response.json()["results"][0]["id"]
            asset = asset_response.json()["results"][0]

            transaction_data = {
                "portfolio": portfolio_id,
                "asset": asset["id"],
                "type": "Buy",
                "quantity": 100,
                "price": 50.00,
                "currency": asset.get("currency", "USD"),
                "date": date.today().isoformat(),
            }

            self.client.post("/api/transactions/", json=transaction_data)

    def get_fx_rates(self):
        """Benchmark FX rate retrieval."""
        self.client.get("/api/fx-rates/")
