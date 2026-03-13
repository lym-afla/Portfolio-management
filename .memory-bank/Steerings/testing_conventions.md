---
Steerings/testing_conventions.md
---

# Testing Conventions

**Purpose:** Define expectations and patterns for tests so numerical correctness is preserved.

- **Test framework:** `pytest` for backend.
- **Fixtures:** Use realistic fixtures that mimic production transactions for regression tests.
- **Data types:** Tests must use `Decimal` consistently for numeric values.
- **Coverage:** Aim for high unit coverage on calculation modules — **>=90%** for core computations.
- **Test types:**
  - Unit tests for calculation helpers and small services.
  - Integration tests for API endpoints with DB fixtures.
  - Regression tests that reproduce historical production outputs.
- **CI:** Run tests and linters on each PR.

## CI/CD Pipeline

### Current GitHub Actions Workflows

**Main CI Pipeline** (`.github/workflows/ci.yml`):
- **Triggers**: Push to main/develop, PRs, daily schedule
- **Matrix Testing**: Python 3.9, 3.10, 3.11 on Ubuntu
- **Services**: PostgreSQL 15 database
- **Test Coverage**: 90% minimum threshold
- **Performance Benchmarks**: Automated regression detection
- **Security Scanning**: Bandit, Safety, Trivy vulnerability scanning
- **Code Quality**: Black, isort, flake8, mypy validation

**PR Checks** (`.github/workflows/pr-checks.yml`):
- **Quick Checks**: Code formatting, linting, security scanning
- **Unit Tests**: 85% coverage requirement on portfolio_management module
- **Integration Tests**: API and workflow testing
- **Performance Checks**: Benchmark regression detection
- **Size Analysis**: Large file detection (>1000 lines)
- **PR Summary**: Automated status comments with recommendations

**Performance Benchmarks** (`.github/workflows/performance-benchmarks.yml`):
- **Triggers**: Main/develop pushes, PRs, weekly schedule
- **Load Testing**: Locust-based stress testing (100 users, 60s duration)
- **Memory Profiling**: mprof memory usage analysis
- **Regression Detection**: Automated performance comparison
- **Artifacts**: Benchmark reports, memory profiles, load test results

### CI Requirements

**Coverage Thresholds:**
- Unit tests: ≥90% coverage required
- Integration tests: Full API endpoint coverage
- Performance tests: Regression detection within 5% tolerance

**Quality Gates:**
- All linting checks must pass
- Security scans must have no high-severity issues
- Code size limits enforced (no files >1000 lines)
- TODO/FIXME comments prohibited in production code

**Test Categories in CI:**
```bash
# Unit tests (fast, isolated)
pytest tests/unit/ -m "not integration and not performance"

# Integration tests (API, database)
pytest tests/integration/ -m "integration"

# Performance tests (benchmarking)
pytest tests/advanced/ -m "performance"

# Regression tests (production scenarios)
pytest tests/advanced/ -m "regression"
```

### Environment Setup

**Test Database:**
- PostgreSQL 15 with health checks
- Isolated test database (`portfolio_test`)
- Automated migration running
- Connection pooling and caching

**Caching Strategy:**
- pip dependencies cached by requirements hash
- pytest cache cached by commit SHA
- Test database reuse for performance

### Security and Compliance

**Automated Security Scanning:**
- **Bandit**: Python security vulnerability scanner
- **Safety**: Known dependency vulnerability checking
- **Trivy**: Container and filesystem vulnerability scanning
- **SARIF Reports**: Security findings uploaded to GitHub Security tab

**Code Quality Enforcement:**
- **Black**: Code formatting (88 character line length)
- **isort**: Import sorting with Django profile
- **flake8**: Linting with extended ignore patterns
- **mypy**: Type checking with ignore-missing-imports

### Performance Monitoring

**Benchmark Categories:**
- **Calculation Performance**: NAV, IRR, FX conversion speeds
- **Database Query Performance**: ORM query optimization
- **API Response Times**: Endpoint latency measurements
- **Memory Usage**: Profile memory-intensive operations

**Regression Detection:**
- Automated comparison with baseline performance
- Alert on >5% performance degradation
- Historical trend tracking and reporting

### Deployment Pipeline (Future)

**Current Status:** CI/CD infrastructure ready, deployment stages commented out
**Planned Stages:**
- **Staging Deployment**: Automatic on develop branch
- **Production Deployment**: Manual approval on main branch
- **Smoke Tests**: Post-deployment validation
- **Slack Notifications**: Deployment status updates

---
