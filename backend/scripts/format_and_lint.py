#!/usr/bin/env python
"""
Script to format and lint Python code in the project.

Run this script from the project root directory.
"""

import subprocess
import sys
from pathlib import Path


def run_command(command, description):
    """
    Run a shell command and print its output.

    Args:
        command: The command to run.
        description: The description of the command.

    Returns:
        True if the command completed successfully, False otherwise.
    """
    print(f"\n\033[1;34m=== Running {description} ===\033[0m")
    try:
        result = subprocess.run(
            command, shell=True, check=True, text=True, capture_output=True
        )
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
    """Run formatting and linting commands.

    Returns:
        int: Exit code (0 for success, 1 for failure).
    """
    # Ensure we're in the project root directory
    if not Path("manage.py").exists():
        print("Error: This script should be run from the project root directory")
        sys.exit(1)

    # Define commands for formatting and linting
    commands = [
        ("black .", "Black code formatting"),
        ("isort .", "Import sorting"),
        ("flake8", "Flake8 linting"),
    ]

    # Run each command
    all_success = True
    for cmd, desc in commands:
        success = run_command(cmd, desc)
        all_success = all_success and success

    if all_success:
        print("\n\033[1;32m✓ All formatting and linting completed successfully\033[0m")
        return 0
    else:
        print("\n\033[1;31m✗ Some formatting or linting tasks failed\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
