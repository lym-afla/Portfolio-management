# Comprehensive Test Plan for M1 Roadmap
## CI Setup, Critical Unit Tests, Cache Invalidation Hooks

### Current Status Summary

**Test Coverage Analysis:**
- Overall coverage: **14%** (1639 total statements, 1402 missed)
- Common app coverage: **25%** (854 statements, 639 missed)
- **6 simple tests currently passing**
- **Existing tests broken** due to Asset-Broker relationship changes

**Critical Issues Identified:**
1. Broken fixtures in `conftest.py` - Asset model no longer has `brokers` relationship
2. Most core business logic untested
3. No API endpoint tests working
4. Missing cache invalidation tests

---

## M1 Roadmap Testing Priorities

### Phase 1: Foundation Repair (Week 1)
**Priority: CRITICAL - Unblock all other testing**

#### 1.1 Fix Broken Test Infrastructure
- [ ] **Task**: Repair `conftest.py` fixtures
  - Remove broken `asset.brokers.add(broker)` calls
  - Update fixtures to match current model relationships
  - Create working asset, user, broker fixtures
  - **Files**: `tests/conftest.py`

#### 1.2 Establish Working Test Pipeline
- [ ] **Task**: Configure pytest with Django properly
  - Fix Django settings configuration
  - Ensure database migrations work in tests
  - Set up test database reuse for speed
  - **Files**: `pytest.ini`

#### 1.3 Basic Coverage Baseline
- [ ] **Task**: Get existing tests running
  - Fix transaction model tests
  - Fix calculation tests (NAV, FX, bonds)
  - Establish coverage measurement
  - **Target**: Get to 20% coverage baseline

### Phase 2: Critical Business Logic Tests (Week 2-3)
**Priority: HIGH - Core financial calculations must be correct**

#### 2.1 Asset Valuation Core Methods
**Target Files**: `tests/unit/models/test_asset_valuation.py`

```python
# Critical tests to implement:
class TestAssetValuation:
    def test_calculate_value_at_date_basic(self):
        """Test basic asset valuation at specific date"""

    def test_calculate_value_at_date_with_fx_conversion(self):
        """Test asset valuation with currency conversion"""

    def test_calculate_value_at_date_bond_notional(self):
        """Test bond valuation with notional amortization"""

    def test_price_at_date_missing_price(self):
        """Test behavior when price data missing"""

    def test_position_multi_account_aggregation(self):
        """Test position calculation across multiple accounts"""

    def test_position_zero_after_full_sale(self):
        """Test position becomes zero after selling all shares"""
```

#### 2.2 Bond-Specific Calculations
**Target Files**: `tests/unit/models/test_bond_calculations.py`

```python
# Critical bond calculation tests:
class TestBondCalculations:
    def test_realized_gain_loss_bond_redemption(self):
        """Test gain/loss calculation for bond redemption"""

    def test_unrealized_gain_loss_with_amortization(self):
        """Test unrealized gain/loss including notional amortization"""

    def test_get_capital_distribution_coupon_handling(self):
        """Test coupon payment calculations in capital distributions"""

    def test_get_current_aci_calculation(self):
        """Test accrued interest calculation accuracy"""

    def test_bond_ytm_calculation(self):
        """Test yield-to-maturity calculation"""

    def test_bond_aci_calculation(self):
        """Test bond ACI (accrued interest) calculation"""
```

#### 2.3 Portfolio Calculation Core
**Target Files**: `tests/unit/calculations/test_portfolio_core.py`

```python
# Critical portfolio calculation tests:
class TestPortfolioCalculations:
    def test_nav_at_date_with_cash_balances(self):
        """Test NAV calculation including cash balances"""

    def test_nav_at_date_multi_currency(self):
        """Test NAV calculation with FX conversion"""

    def test_irr_calculation_basic(self):
        """Test IRR calculation for simple cash flows"""

    def test_irr_edge_cases(self):
        """Test IRR edge cases (N/R, N/A scenarios)"""

    def test_calculate_percentage_shares(self):
        """Test portfolio composition percentage calculations"""

    def test_multi_account_aggregation(self):
        """Test portfolio aggregation across multiple accounts"""
```

#### 2.4 Cash Flow Calculations
**Target Files**: `tests/unit/calculations/test_cash_flow_core.py`

```python
# Critical cash flow tests:
class TestCashFlowCalculations:
    def test_get_calculated_cash_flow_single_transaction(self):
        """Test cash flow calculation for single transaction"""

    def test_get_calculated_cash_flow_with_commission(self):
        """Test cash flow including commission impact"""

    def test_get_cash_flow_by_currency(self):
        """Test cash flow aggregation by currency"""

    def test_fx_transaction_cash_flow(self):
        """Test FX transaction cash flow handling"""
```

### Phase 3: API and Integration Tests (Week 4)
**Priority: MEDIUM - Ensure API reliability**

#### 3.1 Dashboard API Tests
**Target Files**: `tests/integration/api/test_dashboard_apis.py`

```python
# Dashboard API tests:
class TestDashboardAPI:
    def test_get_dashboard_summary_api_basic(self):
        """Test dashboard summary calculation"""

    def test_get_dashboard_summary_multi_currency(self):
        """Test dashboard summary with FX conversion"""

    def test_performance_chart_data_api(self):
        """Test performance chart data generation"""

    def test_portfolio_summary_endpoints(self):
        """Test portfolio summary endpoints"""
```

#### 3.2 Position Tracking Tests
**Target Files**: `tests/integration/api/test_position_tracking.py`

```python
# Position tracking tests:
class TestPositionTracking:
    def test_open_position_calculations(self):
        """Test open position valuation"""

    def test_closed_position_analysis(self):
        """Test closed position P&L calculations"""

    def test_position_entry_exit_dates(self):
        """Test position holding period calculations"""
```

### Phase 4: Cache Invalidation Tests (Week 5)
**Priority: HIGH - Ensure data consistency**

#### 4.1 FX Rate Caching
**Target Files**: `tests/integration/cache/test_fx_caching.py`

```python
# FX caching tests:
class TestFXCaching:
    def test_fx_rate_caching_behavior(self):
        """Test FX rate caching and invalidation"""

    def test_fx_rate_cache_update_on_new_data(self):
        """Test cache updates when new FX data added"""

    def test_cross_currency_path_caching(self):
        """Test caching of cross-currency conversion paths"""
```

#### 4.2 Portfolio Calculation Caching
**Target Files**: `tests/integration/cache/test_portfolio_caching.py`

```python
# Portfolio caching tests:
class TestPortfolioCaching:
    def test_nav_calculation_caching(self):
        """Test NAV calculation caching"""

    def test_portfolio_aggregation_cache_invalidation(self):
        """Test cache invalidation on portfolio changes"""

    def test_cache_invalidation_on_new_transaction(self):
        """Test cache invalidation when transactions added"""
```

---

## Detailed Test File Structure

### Unit Tests Structure
```
tests/unit/
├── models/
│   ├── test_asset_valuation.py          # Asset valuation methods
│   ├── test_bond_calculations.py        # Bond-specific calculations
│   ├── test_position_tracking.py        # Position calculation methods
│   ├── test_transaction_model.py        # Transaction model (fix existing)
│   └── test_fx_model.py                 # FX model methods
├── calculations/
│   ├── test_portfolio_core.py           # Portfolio NAV/IRR calculations
│   ├── test_cash_flow_core.py           # Cash flow calculations
│   ├── test_fx_edge_cases.py            # FX conversion edge cases
│   ├── test_nav_calculations.py         # Fix existing NAV tests
│   ├── test_buy_in_price.py             # Fix existing buy-in price tests
│   ├── test_fx_calculations.py          # Fix existing FX tests
│   ├── test_gain_loss.py                # Fix existing gain/loss tests
│   ├── test_ytm_calculation.py          # Fix existing YTM tests
│   └── test_bond_aci.py                 # Fix existing ACI tests
└── utils/
    ├── test_calculation_utils.py        # Calculation utility functions
    └── test_date_utils.py               # Date handling utilities
```

### Integration Tests Structure
```
tests/integration/
├── api/
│   ├── test_dashboard_apis.py           # Dashboard API endpoints
│   ├── test_position_tracking.py        # Position tracking APIs
│   ├── test_transaction_apis.py         # Transaction processing APIs
│   ├── test_performance_apis.py         # Performance reporting APIs
│   └── test_endpoints_comprehensive.py  # Fix existing API tests
├── workflows/
│   ├── test_transaction_flow.py         # Fix existing workflow tests
│   ├── test_fx_integration.py           # FX integration workflows
│   ├── test_multi_account_workflows.py  # Multi-account workflows
│   └── test_duplicate_detection.py      # Fix existing duplicate tests
├── cache/
│   ├── test_fx_caching.py               # FX rate caching
│   ├── test_portfolio_caching.py        # Portfolio calculation caching
│   └── test_cache_invalidation.py       # Cache invalidation hooks
└── database/
    ├── test_constraints.py              # Fix existing constraint tests
    └── test_data_integrity.py           # Data integrity tests
```

### Performance Tests Structure
```
tests/performance/
├── test_calculation_performance.py      # Calculation performance tests
├── test_api_performance.py              # API response time tests
└── test_database_performance.py         # Database query performance
```

---

## Success Metrics for M1

### Coverage Targets
- **Week 1**: 20% coverage (baseline)
- **Week 2**: 35% coverage (core calculations)
- **Week 3**: 50% coverage (complete business logic)
- **Week 4**: 60% coverage (including APIs)
- **Week 5**: 70% coverage (including cache tests)

### Test Execution Targets
- **Unit tests**: < 2 seconds execution time
- **Integration tests**: < 30 seconds execution time
- **Full test suite**: < 2 minutes execution time

### Quality Gates
- All critical business logic methods must have ≥ 80% coverage
- All API endpoints must have basic integration tests
- All cache invalidation scenarios must be tested
- No broken tests allowed in CI pipeline

---

## Implementation Strategy

### Week-by-Week Execution Plan

#### Week 1: Foundation
1. Day 1-2: Fix conftest.py and basic test infrastructure
2. Day 3-4: Get existing tests running and measure baseline
3. Day 5: Set up CI pipeline with basic test execution

#### Week 2: Core Asset Tests
1. Day 1-2: Implement asset valuation tests
2. Day 3-4: Implement bond calculation tests
3. Day 5: Coverage checkpoint and adjustments

#### Week 3: Portfolio Tests
1. Day 1-2: Implement portfolio calculation tests
2. Day 3-4: Implement cash flow calculation tests
3. Day 5: Integration testing of calculations

#### Week 4: API Tests
1. Day 1-2: Implement dashboard API tests
2. Day 3-4: Implement position tracking tests
3. Day 5: API integration testing

#### Week 5: Cache Tests
1. Day 1-2: Implement FX caching tests
2. Day 3-4: Implement portfolio caching tests
3. Day 5: Final integration and coverage validation

### Risk Mitigation
1. **Fixture Dependency Hell**: Use factory pattern for test data
2. **Performance Issues**: Use test database reuse and selective test execution
3. **CI Pipeline Bottlenecks**: Implement test categorization and parallel execution
4. **Data Consistency**: Implement proper test isolation and cleanup

---

## Next Steps

1. **Immediate**: Fix conftest.py to unblock existing tests
2. **Week 1**: Establish baseline coverage and CI pipeline
3. **Week 2-5**: Implement comprehensive test coverage according to plan
4. **Ongoing**: Monitor coverage metrics and adjust priorities

This plan provides a clear roadmap for achieving M1 goals of CI setup, critical unit tests, and cache invalidation hook testing.
