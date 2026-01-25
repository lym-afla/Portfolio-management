# Development Setup Guide

This guide explains how to set up your development environment to match the pre-commit configuration used in CI/CD.

## 🎯 Goal

Ensure your local development environment produces the same formatting and linting results as the pre-commit hooks and CI/CD pipeline.

## 🛠️ Tools Configuration

### Black (Code Formatter)
- **Line Length:** 88 characters
- **Target Version:** Python 3.9+
- **Config File:** `pyproject.toml` and `.pre-commit-config.yaml`

### isort (Import Sorter)
- **Profile:** Django
- **Line Length:** 88 characters
- **Multi-line Output:** 3
- **Config Files:** `pyproject.toml`, `backend/setup.cfg`, and `.pre-commit-config.yaml`

### Flake8 (Linter)
- **Max Line Length:** 88 characters
- **Ignored Errors:** E203, W503, E501, I
- **Max Complexity:** 20
- **Config Files:** `.flake8` and `backend/setup.cfg`

## 🚀 Quick Start

### 1. Install Development Dependencies

```bash
# Using the virtual environment
cd backend
./venv/Scripts/pip install black isort flake8 flake8-docstrings flake8-bugbear

# Or using the Makefile
make install-dev
```

### 2. Run All Checks

```bash
# Option 1: Use the Python script
python scripts/format_and_lint.py

# Option 2: Use the Makefile
make check

# Option 3: Run tools individually
make format
make lint
```

### 3. Auto-fix Formatting Issues

```bash
# Format code with black and isort
python scripts/format_and_lint.py --fix

# Or use the Makefile
make format
```

## 📋 Available Commands

### Python Script (`scripts/format_and_lint.py`)

```bash
# Run all checks (format, sort, lint)
python scripts/format_and_lint.py

# Auto-fix formatting issues
python scripts/format_and_lint.py --fix
```

### Makefile Commands

```bash
# Show all available commands
make help

# Format code with black and isort
make format

# Run flake8 linting
make lint

# Run all checks (format + lint)
make check

# Quick linting check (no formatting)
make quick-check

# Format specific file
make format-file FILE=path/to/file.py

# Run pre-commit on all files
make pre-commit

# Clean cache files
make clean

# Run tests
make test
```

### Manual Tool Usage

```bash
# Black formatting
cd backend
python -m black --line-length=88 .

# isort import sorting
python -m isort --profile=django --line-length=88 .

# Flake8 linting
python -m flake8 --max-line-length=88 --extend-ignore=E203,W503,E501,I .
```

## 🔧 VS Code Integration

The project includes VS Code settings in `.vscode/settings.json` that automatically:

- Format code on save using Black
- Sort imports on save using isort
- Run flake8 linting in the background
- Use the virtual environment interpreter

### Required VS Code Extensions

1. **Python** (Microsoft) - `ms-python.python`
2. **Black Formatter** - `ms-python.black-formatter`
3. **isort** - `ms-python.isort`

## ⚙️ Configuration Files

### Pre-commit Configuration (`.pre-commit-config.yaml`)
```yaml
- repo: https://github.com/psf/black
  rev: 23.9.1
  hooks:
    - id: black
      language_version: python3
      args: [--line-length=88]

- repo: https://github.com/pycqa/isort
  rev: 5.12.0
  hooks:
    - id: isort
      args: [--profile=django, --line-length=88]

- repo: https://github.com/pycqa/flake8
  rev: 6.1.0
  hooks:
    - id: flake8
      args:
        - --max-line-length=88
        - --extend-ignore=E203,W503,E501,I
```

### Project Configuration (`pyproject.toml`)
```toml
[tool.black]
line-length = 88
target-version = ['py39', 'py310', 'py311']

[tool.isort]
profile = "django"
line_length = 88
multi_line_output = 3
```

### Flake8 Configuration (`.flake8`)
```ini
[flake8]
max-line-length = 88
extend-ignore = E203, W503, E501, I
max-complexity = 20
```

## 🐛 Common Issues and Solutions

### 1. Black formatting fails on certain files
```bash
# Skip problematic files temporarily
black --exclude="file_with_issues.py" .

# Or run with verbose output to debug
black --verbose .
```

### 2. isort import conflicts
```bash
# Check what would be changed
isort --diff --check-only .

# Force reorganization
isort --force-single-line-imports .
```

### 3. Flake8 complexity warnings
The configuration allows `max-complexity = 20`. If you see C901 errors:

```bash
# Check specific function complexity
flake8 --select=C901 your_file.py
```

### 4. Pre-commit hooks fail
```bash
# Run hooks manually to debug
pre-commit run --all-files --verbose

# Skip hooks temporarily (not recommended)
git commit --no-verify
```

## 🔄 Pre-commit Workflow

1. **Make changes** to your code
2. **Run checks** locally: `make check` or `python scripts/format_and_lint.py`
3. **Fix any issues** manually or with `--fix` flag
4. **Commit** your changes
5. **Pre-commit hooks** will run automatically (should pass if local checks passed)

## 📊 Integration with CI/CD

This configuration matches exactly with the GitHub Actions workflow:

- **Black:** Same line length and target version
- **isort:** Same profile and line length
- **Flake8:** Same ignore rules and max line length

If your code passes locally, it should pass in CI/CD.

## 🎉 Best Practices

1. **Run `make check` before committing** to catch issues early
2. **Enable auto-format on save** in your editor
3. **Use the Python script** for comprehensive feedback
4. **Keep dependencies updated** to match pre-commit versions
5. **Review complexity warnings** and consider refactoring complex functions

## 📝 Troubleshooting

If configurations don't match:

1. Check versions: `black --version`, `isort --version`, `flake8 --version`
2. Verify config files are being read (use `--verbose` flag)
3. Check for multiple conflicting config files
4. Ensure virtual environment is activated
5. Run `make clean` to remove cached files

## 🆘 Need Help?

- Check the [Black documentation](https://black.readthedocs.io/)
- Check the [isort documentation](https://isort.readthedocs.io/)
- Check the [Flake8 documentation](https://flake8.pycqa.org/)
- Review the `.pre-commit-config.yaml` for exact CI/CD configuration
