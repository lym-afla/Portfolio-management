# 🧪 Testing Guide for Portfolio Management System

This guide provides comprehensive information about the testing framework implemented for the portfolio management system.

## 📋 Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Coverage Requirements](#coverage-requirements)
- [CI/CD Pipeline](#cicd-pipeline)
- [Performance Testing](#performance-testing)
- [Debugging Tests](#debugging-tests)
- [Best Practices](#best-practices)

## 🎯 Overview

The portfolio management system includes a comprehensive test framework designed to ensure financial accuracy, system reliability, and performance standards. The test suite follows pytest conventions and includes:

- **90%+ code coverage** for core financial calculations
- **High precision testing** (6+ decimal places)
- **Performance benchmarking** with regression detection
- **Production snapshot comparisons**
- **Comprehensive edge case coverage**
- **Automated CI/CD integration**

## 📁 Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Global fixtures and configuration
├── unit/                          # Unit tests
│   ├── calculations/              # Financial calculation tests
│   │   ├── test_fx_calculations.py
│   │   ├── test_buy_in_price.py
│   │   ├── test_gain_loss.py
│   │   └── test_nav_calculations.py
│   └── models/                    # Model tests
│       ├── test_assets.py
│       └── test_transactions.py
├── integration/                   # Integration tests
│   ├── api/                       # API endpoint tests
│   │   └── test_endpoints_comprehensive.py
│   ├── database/                  # Database constraint tests
│   │   └── test_constraints.py
│   └── workflows/                 # Workflow tests
│       ├── test_transaction_flow.py
│       └── test_fx_integration.py
├── advanced/                      # Advanced testing
│   ├── test_regression_suite.py
│   ├── test_performance_suite.py
│   ├── test_production_snapshots.py
│   └── test_edge_cases.py
├── load/                          # Load testing
│   └── locustfile.py
├── smoke/                         # Smoke tests (for production)
└── fixtures/                      # Test fixtures and factories
    ├── __init__.py
    └── factories/
        ├── __init__.py
        ├── asset_factory.py
        ├── transaction_factory.py
        └── fx_factory.py
```

## 🚀 Running Tests

### Local Development

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=portfolio_management --cov-report=html

# Run specific test categories
pytest -m unit                    # Unit tests only
pytest -m integration             # Integration tests only
pytest -m performance             # Performance tests only
pytest -m regression              # Regression tests only

# Run with parallel execution
pytest -n auto

# Run specific test file
pytest tests/unit/calculations/test_buy_in_price.py

# Run with verbose output
pytest -v

# Run tests with markers
pytest -m "not slow"             # Skip slow tests
```

### Docker Testing

```bash
# Build test environment
docker build -f Dockerfile.test -t portfolio-test .

# Run tests in Docker
docker run portfolio-test pytest

# Run with coverage
docker run portfolio-test pytest --cov=portfolio_management
```

### Performance Testing

```bash
# Run performance benchmarks
pytest tests/advanced/test_performance_suite.py --benchmark-only

# Run load testing
locust --headless --users 100 --spawn-rate 10 --run-time 60s -f tests/load/locustfile.py

# Memory profiling
python scripts/profile_memory_usage.py
```

## 📊 Test Categories

### 🔬 Unit Tests (`@pytest.mark.unit`)

Test individual components in isolation:

- **Financial Calculations**: FX rates, buy-in price, gain/loss, NAV
- **Model Methods**: Asset and transaction model logic
- **Utility Functions**: Helper functions and utilities

```python
@pytest.mark.unit
def test_buy_in_price_calculation():
    # Test buy-in price calculation logic
    pass
```

### 🔗 Integration Tests (`@pytest.mark.integration`)

Test component interactions:

- **API Endpoints**: Request/response validation
- **Database Operations**: Constraint validation, foreign keys
- **FX Integration**: Cross-currency conversions, caching

```python
@pytest.mark.integration
def test_portfolio_api_endpoint():
    # Test API endpoint integration
    pass
```

### 📈 Performance Tests (`@pytest.mark.performance`)

Test system performance characteristics:

- **Calculation Speed**: Financial calculation performance
- **Database Queries**: Query optimization
- **API Response Times**: Endpoint performance
- **Memory Usage**: Memory efficiency

```python
@pytest.mark.performance
def test_calculation_performance():
    # Test calculation performance
    pass
```

### 🔙 Regression Tests (`@pytest.mark.regression`)

Prevent calculation regressions:

- **Known Results**: Compare against expected values
- **Production Snapshots**: Validate against production data
- **Precision Requirements**: Maintain calculation accuracy

```python
@pytest.mark.regression
def test_known_calculation_result():
    # Test against known expected result
    pass
```

### ⚠️ Edge Case Tests (`@pytest.mark.edge_case`)

Test boundary conditions and error scenarios:

- **Boundary Values**: Minimum/maximum values
- **Invalid Inputs**: Error handling validation
- **System Robustness**: Recovery from errors

```python
@pytest.mark.edge_case
def test_zero_quantity_transaction():
    # Test edge case handling
    pass
```

## 📏 Coverage Requirements

### Coverage Targets

- **Overall Coverage**: ≥90%
- **Core Calculations**: ≥95%
- **API Endpoints**: ≥85%
- **Models**: ≥90%

### Coverage Exclusions

```toml
[tool.coverage.run]
omit = [
    "*/migrations/*",
    "*/tests/*",
    "*/venv/*",
    "*/env/*",
    "manage.py",
    "portfolio_management/wsgi.py",
    "portfolio_management/asgi.py",
]
```

### Generating Coverage Reports

```bash
# HTML report (detailed)
pytest --cov=portfolio_management --cov-report=html

# Terminal report
pytest --cov=portfolio_management --cov-report=term-missing

# XML report (for CI/CD)
pytest --cov=portfolio_management --cov-report=xml
```

## 🔄 CI/CD Pipeline

### GitHub Actions Workflows

1. **Main CI Pipeline** (`.github/workflows/ci.yml`)
   - Multi-Python version testing (3.9, 3.10, 3.11)
   - Linting (Black, isort, flake8, mypy)
   - Security scanning (Bandit, Safety)
   - Test execution with coverage
   - Performance benchmarks
   - Regression testing

2. **PR Checks** (`.github/workflows/pr-checks.yml`)
   - Quick formatting checks
   - Unit test execution
   - Integration test execution
   - Performance regression detection
   - Code size analysis

3. **Performance Benchmarks** (`.github/workflows/performance-benchmarks.yml`)
   - Scheduled performance testing
   - Load testing with Locust
   - Memory profiling
   - Performance regression alerts

### Pipeline Status

- ✅ **Phase 1-4**: Test framework implementation completed
- 🔄 **Phase 5**: CI/CD integration in progress

## ⚡ Performance Testing

### Benchmark Categories

- **Calculation Performance**: Financial calculation speed
- **Database Performance**: Query efficiency
- **API Performance**: Response times
- **Memory Usage**: Memory efficiency
- **Load Testing**: Concurrent user handling

### Performance Thresholds

```python
PERFORMANCE_THRESHOLDS = {
    'small_portfolio_calculation': {'max_mean_ms': 50},
    'medium_portfolio_calculation': {'max_mean_ms': 200},
    'large_portfolio_calculation': {'max_mean_ms': 1000},
    'fx_rate_lookup': {'max_mean_ms': 1},
    'api_endpoint_response': {'max_mean_ms': 100},
}
```

### Running Performance Tests

```bash
# Benchmark tests
pytest tests/advanced/test_performance_suite.py --benchmark-only

# Load testing
locust --headless --users 100 --spawn-rate 10 --run-time 60s \
       --host http://localhost:8000 -f tests/load/locustfile.py

# Memory profiling
mprof run python scripts/profile_memory_usage.py
mprof plot --output memory-profile.png mprof_*.dat
```

## 🐛 Debugging Tests

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Ensure test database is running
   python manage.py migrate --settings=portfolio_management.settings.test
   ```

2. **Missing Fixtures**
   ```bash
   # Check fixture loading
   pytest --collect-only
   ```

3. **Import Errors**
   ```bash
   # Check Python path
   python -c "import portfolio_management; print('OK')"
   ```

### Debugging Tools

```bash
# Run with debugging
pytest --pdb

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Run specific test with output
pytest -s tests/unit/calculations/test_buy_in_price.py::test_simple_buy
```

### Test Database

```bash
# Reset test database
python manage.py flush --settings=portfolio_management.settings.test

# Create test data
python manage.py loaddata tests/fixtures/test_data.json
```

## ✨ Best Practices

### Writing Tests

1. **Use Descriptive Names**
   ```python
   def test_buy_in_price_calculation_with_partial_sale():
       # Clear description of what's being tested
   ```

2. **Follow AAA Pattern**
   ```python
   def test_calculation():
       # Arrange
       transactions = create_test_transactions()

       # Act
       result = calculate_buy_in_price(transactions)

       # Assert
       assert result == expected_value
   ```

3. **Use Fixtures Effectively**
   ```python
   @pytest.fixture
   def sample_portfolio():
       return PortfolioFactory.create(name="Test Portfolio")
   ```

4. **Test Edge Cases**
   ```python
   def test_zero_quantity_transaction():
       # Test boundary conditions
   ```

### Financial Testing

1. **High Precision**: Use Decimal with sufficient precision
2. **Known Results**: Test against expected calculation results
3. **Currency Handling**: Test multi-currency scenarios
4. **Date Logic**: Test different date scenarios

### Performance Testing

1. **Baselines**: Establish performance baselines
2. **Regression Detection**: Monitor for performance regressions
3. **Realistic Data**: Use realistic test data sizes
4. **Consistent Environment**: Run in consistent test environment

## 📞 Getting Help

### Documentation

- ** pytest Documentation**: https://docs.pytest.org/
- ** Django Testing**: https://docs.djangoproject.com/en/stable/topics/testing/
- ** Factory Boy**: https://factoryboy.readthedocs.io/
- ** Coverage.py**: https://coverage.readthedocs.io/

### Common Commands

```bash
# Help with pytest options
pytest --help

# List available tests
pytest --collect-only

# Check test coverage
coverage report

# Run linting
black --check .
flake8 .
mypy portfolio_management/
```

### Test Results Interpretation

- **✅ PASSED**: Test completed successfully
- **❌ FAILED**: Test failed - check assertion or error
- **⚠️ SKIPPED**: Test was skipped (conditional)
- **🚫 XFAIL**: Expected failure (known issue)
- **🔄 XPASS**: Unexpected pass (test was expected to fail)

For additional help or questions about testing, refer to the project documentation or create an issue in the repository.
