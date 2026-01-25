#!/usr/bin/env python3
"""
Development script to run linting and formatting tools with the same configuration as pre-commit hooks.
This ensures your local development matches the CI/CD pipeline exactly.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle the result."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        print(f"✅ {description} - PASSED")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def main():
    """Main function to run all linting and formatting tools."""
    project_root = Path(__file__).parent
    backend_dir = project_root / "backend"

    print("🔧 Running development linting and formatting tools...")
    print(f"Project root: {project_root}")

    # Configuration matching pre-commit hooks
    black_cmd = [sys.executable, "-m", "black", "--line-length=88", str(backend_dir)]

    isort_cmd = [
        sys.executable,
        "-m",
        "isort",
        "--profile=django",
        "--line-length=88",
        str(backend_dir),
    ]

    flake8_cmd = [
        sys.executable,
        "-m",
        "flake8",
        "--max-line-length=88",
        "--extend-ignore=E203,W503,E501,I",
        str(backend_dir),
    ]

    # Track results
    results = {}

    # Run tools in order: format -> import sort -> lint
    results["black"] = run_command(black_cmd, "Black code formatting")
    results["isort"] = run_command(isort_cmd, "isort import sorting")
    results["flake8"] = run_command(flake8_cmd, "Flake8 linting")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    all_passed = True
    for tool, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{tool:10} : {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n🎉 All tools passed! Your code is ready to commit.")
        return 0
    else:
        print("\n⚠️  Some tools failed. Please fix the issues before committing.")
        print(
            "💡 Tip: Run 'python scripts/format_and_lint.py --fix' to auto-fix some issues."
        )
        return 1


def fix_mode():
    """Run tools in fix mode where applicable."""
    project_root = Path(__file__).parent
    backend_dir = project_root / "backend"

    print("🔧 Running code formatting and import sorting in fix mode...")

    # Black with fix (default behavior)
    black_cmd = [sys.executable, "-m", "black", "--line-length=88", str(backend_dir)]

    # isort with fix (default behavior)
    isort_cmd = [
        sys.executable,
        "-m",
        "isort",
        "--profile=django",
        "--line-length=88",
        str(backend_dir),
    ]

    run_command(black_cmd, "Black code formatting (fix)")
    run_command(isort_cmd, "isort import sorting (fix)")

    print("\n✅ Code formatting and import sorting completed!")
    print("🔍 Run flake8 to check for remaining linting issues.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fix":
        fix_mode()
    else:
        sys.exit(main())
