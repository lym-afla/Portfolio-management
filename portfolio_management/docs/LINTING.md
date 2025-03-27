# Code Formatting and Linting Guide

This project uses several tools to ensure code quality and consistent formatting:

- **Black**: Code formatter that enforces a consistent style
- **isort**: Sorts imports alphabetically and automatically separates them into sections
- **Flake8**: Linter that catches logical errors and enforces PEP 8 style guide
- **mypy**: Optional static type checker
- **pre-commit**: Automatically runs checkers before each commit

## Setup

To set up the linting and formatting tools:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Set up pre-commit hooks (optional but recommended)
pre-commit install
```

Or run the setup script:

```bash
python scripts/setup_linting.py
```

## Usage

### Manual Formatting and Linting

To manually format and lint all Python files in the project:

```bash
python scripts/format_and_lint.py
```

Or run the tools individually:

```bash
# Format code with Black
black .

# Sort imports with isort
isort .

# Lint code with Flake8
flake8
```

### Automatic Formatting with Pre-commit

If you have pre-commit installed, formatting and linting will run automatically when you commit changes:

```bash
git add .
git commit -m "Your commit message"
```

If there are any linting or formatting issues, the commit will be aborted, and you'll need to fix the issues before committing.

## Configuration

The configuration for these tools is in the following files:

- **Black**: `pyproject.toml`
- **isort**: `setup.cfg` (uses the Black profile)
- **Flake8**: `setup.cfg`
- **mypy**: `setup.cfg`
- **pre-commit**: `.pre-commit-config.yaml`

## Code Style Guidelines

This project follows these code style guidelines:

1. Maximum line length: 100 characters
2. Use single quotes for strings (Black will enforce this)
3. Use 4 spaces for indentation (Django convention)
4. Add docstrings for all public modules, functions, classes, and methods
5. Follow PEP 8 style guide with a few exceptions (specified in setup.cfg)
