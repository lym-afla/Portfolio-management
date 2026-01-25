---
Tasks/complexity-refactoring-task.md
---

# Code Complexity Refactoring Task

## 🎯 Objective
Reduce C901 complexity errors across the codebase to improve code maintainability, testability, and developer experience.

## 📊 Current State
- **18 functions** exceed complexity threshold of 20
- **2 functions** with critical complexity (50+)
- **5 functions** with high complexity (30-49)
- **8 functions** with medium complexity (20-29)
- **3 functions** with low complexity (15-19)

## 🚨 Critical Functions (Immediate Action Required)

### 1. `create_security_from_micex` - Complexity: 64
- **File**: `backend/core/import_utils.py:1987`
- **Issue**: Unmanageable function with multiple responsibilities
- **Strategy**: Extract method pattern + data classes
- **Reference**: `scripts/refactoring_example.py` for complete before/after example

### 2. `create_security_from_tinkoff` - Complexity: 47
- **File**: `backend/core/import_utils.py:1454`
- **Issue**: Similar to MICEX version, needs same treatment
- **Strategy**: Extract method pattern + common base class with MICEX version

## ⚠️ High Priority Functions (Next Sprint)

3. `get_security_detail` - Complexity: 49
   - **File**: `backend/core/securities_utils.py:110`
   - **Strategy**: Builder pattern for data assembly

4. `TransactionConsumer.process_import` - Complexity: 42
   - **File**: `backend/transactions/consumers.py:592`
   - **Strategy**: Strategy pattern for different import types

5. `map_tinkoff_operation_to_transaction` - Complexity: 36
   - **File**: `backend/core/tinkoff_utils.py:725`
   - **Strategy**: Strategy pattern for operation types

6. `accounts_summary_data` - Complexity: 36
   - **File**: `backend/core/summary_utils.py:19`
   - **Strategy**: Extract method pattern

7. `TransactionViewSet.import_transactions_from_api` - Complexity: 31
   - **File**: `backend/transactions/views.py:1245`
   - **Strategy**: Extract method pattern

## 📋 Medium Priority Functions (Complexity 20-29)

8. `parse_galaxy_account_security_transactions` - Complexity: 24
9. `_calculate_open_table_output_for_api` - Complexity: 26
10. `TransactionConsumer.receive` - Complexity: 29
11. `TransactionViewSet.save_transactions` - Complexity: 25
12. `_process_transaction_row` - Complexity: 23
13. `TransactionViewSet.save_single_transaction` - Complexity: 23

## 💡 Low Priority Functions (Complexity 15-19)

14. `Assets.realized_gain_loss` - Complexity: 21
15. `UpdateAccountPerformanceConsumer.handle` - Complexity: 21
16. `PriceImportConsumer.import_prices` - Complexity: 21

## 🛠️ Implementation Plan

### Phase 1: Critical Functions (Weeks 1-2)
1. **Refactor `create_security_from_micex`**
   - Follow the complete example in `scripts/refactoring_example.py`
   - Create `MicexSecurityCreator` class
   - Extract validation, parsing, and creation methods
   - Add comprehensive unit tests

2. **Refactor `create_security_from_tinkoff`**
   - Apply similar pattern as MICEX version
   - Consider creating common base class
   - Ensure consistent interface

### Phase 2: High Priority Functions (Weeks 3-4)
1. **Implement builder pattern for `get_security_detail`**
2. **Apply strategy pattern for consumer functions**
3. **Extract methods from transaction views**
4. **Add tests for each refactored function**

### Phase 3: Medium Priority Functions (Weeks 5-6)
1. **Apply extract method pattern to remaining functions**
2. **Focus on import and table utility functions**
3. **Ensure consistent error handling**

### Phase 4: Low Priority & Validation (Weeks 7-8)
1. **Quick refactoring of low-complexity functions**
2. **Comprehensive testing of all changes**
3. **Performance validation**
4. **Documentation updates**

## 🧪 Testing Strategy

### Before Refactoring
- [ ] Ensure current test coverage ≥ 85%
- [ ] Create performance baselines
- [ ] Document current behavior

### During Refactoring
- [ ] Write tests for each extracted method
- [ ] Maintain 100% backward compatibility
- [ ] Run full test suite after each extraction
- [ ] Monitor performance impact

### After Refactoring
- [ ] Verify all tests pass
- [ ] Confirm no performance degradation
- [ ] Validate complexity reduction goals met
- [ ] Update documentation

## ⚙️ Pre-commit Integration

### Current Status
- Complexity checks are in `.flake8` with `max-complexity = 70`
- Need to enable C901 checks in pre-commit hooks

### Implementation Steps
1. **Update `.pre-commit-config.yaml`** to include complexity check
2. **Configure temporary threshold increase** during refactoring period
3. **Implement gradual threshold reduction** as functions are refactored

### Pre-commit Configuration
```yaml
- repo: https://github.com/pycqa/flake8
  rev: 6.1.0
  hooks:
    - id: flake8
      args:
        - --max-line-length=88
        - --extend-ignore=E203,W503,E501,I
        - --max-complexity=20  # Will be enforced by pre-commit
```

## 🎯 Success Criteria

### Technical Goals
- [ ] All functions have complexity ≤ 20
- [ ] Test coverage ≥ 90%
- [ ] No performance degradation (>5% impact)
- [ ] Pre-commit complexity checks enforced
- [ ] Code readability significantly improved

### Process Goals
- [ ] Team trained on complexity patterns
- [ ] Refactoring examples documented
- [ ] Continuous complexity monitoring in CI/CD
- [ ] Best practices documented in memory bank

## 📈 Monitoring & Metrics

### Tools to Use
- `flake8 --select=C901` for complexity checking
- `scripts/complexity_analysis.py` for progress tracking
- Pre-commit hook enforcement
- CI/CD complexity reporting

### Metrics to Track
- Number of functions exceeding threshold
- Average complexity per module
- Test coverage during refactoring
- Performance benchmarks
- Developer feedback on code maintainability

## 🔄 Best Practices (Post-Implementation)

### Code Review Guidelines
1. **Complexity Check**: All new functions must have complexity ≤ 15 (best practice threshold)
2. **Single Responsibility**: Each function should have one clear purpose
3. **Extract Early**: Refactor complex functions during development, not later
4. **Test Coverage**: Maintain ≥ 90% coverage for refactored code
5. **Documentation**: Update complexity patterns in memory bank

### Continuous Improvement
1. **Weekly Complexity Reviews**: Check for new complexity issues
2. **Refactoring Sprints**: Schedule regular refactoring sessions
3. **Training**: Educate team on complexity patterns
4. **Tools**: Maintain and improve refactoring tooling

## 📚 Resources

### Documentation
- `.memory-bank/Tech details/complexity-management.md` - Comprehensive guide
- `scripts/refactoring_example.py` - Concrete refactoring example
- `scripts/complexity_analysis.py` - Analysis and tracking tools

### External Resources
- [Clean Code by Robert C. Martin](https://www.amazon.com/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350884)
- [Refactoring by Martin Fowler](https://refactoring.com/)
- [Python Complexity Management](https://docs.sonarqube.org/latest/user-guide/metric-definitions/)

## 🚨 Important Notes

1. **Backward Compatibility**: All refactoring must maintain existing API contracts
2. **Database Safety**: No database schema changes during refactoring
3. **Performance**: Monitor for any performance regressions
4. **Testing**: Comprehensive testing is mandatory for each refactored function
5. **Documentation**: Update relevant documentation as changes are made

## 🎉 End State

Once this task is complete:
- All functions will have complexity ≤ 20
- Pre-commit hooks will enforce complexity checks
- Code will be more maintainable and testable
- Team will have established refactoring practices
- Complexity management will be part of regular development workflow

**Best Practice Target**: After implementation, set complexity threshold to 15 for all new code to maintain high code quality standards.
