.PHONY: help format lint test clean install-dev check

# Default target
help:
	@echo "Available commands:"
	@echo "  make format     - Format code with black and isort"
	@echo "  make lint       - Run flake8 linting"
	@echo "  make check      - Run all formatting and linting (like pre-commit)"
	@echo "  make test       - Run tests"
	@echo "  make clean      - Clean up cache files"
	@echo "  make install-dev - Install development dependencies"
	@echo "  make pre-commit - Run pre-commit on all files"

# Format code
format:
	@echo "Formatting code..."
	@cd backend && python -m black --line-length=88 .
	@cd backend && python -m isort --profile=django --line-length=88 .

# Lint code
lint:
	@echo "Running flake8 linting..."
	@cd backend && python -m flake8 --max-line-length=88 --max-complexity=20 --extend-ignore=E203,W503,E501,I .

# Run all checks (format, sort, lint)
check: format lint
	@echo "All checks completed!"

# Run tests
test:
	@echo "Running tests..."
	@cd backend && python manage.py test

# Clean cache files
clean:
	@echo "Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/ 2>/dev/null || true

# Install development dependencies
install-dev:
	@echo "Installing development dependencies..."
	@cd backend && pip install -r requirements.txt
	@pip install black isort flake8 flake8-docstrings flake8-bugbear pre-commit

# Run pre-commit on all files
pre-commit:
	@echo "Running pre-commit on all files..."
	@pre-commit run --all-files

# Quick check (only linting, no formatting)
quick-check:
	@echo "Running quick linting check..."
	@cd backend && python -m flake8 --max-line-length=88 --max-complexity=20 --extend-ignore=E203,W503,E501,I .

# Format specific file
format-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make format-file FILE=path/to/file.py"; \
		exit 1; \
	fi
	@echo "Formatting $(FILE)..."
	@python -m black --line-length=88 "$(FILE)"
	@python -m isort --profile=django --line-length=88 "$(FILE)"
