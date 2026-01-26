.PHONY: help format lint check test test-fast test-unit test-int test-all test-cov test-watch test-file test-func test-perf clean install-dev pre-commit dev ci

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "  Code Quality:"
	@echo "    make format       - Format code with black and isort"
	@echo "    make lint         - Run flake8 and mypy linting"
	@echo "    make check        - Run formatting then linting"
	@echo "    make pre-commit   - Run pre-commit on all files"
	@echo ""
	@echo "  Testing:"
	@echo "    make test         - Run tests with dev config (no slow tests)"
	@echo "    make test-fast    - Run unit tests only (fastest)"
	@echo "    make test-unit    - Run unit tests with coverage"
	@echo "    make test-int     - Run integration tests"
	@echo "    make test-all     - Run all tests with coverage"
	@echo "    make test-cov     - Run tests with full coverage report"
	@echo "    make test-watch   - Run tests in watch mode"
	@echo "    make test-perf    - Run performance benchmarks"
	@echo "    make test-file FILE=path/to/test.py"
	@echo "    make test-func FUNC=path/to/test.py::TestClass::test_func"
	@echo ""
	@echo "  Workflows:"
	@echo "    make dev          - Format, lint, then fast tests"
	@echo "    make ci           - Format, lint, then all tests"
	@echo ""
	@echo "  Setup:"
	@echo "    make install-dev  - Install development dependencies"
	@echo "    make clean        - Clean cache and coverage files"

# ============================================================================
# Code Quality
# ============================================================================

format:
	@echo "Formatting code..."
	python -m black --line-length=88 .
	python -m isort --profile=django --line-length=88 .

lint:
	@echo "Running linting..."
	python -m flake8 --max-line-length=88 --max-complexity=50 --extend-ignore=E203,W503,E501,I --docstring-convention=google .
	-python -m mypy .

check: format lint
	@echo "All checks completed!"

pre-commit:
	@echo "Running pre-commit on all files..."
	cd .. && pre-commit run --all-files

# ============================================================================
# Testing
# ============================================================================

test:
	@echo "Running tests with development configuration..."
	python -m pytest -c pytest_dev.ini -m "not slow" -v --tb=short

test-fast:
	@echo "Running fast unit tests..."
	python -m pytest -c pytest_fast.ini -m "unit and not slow" -v --tb=short

test-unit:
	@echo "Running unit tests with coverage..."
	python -m pytest -c pytest_unit.ini -m "unit" -v --tb=short

test-int:
	@echo "Running integration tests..."
	python -m pytest -c pytest.ini -m "integration" -v --tb=short

test-all:
	@echo "Running all tests with coverage..."
	python -m pytest -c pytest.ini -v --tb=short

test-cov:
	@echo "Running tests with full coverage report..."
	python -m pytest -c pytest.ini --cov-report=html --cov-report=term -v

test-watch:
	@echo "Running tests in watch mode..."
	python -m pytest_watch -c pytest_fast.ini -m "unit and not slow"

test-file:
ifndef FILE
	@echo "Usage: make test-file FILE=path/to/test_file.py"
else
	@echo "Running specific test file: $(FILE)"
	python -m pytest -c pytest_fast.ini $(FILE) -v --tb=short
endif

test-func:
ifndef FUNC
	@echo "Usage: make test-func FUNC=path/to/test_file.py::TestClass::test_function"
else
	@echo "Running specific test function: $(FUNC)"
	python -m pytest -c pytest_fast.ini $(FUNC) -v --tb=short -s
endif

test-perf:
	@echo "Running performance benchmarks..."
	python -m pytest -c pytest.ini -m "performance" --benchmark-only

# ============================================================================
# Workflows
# ============================================================================

dev: format lint test-fast

ci: format lint test-all

# ============================================================================
# Setup & Maintenance
# ============================================================================

install-dev:
	@echo "Installing development dependencies..."
	pip install -r requirements-dev.txt

clean:
	@echo "Cleaning cache and coverage files..."
	-rd /s /q __pycache__ 2>nul
	-rd /s /q .pytest_cache 2>nul
	-rd /s /q htmlcov 2>nul
	-del /q .coverage coverage.xml 2>nul
