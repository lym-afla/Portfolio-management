#!/usr/bin/env python
"""
Script to set up linting and formatting tools for the project.
Run this script from the project root directory.
"""

import subprocess
import sys
from pathlib import Path


def run_command(command, description):
    """Run a shell command and print its output."""
    print(f"\n\033[1;34m=== {description} ===\033[0m")
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        if result.stdout:
            print(result.stdout)
        print(f"\033[1;32m✓ {description} completed successfully\033[0m")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\033[1;31m✗ {description} failed\033[0m")
        print(e.stdout)
        print(e.stderr)
        return False


def main():
    # Ensure we're in the project root directory
    if not Path("manage.py").exists():
        print("Error: This script should be run from the project root directory")
        sys.exit(1)

    # Install development dependencies
    commands = [
        ("pip install -r requirements-dev.txt", "Installing development dependencies"),
        ("pre-commit install", "Setting up pre-commit hooks"),
    ]

    # Run commands
    all_success = True
    for cmd, desc in commands:
        success = run_command(cmd, desc)
        all_success = all_success and success

    if all_success:
        print("\n\033[1;32m✓ Setup completed successfully\033[0m")
        print("\nYou can now run the following commands:")
        print("  - python scripts/format_and_lint.py  # Format and lint all files")
        print("  - black .                          # Format code with Black")
        print("  - isort .                          # Sort imports")
        print("  - flake8                           # Run linting")
        print("\nPre-commit hooks are installed and will run automatically on git commit.")
        return 0
    else:
        print("\n\033[1;31m✗ Setup failed\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
