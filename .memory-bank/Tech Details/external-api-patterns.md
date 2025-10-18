# External API Integration Patterns

## Overview

This document captures the architectural patterns and best practices for integrating with external APIs in the portfolio management system. It covers error handling, rate limiting, data transformation, and resilience patterns based on real-world implementation experience.

---

## General Integration Principles

### API Client Architecture

#### Separation of Concerns
```python
# API-specific utilities (core/tinkoff_utils.py, core/yahoo_utils.py)
# - Handle API authentication and request formatting
# - Transform API responses to internal data structures
# - Manage API-specific quirks and limitations

# Import orchestrators (core/import_utils.py)
# - Coordinate multiple API calls
# - Handle business logic for data import
# - Manage transaction creation and validation

# Model layer (common/models.py)
# - Contain domain-specific API methods
# - Provide clean interfaces for API data
# - Handle database persistence
```

#### Error Handling Strategy
```python
# Layered error handling
try:
    # API call
    result = api_call()
except SpecificAPIError as e:
    # Handle known API errors
    logger.warning(f"API specific error: {e}")
    return handle_api_error(e)
except requests.RequestException as e:
    # Handle network/connection errors
    logger.error(f"Network error: {e}")
    return handle_network_error(e)
except Exception as e:
    # Handle unexpected errors
    logger.error(f"Unexpected error: {e}")
    raise
```

---

## T-Bank API Integration

### Authentication & Session Management

#### Modern Architecture (v0.2.30+)
```python
# Let yfinance handle the session internally (uses curl_cffi for better browser mimicking)
# Don't pass custom session objects to modern API clients
ticker = yf.Ticker(symbol)  # ✅ Correct
# ticker = yf.Ticker(symbol, session=session)  # ❌ Wrong for modern versions
```

#### API Rate Limiting
```python
# Add delays between requests to avoid rate limiting
import time

def fetch_multiple_accounts(accounts):
    results = []
    for account in accounts:
        result = fetch_account_data(account)
        results.append(result)
        time.sleep(0.5)  # 500ms delay between requests
    return results
```

### Data Transformation Patterns

#### Transaction Mapping
```python
# Centralized mapping function
async def map_tinkoff_operation_to_transaction(operation, investor, account):
    """Map T-Bank operation to internal transaction structure"""

    # Handle different operation types
    if operation.type == OperationType.OPERATION_TYPE_BUY:
        return await map_buy_operation(operation, investor, account)
    elif operation.type == OperationType.OPERATION_TYPE_SELL:
        return await map_sell_operation(operation, investor, account)
    elif operation.type == OperationType.OPERATION_TYPE_BOND_REPAYMENT:
        return await map_bond_redemption(operation, investor, account)
    # ... other operation types

    raise ValueError(f"Unsupported operation type: {operation.type}")
```

#### Special Case: Bond Redemption Quantity=0
```python
# T-Bank API returns quantity=0 for bond redemptions
# The actual redemption info is in the payment field
if operation.type in [
    OperationType.OPERATION_TYPE_BOND_REPAYMENT,
    OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL,
]:
    if operation.payment:
        cash_received = quotation_to_decimal(operation.payment)
        transaction_data["cash_flow"] = cash_received
        transaction_data["notional_change"] = cash_received

    # Set quantity to None (bonds held doesn't change)
    transaction_data["quantity"] = None
    transaction_data["price"] = None
```

#### Currency and Amount Handling
```python
def quotation_to_decimal(quotation):
    """Convert T-Bank MoneyValue to Decimal"""
    units = Decimal(quotation.units)
    nano = Decimal(quotation.nano) / Decimal(1000000000)
    return units + nano

def decimal_to_quotation(decimal_value):
    """Convert Decimal to T-Bank MoneyValue"""
    units = int(decimal_value)
    nano = int((decimal_value - Decimal(units)) * 1000000000)
    return MoneyValue(units=units, nano=nano)
```

---

## Yahoo Finance Integration

### Browser Mimicking Strategy

#### Modern yfinance Architecture
```python
# Modern yfinance (v0.2.30+) uses curl_cffi internally
# This automatically handles browser mimicking and anti-bot protection
ticker = yf.Ticker(symbol)
data = ticker.history(start="2024-01-01", end="2024-12-31")
```

#### Direct Requests with Headers
```python
# For direct API calls (availability checks, etc.)
def is_yahoo_finance_available():
    """Check if Yahoo Finance is available with proper headers"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    try:
        response = requests.get("https://finance.yahoo.com", headers=headers, timeout=10)
        return response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False
```

### API Parameter Constraints

#### Date Range Limitations
```python
# yfinance allows max 2 of 3 parameters: period, start, end
# ❌ Wrong - Setting all three causes error
ticker.history(period="1d", start="2024-01-01", end="2024-01-02")

# ✅ Correct - Only use start and end
ticker.history(start="2024-01-01", end="2024-01-02")

# ✅ Correct - Use period only
ticker.history(period="1mo")
```

#### Currency Pair Format
```python
# Currency pairs must be in XXXYYY=X format
def get_fx_rate(from_currency, to_currency, date):
    currency_pair = f"{from_currency}{to_currency}=X"  # e.g., "USDEUR=X"
    ticker = yf.Ticker(currency_pair)

    data = ticker.history(
        start=date.strftime('%Y-%m-%d'),
        end=date.strftime('%Y-%m-%d')
    )

    return data['Close'].iloc[0] if not data.empty else None
```

---

## Error Handling & Resilience Patterns

### Circuit Breaker Pattern
```python
import time
from functools import wraps

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == 'OPEN':
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = 'HALF_OPEN'
                else:
                    raise Exception("Circuit breaker is OPEN")

            try:
                result = func(*args, **kwargs)
                if self.state == 'HALF_OPEN':
                    self.state = 'CLOSED'
                    self.failure_count = 0
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    self.state = 'OPEN'

                raise e
        return wrapper

# Usage
@circuit_breaker(failure_threshold=3, recovery_timeout=30)
def fetch_market_data(symbol):
    return api_client.get_data(symbol)
```

### Retry Pattern with Exponential Backoff
```python
import time
import random

def retry_with_backoff(max_retries=3, base_delay=1, max_delay=60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, APITimeoutError) as e:
                    if attempt == max_retries - 1:
                        raise e

                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    time.sleep(delay)

        return wrapper
    return decorator

# Usage
@retry_with_backoff(max_retries=3, base_delay=1)
def fetch_with_retry(url):
    return requests.get(url, timeout=10)
```

### Graceful Degradation
```python
def get_portfolio_prices(securities, date):
    """Get prices with fallback strategies"""

    # Try primary data source
    prices = get_prices_from_primary_source(securities, date)

    # If primary fails, try secondary
    if not prices:
        logger.warning("Primary source failed, trying secondary")
        prices = get_prices_from_secondary_source(securities, date)

    # If all fail, use last known prices
    if not prices:
        logger.warning("All sources failed, using last known prices")
        prices = get_last_known_prices(securities)

    return prices
```

---

## Data Validation & Quality

### Schema Validation
```python
from pydantic import BaseModel, validator
from decimal import Decimal
from datetime import date

class TinkoffOperation(BaseModel):
    id: str
    type: str
    date: date
    payment: Decimal
    quantity: Decimal
    price: Decimal

    @validator('quantity')
    def validate_quantity(cls, v):
        if v < 0 and v != 0:
            raise ValueError("Quantity cannot be negative (except zero for redemptions)")
        return v

    @validator('price')
    def validate_price(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Price must be positive")
        return v
```

### Business Logic Validation
```python
def validate_transaction_consistency(transaction_data, existing_position=None):
    """Validate transaction against business rules"""
    errors = []

    # Check for duplicate transactions
    if is_duplicate_transaction(transaction_data):
        errors.append("Transaction appears to be a duplicate")

    # Check position consistency
    if transaction_data['type'] == 'Sell':
        if existing_position and abs(transaction_data['quantity']) > existing_position:
            errors.append("Cannot sell more than position")

    # Check price reasonableness
    if transaction_data['price']:
        if not is_price_reasonable(transaction_data):
            errors.append("Price seems unreasonable")

    return errors
```

### Data Quality Monitoring
```python
def monitor_api_quality():
    """Monitor data quality from external APIs"""

    # Check for missing data
    missing_prices = check_missing_prices()
    if missing_prices > threshold:
        alert_team("High number of missing prices detected")

    # Check for stale data
    stale_data = check_data_freshness()
    if stale_data > threshold:
        alert_team("Data appears to be stale")

    # Check for anomalous values
    anomalies = detect_price_anomalies()
    if anomalies:
        alert_team(f"Price anomalies detected: {anomalies}")
```

---

## Configuration & Secrets Management

### API Configuration
```python
# settings.py
API_CONFIG = {
    'tinkoff': {
        'base_url': 'https://invest-openapi.tinkoff.ru',
        'timeout': 30,
        'rate_limit': 100,  # requests per minute
        'retry_attempts': 3,
    },
    'yahoo': {
        'timeout': 10,
        'rate_limit': 2000,  # requests per hour
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...',
    }
}
```

### Secure Credential Management
```python
# Use environment variables for API keys
import os

class APIClient:
    def __init__(self, api_name):
        self.config = API_CONFIG[api_name]
        self.api_key = os.getenv(f"{api_name.upper()}_API_KEY")

        if not self.api_key:
            raise ValueError(f"Missing API key for {api_name}")

    def make_request(self, endpoint, params=None):
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        return requests.get(
            f"{self.config['base_url']}/{endpoint}",
            headers=headers,
            params=params,
            timeout=self.config['timeout']
        )
```

---

## Performance Optimization

### Async Operations
```python
import asyncio
import aiohttp

async def fetch_multiple_symbols(symbols):
    """Fetch multiple symbols concurrently"""

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_symbol(session, symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return results

async def fetch_symbol(session, symbol):
    """Fetch single symbol"""
    url = f"https://api.example.com/stocks/{symbol}"

    try:
        async with session.get(url) as response:
            return await response.json()
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return None
```

### Caching Strategy
```python
from django.core.cache import cache
import hashlib

def get_cached_market_data(symbol, date):
    """Get market data with caching"""

    cache_key = f"market_data:{symbol}:{date}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return cached_data

    # Fetch from API
    data = fetch_from_api(symbol, date)

    # Cache for 1 hour
    cache.set(cache_key, data, 3600)

    return data

def invalidate_cache_for_symbol(symbol):
    """Invalidate all cache entries for a symbol"""
    # This would need to be implemented based on cache backend
    cache.delete_pattern(f"market_data:{symbol}:*")
```

### Batch Processing
```python
def process_large_portfolio(portfolio_id):
    """Process large portfolios in batches"""

    batch_size = 100
    offset = 0

    while True:
        securities = get_portfolio_securities(portfolio_id, offset, batch_size)
        if not securities:
            break

        # Process batch
        process_securities_batch(securities)

        # Add delay to respect rate limits
        time.sleep(1)

        offset += batch_size
```

---

## Testing External Integrations

### Mock API Responses
```python
import pytest
from unittest.mock import patch, Mock

@pytest.fixture
def mock_tinkoff_response():
    with patch('core.tinkoff_utils.get_operations') as mock:
        mock.return_value = [
            Mock(
                id='txn_123',
                type=Mock(value='OPERATION_TYPE_BUY'),
                date='2024-01-01',
                payment=Mock(units=1000, nano=0),
                quantity=10,
                price=Mock(units=150, nano=250000000)
            )
        ]
        yield mock

def test_import_with_mock(mock_tinkoff_response):
    """Test import process with mocked API responses"""
    result = import_transactions_from_tinkoff(account_id, start_date, end_date)

    assert result['imported'] == 1
    assert result['skipped'] == 0
```

### Integration Test Environment
```python
# Use test API endpoints when available
TEST_API_CONFIG = {
    'tinkoff': {
        'base_url': 'https://api-invest.tinkoff.ru/openapi/sandbox/',
        'use_sandbox': True,
    }
}

@pytest.fixture
def test_api_client():
    """Create test API client with sandbox credentials"""
    return APIClient('tinkoff', use_test_config=True)
```

### Contract Testing
```python
def test_api_contract():
    """Test that API responses match expected contract"""

    response = api_client.get_portfolio()

    assert 'positions' in response
    assert isinstance(response['positions'], list)

    for position in response['positions']:
        assert 'figi' in position
        assert 'quantity' in position
        assert 'average_price' in position
```

---

## Monitoring & Observability

### API Performance Metrics
```python
import time
from prometheus_client import Counter, Histogram

# Metrics
api_requests_total = Counter('api_requests_total', 'Total API requests', ['api', 'status'])
api_request_duration = Histogram('api_request_duration_seconds', 'API request duration', ['api'])

def monitor_api_call(api_name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                api_requests_total.labels(api=api_name, status='success').inc()
                return result
            except Exception as e:
                api_requests_total.labels(api=api_name, status='error').inc()
                raise
            finally:
                api_request_duration.labels(api=api_name).observe(time.time() - start_time)

        return wrapper
    return decorator

# Usage
@monitor_api_call('tinkoff')
def fetch_portfolio():
    return tinkoff_client.get_portfolio()
```

### Error Logging
```python
import logging
import traceback

logger = logging.getLogger('api_integration')

def log_api_error(api_name, error, context=None):
    """Log API errors with full context"""

    error_data = {
        'api': api_name,
        'error_type': type(error).__name__,
        'error_message': str(error),
        'traceback': traceback.format_exc(),
        'context': context or {},
        'timestamp': time.time()
    }

    logger.error(f"API Error: {error_data}")

    # Send to monitoring service
    send_error_to_monitoring(error_data)
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Hardcoded API Limits
```python
# ❌ Wrong - Hardcoded limits
API_LIMITS = {
    'requests_per_minute': 100,
    'timeout': 30
}

# ✅ Correct - Configurable limits
API_LIMITS = {
    'requests_per_minute': int(os.getenv('API_RATE_LIMIT', '100')),
    'timeout': int(os.getenv('API_TIMEOUT', '30'))
}
```

### Pitfall 2: No Graceful Fallbacks
```python
# ❌ Wrong - No fallback
def get_price(symbol):
    response = api_client.get_price(symbol)
    return response['price']

# ✅ Correct - With fallback
def get_price(symbol):
    try:
        response = api_client.get_price(symbol)
        return response['price']
    except APIError:
        logger.warning(f"Failed to get price for {symbol}, using cache")
        return get_cached_price(symbol)
```

### Pitfall 3: Ignoring Rate Limits
```python
# ❌ Wrong - No rate limiting
for symbol in symbols:
    price = api_client.get_price(symbol)

# ✅ Correct - With rate limiting
for symbol in symbols:
    price = api_client.get_price(symbol)
    time.sleep(0.1)  # Respect rate limits
```

---

## References

- **T-Bank API Documentation**: https://tinkoff.github.io/investAPI/
- **yfinance Library**: https://github.com/ranaroussi/yfinance
- **HTTP Best Practices**: https://tools.ietf.org/html/rfc7234
- **Circuit Breaker Pattern**: https://martinfowler.com/bliki/CircuitBreaker.html

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-04 | Initial API integration patterns from Yahoo Finance fix |
| 1.1 | 2025-10-04 | Added T-Bank API patterns and bond redemption handling |
| 1.2 | 2025-10-04 | Added error handling, monitoring, and testing patterns |
