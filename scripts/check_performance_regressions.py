#!/usr/bin/env python3
"""
Performance Regression Checker

Checks benchmark results against previous baselines to detect performance regressions.
"""

import json
import os
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

PERFORMANCE_THRESHOLDS = {
    "small_portfolio_calculation": {"max_mean_ms": 50, "max_regression_percent": 20},
    "medium_portfolio_calculation": {"max_mean_ms": 200, "max_regression_percent": 15},
    "large_portfolio_calculation": {"max_mean_ms": 1000, "max_regression_percent": 25},
    "fx_rate_lookup": {"max_mean_ms": 1, "max_regression_percent": 30},
    "api_endpoint_response": {"max_mean_ms": 100, "max_regression_percent": 20},
    "database_query": {"max_mean_ms": 50, "max_regression_percent": 25},
}


def load_baseline_data():
    """Load baseline performance data from previous runs."""
    baseline_file = (
        Path(__file__).parent.parent
        / "tests"
        / "fixtures"
        / "performance_baseline.json"
    )

    if baseline_file.exists():
        with open(baseline_file, "r") as f:
            return json.load(f)
    return {}


def save_baseline_data(benchmark_results):
    """Save current benchmark results as new baseline."""
    baseline_file = (
        Path(__file__).parent.parent
        / "tests"
        / "fixtures"
        / "performance_baseline.json"
    )
    baseline_file.parent.mkdir(parents=True, exist_ok=True)

    # Extract relevant data for baseline
    baseline_data = {}
    for benchmark in benchmark_results.get("benchmarks", []):
        name = benchmark["name"]
        baseline_data[name] = {
            "mean": benchmark["mean"],
            "min": benchmark["min"],
            "max": benchmark["max"],
            "rounds": benchmark["rounds"],
            "timestamp": benchmark_results.get("metadata", {}).get(
                "datetime", "unknown"
            ),
        }

    with open(baseline_file, "w") as f:
        json.dump(baseline_data, f, indent=2)

    print(f"✅ Performance baseline updated: {baseline_file}")


def check_performance_regressions(benchmark_file):
    """Check for performance regressions in benchmark results."""

    with open(benchmark_file, "r") as f:
        current_results = json.load(f)

    baseline_data = load_baseline_data()
    regressions = []
    improvements = []

    for benchmark in current_results.get("benchmarks", []):
        name = benchmark["name"]
        current_mean = benchmark["mean"]

        # Find matching baseline
        baseline_entry = None
        for baseline_name, baseline_metrics in baseline_data.items():
            if (
                name.lower() in baseline_name.lower()
                or baseline_name.lower() in name.lower()
            ):
                baseline_entry = baseline_metrics
                break

        if baseline_entry:
            baseline_mean = baseline_entry["mean"]

            # Calculate percentage change
            if baseline_mean > 0:
                change_percent = ((current_mean - baseline_mean) / baseline_mean) * 100

                # Check against thresholds
                threshold_key = None
                for key in PERFORMANCE_THRESHOLDS:
                    if key.lower() in name.lower():
                        threshold_key = key
                        break

                if threshold_key:
                    threshold = PERFORMANCE_THRESHOLDS[threshold_key]

                    # Check absolute threshold
                    if current_mean > threshold["max_mean_ms"]:
                        regressions.append(
                            {
                                "name": name,
                                "type": "absolute_threshold",
                                "current_ms": current_mean,
                                "threshold_ms": threshold["max_mean_ms"],
                                "excess_percent": (
                                    (current_mean - threshold["max_mean_ms"])
                                    / threshold["max_mean_ms"]
                                )
                                * 100,
                            }
                        )

                    # Check regression threshold
                    if change_percent > threshold["max_regression_percent"]:
                        regressions.append(
                            {
                                "name": name,
                                "type": "regression",
                                "current_ms": current_mean,
                                "baseline_ms": baseline_mean,
                                "change_percent": change_percent,
                                "threshold_percent": threshold[
                                    "max_regression_percent"
                                ],
                            }
                        )
                    elif change_percent < -threshold["max_regression_percent"]:
                        improvements.append(
                            {
                                "name": name,
                                "current_ms": current_mean,
                                "baseline_ms": baseline_mean,
                                "improvement_percent": abs(change_percent),
                            }
                        )

    # Print results
    print("📊 Performance Regression Analysis")
    print("=" * 50)

    if regressions:
        print(f"❌ {len(regressions)} Performance Regressions Detected:")
        for regression in regressions:
            if regression["type"] == "absolute_threshold":
                print(f"  • {regression['name']}")
                print(f"    Current: {regression['current_ms']:.2f}ms")
                print(f"    Threshold: {regression['threshold_ms']:.2f}ms")
                print(f"    Exceeds by: {regression['excess_percent']:.1f}%")
            else:
                print(f"  • {regression['name']}")
                print(f"    Current: {regression['current_ms']:.2f}ms")
                print(f"    Baseline: {regression['baseline_ms']:.2f}ms")
                print(f"    Regression: +{regression['change_percent']:.1f}%")
                print(f"    Threshold: {regression['threshold_percent']:.1f}%")
            print()
    else:
        print("✅ No performance regressions detected!")

    if improvements:
        print(f"🚀 {len(improvements)} Performance Improvements:")
        for improvement in improvements:
            print(f"  • {improvement['name']}")
            print(f"    Current: {improvement['current_ms']:.2f}ms")
            print(f"    Baseline: {improvement['baseline_ms']:.2f}ms")
            print(f"    Improvement: -{improvement['improvement_percent']:.1f}%")
            print()

    # Return exit code based on regressions
    if regressions:
        print(
            "⚠️  Performance regressions detected. Consider optimization before merging."
        )
        return 1
    else:
        print("✅ All performance checks passed!")
        return 0


def main():
    """Main function to check performance regressions."""
    if len(sys.argv) != 2:
        print("Usage: python check_performance_regressions.py <benchmark-results.json>")
        sys.exit(1)

    benchmark_file = sys.argv[1]

    if not os.path.exists(benchmark_file):
        print(f"❌ Benchmark file not found: {benchmark_file}")
        sys.exit(1)

    # Check for regressions
    exit_code = check_performance_regressions(benchmark_file)

    # Update baseline if this is the main branch
    if os.environ.get("GITHUB_REF") == "refs/heads/main" and exit_code == 0:
        with open(benchmark_file, "r") as f:
            results = json.load(f)
        save_baseline_data(results)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
