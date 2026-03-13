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
	cd backend && ../backend/venv/Scripts/black.exe --line-length=88 .
	cd backend && ../backend/venv/Scripts/isort.exe --profile=django --line-length=88 .

# Lint code
lint:
	@echo "Running flake8 linting..."
	cd backend && ../backend/venv/Scripts/flake8.exe --max-line-length=88 --max-complexity=20 --extend-ignore=E203,W503,E501,I .

# Run all checks (format, sort, lint)
check: format lint
	@echo "All checks completed!"

# Run tests
test:
	@echo "Running tests..."
	cd backend && ../backend/venv/Scripts/python.exe manage.py test

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
	cd backend && ../backend/venv/Scripts/pip.exe install -r requirements.txt
	../backend/venv/Scripts/pip.exe install black isort flake8 flake8-docstrings flake8-bugbear pre-commit

# Run pre-commit on all files
pre-commit:
	@echo "Running pre-commit on all files..."
	../backend/venv/Scripts/pre-commit.exe run --all-files

# Quick check (only linting, no formatting)
quick-check:
	@echo "Running quick linting check..."
	cd backend && ../backend/venv/Scripts/flake8.exe --max-line-length=88 --max-complexity=20 --extend-ignore=E203,W503,E501,I .

# Format specific file
format-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make format-file FILE=path/to/file.py"; \
		exit 1; \
	fi
	@echo "Formatting $(FILE)..."
	../backend/venv/Scripts/black.exe --line-length=88 "$(FILE)"
	../backend/venv/Scripts/isort.exe --profile=django --line-length=88 "$(FILE)"
