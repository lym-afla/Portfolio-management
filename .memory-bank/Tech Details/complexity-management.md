# Code Complexity Management

This document provides comprehensive guidance for managing and reducing code complexity in the portfolio management application.

## 🎯 Complexity Thresholds

- **Target**: 15-20 (Good complexity for all functions)
- **Acceptable**: 21-25 (During refactoring periods)
- **Needs Attention**: 26-30 (Plan for refactoring)
- **High Priority**: 31+ (Immediate refactoring required)

## 📊 Current State Analysis

As of the latest analysis, the following functions exceed complexity thresholds:

### Critical (Complexity 50+) - Immediate Action Required
1. `create_security_from_micex` - 64 complexity
2. `create_security_from_tinkoff` - 47 complexity

### High Priority (Complexity 30-49)
1. `get_security_detail` - 49 complexity
2. `TransactionConsumer.process_import` - 42 complexity
3. `accounts_summary_data` - 36 complexity
4. `map_tinkoff_operation_to_transaction` - 36 complexity
5. `TransactionViewSet.import_transactions_from_api` - 31 complexity

### Medium Priority (Complexity 20-29)
- Multiple functions with complexity between 20-29 requiring refactoring

## 🛠️ Refactoring Strategies

### 1. Extract Method Pattern
Break large functions into smaller, focused methods with single responsibilities.

**Best for**: Long functions with multiple logical steps

**Example**: `create_security_from_micex` → Split into validation, parsing, creation, and metadata methods

### 2. Strategy Pattern
Replace complex conditional logic with strategy objects.

**Best for**: Functions with many if/elif branches based on type or state

**Example**: `map_tinkoff_operation_to_transaction` → Strategy for each operation type

### 3. Builder Pattern
For complex object construction with many optional parameters.

**Best for**: Functions that assemble complex data structures

**Example**: `get_security_detail` → Builder for assembling security detail data

### 4. Data Class Pattern
Use structured data classes instead of passing many parameters.

**Best for**: Functions with long parameter lists

**Example**: Transaction processing functions → TransactionData dataclass

### 5. Early Returns Pattern
Reduce nesting by returning early for validation and error cases.

**Best for**: Functions with deeply nested conditionals

**Example**: View functions → Early returns for validation failures

## 📋 Refactoring Workflow

### Phase 1: Critical Functions (Weeks 1-2)
1. `create_security_from_micex` (64) → Extract method pattern + data classes
2. `create_security_from_tinkoff` (47) → Similar approach as MICEX version

### Phase 2: High Priority Functions (Weeks 3-4)
1. `get_security_detail` (49) → Builder pattern
2. `TransactionConsumer.process_import` (42) → Strategy pattern
3. `map_tinkoff_operation_to_transaction` (36) → Strategy pattern
4. `accounts_summary_data` (36) → Extract method pattern
5. `TransactionViewSet.import_transactions_from_api` (31) → Extract method pattern

### Phase 3: Medium Priority Functions (Weeks 5-6)
- Functions with complexity 20-35
- Apply appropriate patterns based on function characteristics

### Phase 4: Validation and Cleanup (Weeks 7-8)
- Remaining functions with complexity 15-21
- Comprehensive testing and validation
- Documentation updates

## 🧪 Testing Strategy

### Before Refactoring
1. Ensure comprehensive test coverage
2. Establish performance baselines
3. Document current behavior

### During Refactoring
1. Refactor one function at a time
2. Run tests after each extraction
3. Maintain identical behavior
4. Monitor performance impact

### After Refactoring
1. Verify all tests pass
2. Check performance hasn't degraded
3. Validate complexity reduction
4. Update documentation

## ⚙️ Configuration

### Flake8 Configuration
```ini
[flake8]
max-complexity = 20  # Target threshold
# Temporarily increase to 25 during active refactoring
```

### Pre-commit Hooks
Add complexity check to pre-commit hooks for continuous monitoring.

## 📈 Monitoring

### Metrics to Track
- Number of functions exceeding complexity threshold
- Average function complexity per module
- Complexity reduction over time
- Test coverage during refactoring

### Tools
- `flake8 --select=C901` for complexity checking
- Custom scripts for complexity analysis
- CI/CD integration for continuous monitoring

## 🎯 Success Criteria

### Technical Goals
- All functions have complexity ≤ 20
- Test coverage ≥ 90%
- No performance degradation
- Improved code readability

### Process Goals
- Team trained on complexity patterns
- Refactoring becomes routine practice
- Complexity monitoring in CI/CD
- Documentation maintained

## 📚 References

### Code Quality Resources
- [Clean Code by Robert C. Martin](https://www.amazon.com/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350884)
- [Refactoring by Martin Fowler](https://refactoring.com/)
- [Python Complexity Management](https://docs.sonarqube.org/latest/user-guide/metric-definitions/)

### Project-Specific Resources
- `COMPLEXITY_REFACTORING_GUIDE.md` - Detailed refactoring guide
- `scripts/refactoring_example.py` - Concrete refactoring examples
- `scripts/complexity_analysis.py` - Complexity analysis tools

## 🔄 Continuous Improvement

### Code Review Checklist
- [ ] Function complexity ≤ 20
- [ ] Single responsibility principle followed
- [ ] Clear method names and purposes
- [ ] Adequate test coverage
- [ ] Documentation updated if needed

### Best Practices
1. Write tests before refactoring
2. Refactor in small, testable steps
3. Use extract method pattern liberally
4. Apply appropriate design patterns
5. Monitor complexity continuously
6. Train team members on complexity management

---

**Related Files:**
- `COMPLEXITY_REFACTORING_GUIDE.md` - Comprehensive refactoring strategies
- `scripts/complexity_analysis.py` - Analysis tools
- `scripts/refactoring_example.py` - Practical examples
- `.flake8` - Configuration settings
