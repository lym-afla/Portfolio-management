# Performance Tests

This directory contains performance tests for the broker performance update functionality.

## Test Files

### `test_save_update_broker_performance.py`
Non-SSE tests that work with any setup. These tests focus on:
- Performance calculation logic
- Account table API functionality
- Validation endpoints
- No external dependencies like daphne required

### `test_save_update_broker_performance_httpx.py`
SSE tests that use httpx with ASGI transport (compatible with uvicorn). These tests:
- Test Server-Sent Events (SSE) endpoints
- Work with uvicorn without requiring daphne
- Use async/await patterns with proper django_db marks
- Test the full broker performance update flow

## Running Tests

### Option 1: Run non-SSE tests only
```bash
pytest tests/performance/test_save_update_broker_performance.py -v
```

### Option 2: Run SSE tests with httpx (recommended for uvicorn setups)
```bash
pytest tests/performance/test_save_update_broker_performance_httpx.py -v
```

### Option 3: Run all performance tests
```bash
pytest tests/performance/ -v
```

### Option 4: Run specific test categories
```bash
# Run only calculation tests
pytest tests/performance/ -k "calculate_performance" -v

# Run only validation tests
pytest tests/performance/ -k "validation" -v

# Run only SSE tests
pytest tests/performance/ -k "update_broker_performance" -v
```

## Test Coverage

### Non-SSE Tests (`test_save_update_broker_performance.py`)
- **Calculation Tests**: Core performance calculation logic
- **API Tests**: Accounts table API functionality
- **Validation Tests**: Input validation for performance update endpoints

### SSE Tests (`test_save_update_broker_performance_httpx.py`)
- **SSE Endpoint Tests**: Test server-sent events for broker performance updates
- **Authentication Tests**: Unauthorized access handling
- **Error Handling Tests**: Missing session, no transactions scenarios
- **Integration Tests**: Full flow with database interactions

## Notes

- The non-SSE tests work in any Django test environment
- The SSE tests require uvicorn or another ASGI server (not daphne)
- Both test files use proper async/await patterns with Django's sync_to_async
- All async tests are marked with `@pytest.mark.django_db(transaction=True)`
