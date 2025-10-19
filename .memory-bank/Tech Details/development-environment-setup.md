# Development Environment Setup

This document provides comprehensive guidance for setting up a development environment that matches the pre-commit configuration and CI/CD pipeline.

## 🎯 Overview

The development environment uses three main tools:
- **Black** - Code formatter (88 character line length)
- **isort** - Import sorter (Django profile, 88 character line length)
- **Flake8** - Linter (max line length 88, ignore E203,W503,E501,I)

## ⚙️ Configuration Files

### 1. Pre-commit Configuration (`.pre-commit-config.yaml`)
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

### 2. Project Configuration (`pyproject.toml`)
```toml
[tool.black]
line-length = 88
target-version = ['py39', 'py310', 'py311']

[tool.isort]
profile = "django"
line_length = 88
multi_line_output = 3
```

### 3. Flake8 Configuration (`.flake8`)
```ini
[flake8]
max-line-length = 88
extend-ignore = E203, W503, E501, I
max-complexity = 20
```

### 4. Backend Configuration (`backend/setup.cfg`)
Contains flake8 and isort settings that match pre-commit configuration.

## 🚀 Quick Commands

### All-in-one Commands
```bash
# Run all checks (format, sort, lint)
python scripts/format_and_lint.py
make check

# Auto-fix formatting
python scripts/format_and_lint.py --fix
make format
```

### Individual Tools
```bash
# Black formatting
cd backend && python -m black --line-length=88 .

# isort import sorting
cd backend && python -m isort --profile=django --line-length=88 .

# Flake8 linting
cd backend && python -m flake8 --max-line-length=88 --extend-ignore=E203,W503,E501,I .
```

## 🔧 VS Code Integration

The `.vscode/settings.json` file configures:
- Auto-format on save with Black
- Auto-sort imports on save with isort
- Background flake8 linting
- Virtual environment interpreter

Required extensions:
- `ms-python.python`
- `ms-python.black-formatter`
- `ms-python.isort`

## 🐛 Common Issues

### 1. Flake8 Complexity Warnings (C901)
- Configuration allows `max-complexity = 20`
- Consider refactoring functions exceeding this limit
- Use `flake8 --select=C901 file.py` to check specific files

### 2. Import Order Conflicts
- isort uses Django profile
- Check with `isort --diff --check-only .`
- Force reorganization with `isort --force-single-line-imports .`

### 3. Black Formatting Issues
- Some files may fail due to encoding or multiprocessing issues
- Use `black --verbose .` to debug
- Skip problematic files with `--exclude` flag

## 🔄 Development Workflow

1. Make code changes
2. Run `make check` or `python scripts/format_and_lint.py`
3. Fix any issues manually or with `--fix` flag
4. Commit changes (pre-commit hooks should pass)

## 📋 Installation

```bash
# Install development dependencies
cd backend
./venv/Scripts/pip install black isort flake8 flake8-docstrings flake8-bugbear

# Or use Makefile
make install-dev
```

## 📊 CI/CD Integration

This configuration exactly matches GitHub Actions workflow:
- Same tool versions as pre-commit
- Same arguments and ignore rules
- Same line length and complexity settings

Code passing locally should pass in CI/CD.

## 🎉 Best Practices

1. Run `make check` before committing
2. Enable auto-format in editor
3. Review complexity warnings
4. Keep dependencies updated
5. Use Python script for comprehensive feedback

---

**Related Files:**
- `DEVELOPMENT.md` - Comprehensive development guide
- `scripts/format_and_lint.py` - Automation script
- `Makefile` - Command shortcuts
- `.vscode/settings.json` - IDE configuration
