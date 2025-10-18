---
Tasks/backend-test-framework-design.md
---

# Backend Test Framework Design & Implementation Plan

**Created:** 2025-10-18
**Status:** ✅ COMPLETED 2025-10-18
**Priority:** High
**Implementation Started:** 2025-10-18
**Phase 1 & 2:** ✅ COMPLETED
**Phase 3:** ✅ COMPLETED
**Phase 4:** ✅ COMPLETED
**Phase 5:** ✅ COMPLETED

## Overview

Design and implement a comprehensive backend test framework for the portfolio management system to ensure financial accuracy, prevent regressions, and maintain code quality standards.

## Current State Analysis

### Existing Test Infrastructure
- **Minimal Coverage**: Only placeholder `tests.py` files exist across modules
- **Basic pytest Setup**: Simple `conftest.py` with user, broker, and asset fixtures
- **No Financial Testing**: Critical calculations in `common/models.py` are untested
- **Missing Test Data**: No realistic market data or transaction fixtures

### Identified Gaps
1. **Core Financial Logic**: No tests for FX calculations, NAV computations, buy-in price algorithms
2. **Integration Testing**: No API endpoint or database integration tests
3. **Regression Protection**: No production data regression tests
4. **Performance Testing**: No tests for large dataset processing
5. **Edge Case Coverage**: No tests for boundary conditions or error scenarios

## Proposed Test Framework Architecture

### 1. Directory Structure
```
tests/
├── conftest.py                    # Enhanced global fixtures & configuration
├── unit/                          # Fast, isolated unit tests
│   ├── models/
│   │   ├── test_assets.py         # Asset model method tests
│   │   ├── test_transactions.py   # Transaction model tests
│   │   ├── test_fx.py            # FX model tests
│   │   └── test_brokers.py       # Broker model tests
│   ├── calculations/
│   │   ├── test_fx_calculations.py   # FX rate calculation tests
│   │   ├── test_nav_calculations.py  # NAV computation tests
│   │   ├── test_buy_in_price.py      # Buy-in price algorithm tests
│   │   └── test_gain_loss.py         # Gain/loss calculation tests
│   └── utils/
│       ├── test_portfolio_utils.py   # Portfolio utility functions
│       └── test_securities_utils.py  # Securities utility functions
├── integration/                   # Database & API integration tests
│   ├── api/
│   │   ├── test_endpoints.py     # API endpoint tests
│   │   └── test_serializers.py   # API serializer tests
│   ├── database/
│   │   ├── test_constraints.py   # Database constraint tests
│   │   └── test_migrations.py    # Migration tests
│   └── workflows/
│       ├── test_transaction_flow.py  # Transaction processing tests
│       └── test_fx_integration.py    # FX rate integration tests
├── fixtures/                      # Test data fixtures
│   ├── json/
│   │   ├── sample_transactions.json
│   │   ├── sample_assets.json
│   │   └── fx_rate_data.json
│   └── factories/
│       ├── asset_factory.py      # Asset model factory
│       ├── transaction_factory.py # Transaction model factory
│       └── fx_factory.py         # FX rate factory
├── regression/                    # Production regression tests
│   ├── test_nav_regression.py    # NAV calculation regression
│   ├── test_fx_regression.py     # FX calculation regression
│   └── production_snapshots/     # Production data snapshots
└── performance/                   # Performance and load tests
    ├── test_large_datasets.py    # Large dataset processing
    └── test_query_performance.py # Database query performance
```

### 2. Test Categories & Priorities

#### **HIGH PRIORITY** (Core Financial Logic - 90%+ coverage required)
- **FX Rate Calculations**: `FX.get_rate()` method with cross-currency conversions
- **Buy-In Price Algorithm**: `Assets.calculate_buy_in_price()` edge cases and precision
- **Realized/Unrealized Gains**: Gain/loss calculation accuracy across scenarios
- **NAV Computations**: Net Asset Value calculation integrity
- **Transaction Processing**: Transaction flow and balance updates
- **Position Calculations**: Asset position determination logic
- **Bond Valuation**: Bond notional and coupon calculations (if implemented)

#### **MEDIUM PRIORITY** (Integration & API)
- **API Endpoints**: REST API functionality and response validation
- **Database Constraints**: Model constraint enforcement
- **Broker Balance Calculations**: Cash balance accuracy
- **FX Rate Integration**: External API integration handling
- **Annual Performance**: Aggregated performance calculations

#### **LOW PRIORITY** (Basic Functionality)
- **CRUD Operations**: Basic create/read/update/delete operations
- **Simple Validations**: Field-level validation tests
- **Authentication**: User authentication and authorization

### 3. Enhanced Test Infrastructure

#### Global Fixtures (`conftest.py`)
```python
# Enhanced fixtures for:
- Multi-currency test data
- Historical price series
- FX rate scenarios (direct & cross-currency)
- Transaction patterns (buys, sells, dividends, corporate actions)
- Broker configurations
- User scenarios with different permissions
- Test database with proper constraints
- Decimal precision helpers
```

#### Factory Classes
- **AssetFactory**: Generate realistic assets with various types
- **TransactionFactory**: Create transaction sequences for testing
- **FXRateFactory**: Generate FX rate data for different currency pairs
- **BrokerFactory**: Create broker configurations
- **PriceHistoryFactory**: Generate historical price data

#### Test Data Management
- **Realistic Market Data**: Historical prices for common securities
- **FX Rate Histories**: Multi-year FX rate data
- **Transaction Scenarios**: Common investment patterns
- **Edge Case Data**: Boundary conditions and error scenarios

### 4. Specialized Test Modules

#### Financial Calculation Tests
```python
# Key focus areas:
- Decimal precision and rounding
- Cross-currency FX conversions
- Buy-in price algorithm accuracy
- Realized gain calculations for partial sales
- Unrealized gain calculations
- Position determination logic
- NAV aggregation accuracy
```

#### Integration Tests
```python
# Coverage areas:
- API endpoint functionality
- Database constraint enforcement
- Transaction workflow integrity
- FX rate API integration
- External data source integration
```

#### Regression Tests
```python
# Protection against:
- NAV calculation changes
- FX rate calculation modifications
- Buy-in price algorithm changes
- Performance regressions
- Production data drift
```

### 5. Testing Standards & Conventions

#### Code Quality Standards
- **Framework**: pytest (as specified in testing conventions)
- **Data Types**: Decimal for all numeric values
- **Coverage**: >=90% for core calculations, >=80% overall
- **Fixtures**: Realistic production-like data
- **Precision**: Consistent Decimal usage throughout tests

#### Test Naming & Structure
```python
# Naming convention:
test_[method]_[scenario]_[expected_result]

# Examples:
test_fx_get_rate_direct_currency_success
test_buy_in_price_long_position_partial_sales
test_nav_calculation_multi_currency_portfolio
```

#### Test Documentation
- **Docstrings**: Clear description of what each test validates
- **Comments**: Explanation of complex financial scenarios
- **Fixtures**: Documentation of test data purpose and structure

### 6. Implementation Phases

#### **Phase 1: Foundation Setup** (Week 1-2) ✅ COMPLETED 2025-10-18
- [x] Create new test directory structure
- [x] Enhance `conftest.py` with comprehensive fixtures
- [x] Implement factory classes for test data generation
- [x] Create sample test data fixtures
- [x] Set up test database configuration

#### **Phase 2: Core Calculation Tests** (Week 2-4) ✅ COMPLETED 2025-10-18
- [x] FX rate calculation tests (`test_fx_calculations.py`) ✅
- [x] Buy-in price algorithm tests (`test_buy_in_price.py`) ✅
- [x] Gain/loss calculation tests (`test_gain_loss.py`) ✅
- [x] NAV computation tests (`test_nav_calculations.py`) ✅
- [x] Asset position tests (`test_assets.py`) ✅
- [x] Transaction processing tests (`test_transactions.py`) ✅

#### **Phase 3: Integration & API Tests** (Week 4-5) ✅ COMPLETED 2025-10-18
- [x] API endpoint tests (`test_endpoints_comprehensive.py`) ✅
- [x] Database constraint tests (`test_constraints.py`) ✅
- [x] Transaction flow tests (`test_transaction_flow.py`) ✅
- [x] FX integration tests (`test_fx_integration.py`) ✅

#### **Phase 4: Advanced Testing** (Week 5-6) ✅ COMPLETED 2025-10-18
- [x] Regression test implementation (`test_regression_suite.py`) ✅
- [x] Performance test setup (`test_performance_suite.py`) ✅
- [x] Production snapshot comparison (`test_production_snapshots.py`) ✅
- [x] Edge case and error scenario coverage (`test_edge_cases.py`) ✅

#### **Phase 5: CI/CD Integration** (Week 6) ✅ COMPLETED 2025-10-18
- [x] GitHub Actions/CI pipeline setup (`ci.yml`, `pr-checks.yml`) ✅
- [x] Coverage reporting configuration (`pyproject.toml`, codecov) ✅
- [x] Linting integration (flake8, black, mypy, pre-commit) ✅
- [x] Automated test execution on PRs (multi-stage validation) ✅
- [x] Performance benchmarking (benchmarking, load testing, profiling) ✅

### 7. Compliance with Memory Bank Requirements

#### Testing Convention Adherence
- **pytest Framework**: As specified in `Steerings/testing_conventions.md`
- **Decimal Usage**: Consistent with `Steerings/Calculation Conventions.md`
- **Coverage Targets**: >=90% for core computations
- **Realistic Fixtures**: Production-like transaction data

#### Protected Logic Testing
- **NAV Calculations**: Comprehensive test coverage for protected logic
- **FX Decomposition**: FX effect calculation validation
- **Buy-In Price**: Average buy-in price algorithm testing
- **Bond Handling**: Bond valuation and notional tests

#### Financial Accuracy
- **Precision Testing**: Decimal precision validation
- **Cross-Currency**: Multi-currency portfolio testing
- **Edge Cases**: Boundary condition and error scenario coverage
- **Regression Protection**: Production result consistency

### 8. Success Metrics

#### Coverage Metrics
- **Core Calculations**: >=90% line coverage
- **Overall Codebase**: >=80% line coverage
- **Branch Coverage**: >=85% for decision logic

#### Quality Metrics
- **Test Pass Rate**: 100% on CI pipeline
- **Performance**: Test suite completion <5 minutes
- **Regression Detection**: Zero production calculation regressions

#### Maintenance Metrics
- **Test Documentation**: 100% test docstring coverage
- **Fixture Reusability**: >=80% fixture reuse across tests
- **Test Stability**: Zero flaky tests in CI

### 9. Risk Mitigation

#### Technical Risks
- **Data Accuracy**: Validate all test data against known good results
- **Performance**: Monitor test execution time and optimize
- **Complexity**: Break down complex scenarios into manageable test units

#### Business Risks
- **Financial Accuracy**: Peer review of all financial calculation tests
- **Regression Protection**: Automated regression test execution
- **Compliance**: Ensure tests meet financial accuracy standards

### 10. Next Steps

1. **Review and Approve**: Stakeholder review of this test framework design
2. **Resource Allocation**: Assign development resources for implementation
3. **Timeline Confirmation**: Confirm implementation timeline and milestones
4. **Tool Setup**: Prepare development environment and testing tools
5. **Begin Implementation**: Start with Phase 1 foundation setup

## Dependencies

- **Testing Framework**: pytest, pytest-django, pytest-cov
- **Test Data**: factory_boy, faker
- **API Testing**: requests, django-rest-framework-test
- **Performance Testing**: pytest-benchmark
- **Database**: Test database configuration (SQLite for speed, PostgreSQL for integration)

## Notes

- This design prioritizes financial calculation accuracy above all else
- Test framework should evolve with application complexity
- Regular review and updates needed as business logic changes
- Consider test data privacy and security for production snapshots

---

**Related Documents:**
- [Steerings/testing_conventions.md](../Steerings/testing_conventions.md)
- [Steerings/Calculation Conventions.md](../Steerings/Calculation%20Conventions.md)
- [Product Overview/Portfolio NAV.md](../Product%20Overview/Portfolio%20NAV.md)
- [Tech details/NAV Function and FX Flow.md](../Tech%20details/NAV%20Function%20and%20FX%20Flow.md)
