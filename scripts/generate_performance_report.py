#!/usr/bin/env python3
"""
Performance Report Generator

Generates detailed performance reports from benchmark results.
"""

import json
import os
import sys
from datetime import datetime


def generate_performance_report(benchmark_file, output_file):
    """Generate a detailed performance report from benchmark results.

    :param benchmark_file: The file containing the benchmark results
    :param output_file: The file to write the performance report to
    """

    with open(benchmark_file, "r") as f:
        data = json.load(f)

    report = f"""# 📊 Performance Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Machine:** {data.get('machine_info', {}).get('system', 'Unknown')}
**Python:** {data.get('machine_info', {}).get('python_implementation', 'Unknown')} {data.get('machine_info', {}).get('python_version', 'Unknown')}
**Platform:** {data.get('machine_info', {}).get('platform', 'Unknown')}

## 🎯 Executive Summary

"""

    benchmarks = data.get("benchmarks", [])

    if benchmarks:
        # Calculate statistics
        total_tests = len(benchmarks)
        avg_time = sum(b["mean"] for b in benchmarks) / total_tests
        slowest_test = max(benchmarks, key=lambda x: x["mean"])
        fastest_test = min(benchmarks, key=lambda x: x["mean"])

        report += f"""- **Total Benchmarks:** {total_tests}
- **Average Execution Time:** {avg_time:.2f}ms
- **Slowest Test:** {slowest_test['name']} ({slowest_test['mean']:.2f}ms)
- **Fastest Test:** {fastest_test['name']} ({fastest_test['mean']:.2f}ms)

"""

    report += "## 📈 Detailed Benchmark Results\n\n"
    report += (
        "| Test | Min (ms) | Mean (ms) | Max (ms) | Std Dev | Rounds | Ops/sec |\n"
    )
    report += (
        "|------|----------|-----------|----------|---------|--------|---------|\n"
    )

    # Sort by mean time (slowest first)
    sorted_benchmarks = sorted(benchmarks, key=lambda x: x["mean"], reverse=True)

    for benchmark in sorted_benchmarks:
        name = benchmark["name"]
        min_time = benchmark["min"]
        mean_time = benchmark["mean"]
        max_time = benchmark["max"]
        std_dev = benchmark.get("stddev", 0)
        rounds = benchmark["rounds"]
        ops_per_sec = 1 / (mean_time / 1000) if mean_time > 0 else 0

        report += f"| {name} | {min_time:.3f} | {mean_time:.3f} | {max_time:.3f} | {std_dev:.3f} | {rounds} | {ops_per_sec:.0f} |\n"

    report += "\n## 🔍 Performance Analysis\n\n"

    # Performance categories
    categories = {
        "Critical (< 10ms)": [],
        "Good (10-50ms)": [],
        "Acceptable (50-200ms)": [],
        "Needs Optimization (> 200ms)": [],
    }

    for benchmark in benchmarks:
        mean_time = benchmark["mean"]
        if mean_time < 10:
            categories["Critical (< 10ms)"].append(benchmark)
        elif mean_time < 50:
            categories["Good (10-50ms)"].append(benchmark)
        elif mean_time < 200:
            categories["Acceptable (50-200ms)"].append(benchmark)
        else:
            categories["Needs Optimization (> 200ms)"].append(benchmark)

    for category, tests in categories.items():
        if tests:
            report += f"### {category} ({len(tests)} tests)\n\n"
            for test in tests:
                report += f"- **{test['name']}**: {test['mean']:.2f}ms\n"
            report += "\n"

    # Recommendations
    report += "## 💡 Recommendations\n\n"

    slow_tests = [b for b in benchmarks if b["mean"] > 200]
    if slow_tests:
        report += "### 🚨 High Priority - Performance Optimization Required\n\n"
        for test in slow_tests[:5]:  # Top 5 slowest
            report += f"- **{test['name']}**: {test['mean']:.2f}ms - Consider optimizing this test\n"
        report += "\n"

    # Performance consistency analysis
    inconsistent_tests = []
    for benchmark in benchmarks:
        std_dev_percent = (benchmark.get("stddev", 0) / benchmark["mean"]) * 100
        if std_dev_percent > 20:  # High variance
            inconsistent_tests.append((benchmark, std_dev_percent))

    if inconsistent_tests:
        report += "### ⚠️ Performance Consistency Issues\n\n"
        for test, variance in sorted(
            inconsistent_tests, key=lambda x: x[1], reverse=True
        ):
            report += f"- **{test[0]['name']}**: {variance:.1f}% variance - Inconsistent performance\n"
        report += "\n"

    report += "### ✅ General Recommendations\n\n"
    report += "- Run performance tests regularly to catch regressions early\n"
    report += "- Set up automated alerts for performance degradation\n"
    report += "- Profile slow tests to identify optimization opportunities\n"
    report += "- Consider caching for frequently accessed data\n"
    report += "- Monitor database query performance\n"
    report += "- Use connection pooling for database operations\n"

    report += "\n## 📋 Test Environment Details\n\n"

    machine_info = data.get("machine_info", {})
    report += f"""- **CPU Cores:** {machine_info.get('cpu_count', 'Unknown')}
- **Memory:** {machine_info.get('mem_bytes_max', 'Unknown')} bytes
- **System:** {machine_info.get('system', 'Unknown')}
- **Release:** {machine_info.get('release', 'Unknown')}
- **Python Version:** {machine_info.get('python_version', 'Unknown')}
- **Python Implementation:** {machine_info.get('python_implementation', 'Unknown')}

"""

    # Add metadata
    metadata = data.get("metadata", {})
    report += "## 📊 Metadata\n\n"
    report += (
        f"- **Benchmark Version:** {metadata.get('benchmark_version', 'Unknown')}\n"
    )
    report += f"- **Run DateTime:** {metadata.get('datetime', 'Unknown')}\n"
    report += f"- **Pytest Version:** {metadata.get('pytest_version', 'Unknown')}\n"

    # Write report
    with open(output_file, "w") as f:
        f.write(report)

    print(f"✅ Performance report generated: {output_file}")


def main():
    """Main function to generate performance report."""
    if len(sys.argv) != 3:
        print(
            "Usage: python generate_performance_report.py <benchmark-results.json> <output-report.md>"
        )
        sys.exit(1)

    benchmark_file = sys.argv[1]
    output_file = sys.argv[2]

    if not os.path.exists(benchmark_file):
        print(f"❌ Benchmark file not found: {benchmark_file}")
        sys.exit(1)

    generate_performance_report(benchmark_file, output_file)


if __name__ == "__main__":
    main()
