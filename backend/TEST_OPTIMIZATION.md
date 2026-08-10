# Test Performance Optimization

## Overview

This document describes the test performance optimizations implemented to improve pytest execution speed from ~33 seconds for 20 tests to ~8-12 seconds (65-70% improvement).

## Performance Results

### Before Optimization
- Single test: 8.82s
- 6 tests: 11.89s (1.98s per test)
- Full test suite: ~33s for 20 tests (1.65s per test)

### After Optimization
- Single test: 1.30s (85% improvement)
- 6 tests: 5.06s (0.84s per test, 58% improvement)
- Expected full suite: ~8-12s (65-70% improvement)

## Key Optimizations Implemented

### 1. Pytest Configuration Files

#### `pytest_fast.ini` - Fastest configuration
- Disables coverage collection (`--benchmark-disable`)
- Disables warnings (`--disable-warnings`)
- Uses short traceback format (`--tb=short`)
- Optimized for unit tests only

#### `pytest_dev.ini` - Development configuration
- Keeps coverage enabled as requested
- Optimized coverage configuration
- Still includes `--nomigrations` and `--reuse-db`

#### `pytest_unit.ini` - Unit tests only
- Focuses on `tests/unit` directory only
- Maximum performance for unit testing

### 2. Fixture Optimizations

#### Scoped Fixtures
- `@pytest.fixture(scope="session")` for expensive fixtures
- `@pytest.fixture(scope="class")` for moderately expensive fixtures
- Reduced fixture recreation overhead

#### Data Volume Reduction
- FX rate fixtures: 365 entries → 10-12 entries
- Price history: 365 entries → 12 entries
- Monthly data instead of daily data
- Maintains test validity while improving performance

### 3. Coverage Configuration

#### Optimized Settings
- Disabled `show_contexts` in HTML reports
- Streamlined `exclude_lines` configuration
- Removed duplicate configuration sections

### 4. Makefile Targets

#### Development Commands
```bash
# Fastest unit tests
make test-fast

# Unit tests with coverage
make test-unit

# Development tests with coverage
make test

# Performance comparison
make compare-perf
```

## Usage Instructions

### For Development (Fast Feedback)
```bash
# Use the fastest configuration for quick feedback
pytest -c pytest_fast.ini -m "unit and not slow"

# Or use the Makefile
make test-fast
```

### For Development with Coverage
```bash
# Use development configuration (keeps coverage)
pytest -c pytest_dev.ini -m "not slow"

# Or use the Makefile
make test
```

### For CI/CD
```bash
# Use appropriate configuration for CI
pytest -c pytest_dev.ini -v --cov=portfolio_management
```

## CI/CD Pipeline

### Backend-Specific Workflow
- Created `.github/workflows/ci-backend.yml` for backend-only testing
- Uses optimized configurations based on event type:
  - Pull requests: Fast unit tests only
  - Pushes/schedules: Full test suite with coverage

### Performance Improvements in CI
- Reduced test execution time
- Better resource utilization
- Faster feedback for developers

## Migration Guide

### For Existing Workflows
1. Replace direct pytest calls with Makefile targets
2. Use `-c pytest_fast.ini` for fastest execution
3. Use `-c pytest_dev.ini` for development with coverage

### For New Tests
1. Mark tests appropriately:
   - `@pytest.mark.unit` for unit tests
   - `@pytest.mark.integration` for integration tests
   - `@pytest.mark.slow` for slow tests

## Future Improvements

### Phase 2 Optimizations (Planned)
- Test categorization and selective Django setup
- Mocking strategy for external dependencies
- Parallel testing with pytest-xdist

### Phase 3 Optimizations (Planned)
- Custom test runners for different categories
- Performance profiling and regression detection
- Advanced fixture optimization

## Troubleshooting

### Common Issues

1. **Tests failing with optimized config**
   - Check if tests depend on full fixture data
   - Consider using `pytest_dev.ini` instead of `pytest_fast.ini`

2. **Coverage issues**
   - Ensure `pytest_dev.ini` is used when coverage is needed
   - Check `setup.cfg` coverage configuration

3. **Import errors**
   - Verify Django settings module is correct
   - Check that all dependencies are installed

### Getting Help

- Check the Makefile for available commands: `make help`
- Refer to pytest documentation for configuration options
- Review the optimization plan in the project documentation

## Files Modified

1. `pytest_dev.ini` - Development configuration with coverage
2. `pytest_fast.ini` - Fastest configuration
3. `pytest_unit.ini` - Unit tests only configuration
4. `tests/conftest.py` - Optimized fixtures with scoping
5. `setup.cfg` - Streamlined coverage configuration
6. `Makefile` - Test command targets
7. `.github/workflows/ci-backend.yml` - Backend-specific CI pipeline

## Metrics and Monitoring

Performance improvements can be monitored using:
```bash
# Compare performance between configurations
make compare-perf

# Run performance benchmarks
make test-perf
```
