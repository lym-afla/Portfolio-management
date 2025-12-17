.PHONY: help test test-fast test-unit test-integration test-cov test-all clean lint format

# Default target
help:
	@echo "Available targets:"
	@echo "  test-fast     - Run unit tests only (fastest, minimal setup)"
	@echo "  test-unit     - Run unit tests with coverage"
	@echo "  test-int      - Run integration tests"
	@echo "  test-all      - Run all tests with coverage"
	@echo "  test-cov      - Run tests with full coverage report"
	@echo "  test-watch    - Run tests in watch mode"
	@echo "  lint          - Run code linting"
	@echo "  format        - Format code with black and isort"
	@echo "  clean         - Clean cache and coverage files"

# Fastest test run - unit tests only with minimal setup
test-fast:
	@echo "Running fast unit tests..."
	venv/Scripts/python.exe -m pytest -c pytest_fast.ini -m "unit and not slow" -v --tb=short

# Unit tests with coverage
test-unit:
	@echo "Running unit tests with coverage..."
	venv/Scripts/python.exe -m pytest -c pytest_unit.ini -m "unit" -v --tb=short

# Run tests using development configuration (optimized but with coverage)
test:
	@echo "Running tests with development configuration..."
	venv/Scripts/python.exe -m pytest -c pytest_dev.ini -m "not slow" -v --tb=short

# Integration tests only
test-int:
	@echo "Running integration tests..."
	venv/Scripts/python.exe -m pytest -c pytest.ini -m "integration" -v --tb=short

# Run all tests with coverage (original behavior)
test-all:
	@echo "Running all tests with coverage..."
	venv/Scripts/python.exe -m pytest -c pytest.ini -v --tb=short

# Full coverage report
test-cov:
	@echo "Running tests with full coverage report..."
	venv/Scripts/python.exe -m pytest -c pytest.ini --cov-report=html --cov-report=term -v

# Watch mode for development (requires pytest-watch)
test-watch:
	@echo "Running tests in watch mode..."
	@if venv/Scripts/pytest-watch.exe --help > /dev/null 2>&1; then \
		venv/Scripts/pytest-watch.exe -c pytest_fast.ini -m "unit and not slow"; \
	else \
		echo "pytest-watch not installed. Install with: pip install pytest-watch"; \
	fi

# Run specific test file
test-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make test-file FILE=path/to/test_file.py"; \
		exit 1; \
	fi
	@echo "Running specific test file: $(FILE)"
	venv/Scripts/python.exe -m pytest -c pytest_fast.ini $(FILE) -v --tb=short

# Run specific test function
test-func:
	@if [ -z "$(FUNC)" ]; then \
		echo "Usage: make test-func FUNC=path/to/test_file.py::TestClass::test_function"; \
		exit 1; \
	fi
	@echo "Running specific test function: $(FUNC)"
	venv/Scripts/python.exe -m pytest -c pytest_fast.ini $(FUNC) -v --tb=short -s

# Performance benchmarking
test-perf:
	@echo "Running performance benchmarks..."
	venv/Scripts/python.exe -m pytest -c pytest.ini -m "performance" --benchmark-only

# Code quality checks
lint:
	@echo "Running linting..."
	venv/Scripts/flake8.exe .
	venv/Scripts/mypy.exe . || true

# Format code
format:
	@echo "Formatting code..."
	venv/Scripts/black.exe .
	venv/Scripts/isort.exe .

# Clean cache and temporary files
clean:
	@echo "Cleaning cache and temporary files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache
	@rm -rf htmlcov
	@rm -f .coverage
	@rm -f coverage.xml

# Quick development workflow - format, lint, test
dev: format lint test-fast

# Full CI workflow - everything
ci: format lint test-all

# Performance comparison
compare-perf:
	@echo "Comparing performance between configurations..."
	@echo "Original configuration:"
	@time venv/Scripts/python.exe -m pytest -c pytest.ini tests/unit/calculations/test_gain_loss.py::TestRealizedGainLoss::test_realized_gain_simple_profit -v --no-cov --disable-warnings
	@echo "Optimized configuration:"
	@time venv/Scripts/python.exe -m pytest -c pytest_fast.ini tests/unit/calculations/test_gain_loss.py::TestRealizedGainLoss::test_realized_gain_simple_profit -v --disable-warnings
