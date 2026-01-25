#!/usr/bin/env python3
"""
Complexity analysis script to help identify and prioritize C901 complexity errors.
This script categorizes functions by complexity level and provides refactoring guidance.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def get_flake8_complexity_report() -> List[Tuple[str, int, int, str]]:
    """Get flake8 complexity report for C901 errors."""
    try:
        # Use the virtual environment's flake8
        project_root = Path(__file__).parent
        venv_python = project_root / "backend" / "venv" / "Scripts" / "python.exe"

        result = subprocess.run(
            [
                str(venv_python),
                "-m",
                "flake8",
                "--select=C901",
                "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
                "backend/",
            ],
            capture_output=True,
            text=True,
            cwd=project_root,
        )

        complexity_errors = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split(":")
                if len(parts) >= 4:
                    file_path = parts[0]
                    line_num = int(parts[1])
                    col_num = int(parts[2])
                    error_text = ":".join(parts[3:])

                    # Extract complexity number from error text
                    import re

                    complexity_match = re.search(
                        r"is too complex \((\d+)\)", error_text
                    )
                    if complexity_match:
                        complexity = int(complexity_match.group(1))
                        func_name = (
                            error_text.split("'")[1] if "'" in error_text else "unknown"
                        )
                        complexity_errors.append(
                            (file_path, line_num, complexity, func_name)
                        )

        return sorted(complexity_errors, key=lambda x: x[2], reverse=True)

    except Exception as e:
        print(f"Error running flake8: {e}")
        return []


def categorize_complexity(errors: List[Tuple[str, int, int, str]]) -> Dict[str, List]:
    """Categorize complexity errors by severity."""
    categories = {
        "critical": [],  # 50+
        "high": [],  # 30-49
        "medium": [],  # 20-29
        "low": [],  # 15-19 (if we lower threshold)
    }

    for file_path, line_num, complexity, func_name in errors:
        item = (file_path, line_num, complexity, func_name)
        if complexity >= 50:
            categories["critical"].append(item)
        elif complexity >= 30:
            categories["high"].append(item)
        elif complexity >= 20:
            categories["medium"].append(item)
        else:
            categories["low"].append(item)

    return categories


def generate_refactoring_plan(categories: Dict[str, List]) -> str:
    """Generate a prioritized refactoring plan."""
    plan = ["# Complexity Refactoring Plan\n"]

    total_functions = sum(len(funcs) for funcs in categories.values())
    plan.append(f"Found {total_functions} functions exceeding complexity threshold.\n")

    for category, items in categories.items():
        if not items:
            continue

        if category == "critical":
            plan.append("## CRITICAL (Complexity 50+) - Immediate Action Required")
            priority = "Break down immediately - these are unmanageable"
        elif category == "high":
            plan.append("## HIGH PRIORITY (Complexity 30-49)")
            priority = "Plan refactoring in next sprint"
        elif category == "medium":
            plan.append("## MEDIUM PRIORITY (Complexity 20-29)")
            priority = "Schedule for refactoring when time permits"
        else:
            plan.append("## LOW PRIORITY (Complexity 15-19)")
            priority = "Consider for future cleanup"

        plan.append(f"*{priority}*\n")

        for file_path, line_num, complexity, func_name in items:
            plan.append(f"- **{func_name}** ({complexity}) - `{file_path}:{line_num}`")

        plan.append("")

    return "\n".join(plan)


def suggest_refactoring_strategies() -> str:
    """Provide specific refactoring strategies."""
    strategies = """
## Refactoring Strategies

### 1. Extract Method Pattern
Break large functions into smaller, focused functions:

```python
# Before (complex)
def complex_function(data):
    # validation logic
    # processing logic
    # formatting logic
    # save logic

# After (refactored)
def complex_function(data):
    validated_data = validate_input(data)
    processed_data = process_data(validated_data)
    formatted_data = format_output(processed_data)
    return save_result(formatted_data)

def validate_input(data):
    # validation logic only

def process_data(data):
    # processing logic only
```

### 2. Strategy Pattern
For complex conditional logic:

```python
# Before
def process_transaction(transaction):
    if transaction.type == "buy":
        # complex buy logic
    elif transaction.type == "sell":
        # complex sell logic
    elif transaction.type == "fx":
        # complex fx logic

# After
class TransactionProcessor:
    def __init__(self):
        self.strategies = {
            "buy": BuyStrategy(),
            "sell": SellStrategy(),
            "fx": FXStrategy()
        }

    def process(self, transaction):
        strategy = self.strategies[transaction.type]
        return strategy.process(transaction)
```

### 3. Builder Pattern
For complex object construction:

```python
# Before
def create_complex_object(param1, param2, param3, param4, param5):
    # complex construction logic

# After
class ComplexObjectBuilder:
    def __init__(self):
        self.obj = ComplexObject()

    def with_param1(self, value):
        self.obj.param1 = value
        return self

    def build(self):
        return self.obj

# Usage
obj = (ComplexObjectBuilder()
       .with_param1(value1)
       .with_param2(value2)
       .build())
```

### 4. Data Class/NamedTuple
For complex data passing:

```python
# Before
def process_data(data1, data2, data3, data4, data5):
    # complex processing

# After
from dataclasses import dataclass

@dataclass
class ProcessingData:
    data1: str
    data2: int
    data3: float
    data4: bool
    data5: str

def process_data(data: ProcessingData):
    # cleaner processing with data.data1, etc.
```

### 5. Early Returns
For nested conditions:

```python
# Before
def process_request(request):
    if request.user:
        if request.user.is_active:
            if request.has_permission:
                # main logic
                return result
            else:
                return "No permission"
        else:
            return "User inactive"
    else:
        return "No user"

# After
def process_request(request):
    if not request.user:
        return "No user"

    if not request.user.is_active:
        return "User inactive"

    if not request.has_permission:
        return "No permission"

    # main logic
    return result
```
"""
    return strategies


def main():
    """Main function to analyze complexity."""
    print("Analyzing code complexity...")

    # Get complexity errors
    complexity_errors = get_flake8_complexity_report()

    if not complexity_errors:
        print("No complexity issues found!")
        return 0

    # Categorize by severity
    categories = categorize_complexity(complexity_errors)

    # Generate report
    refactoring_plan = generate_refactoring_plan(categories)
    strategies = suggest_refactoring_strategies()

    # Output report
    print(refactoring_plan)
    print(strategies)

    # Save to file
    report_path = Path(__file__).parent / "complexity_report.md"
    with open(report_path, "w") as f:
        f.write(refactoring_plan + strategies)

    print(f"\nDetailed report saved to: {report_path}")
    print("\nNext steps:")
    print("1. Start with CRITICAL complexity functions (50+)")
    print("2. Apply appropriate refactoring strategies")
    print("3. Run tests after each refactoring")
    print("4. Update documentation if needed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
