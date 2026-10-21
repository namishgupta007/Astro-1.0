"""Unit tests executing the controlled graph-accuracy benchmark suite."""

from __future__ import annotations

import unittest

from tests.benchmark_fixtures import (
    evaluate_fixture,
    get_js_ts_fixtures,
    get_python_fixtures,
)


class TestGraphAccuracyBenchmark(unittest.TestCase):
    """Executes all controlled synthetic fixtures and asserts accuracy constraints."""

    pass


def _create_test_method(case):
    def test_method(self):
        res = evaluate_fixture(case)
        if not res.passed:
            self.fail(
                f"Benchmark case '{case.name}' failed:\n"
                f"  Notes: {res.notes}\n"
                f"  Forbidden violations: {res.forbidden_call_violations}\n"
                f"  Predicted calls: {res.predicted_calls} (expected: {res.expected_calls})\n"
                f"  Predicted imports: {res.predicted_imports} (expected: {res.expected_imports})"
            )
    return test_method


for case in get_python_fixtures():
    setattr(
        TestGraphAccuracyBenchmark,
        f"test_{case.name}",
        _create_test_method(case),
    )

for case in get_js_ts_fixtures():
    setattr(
        TestGraphAccuracyBenchmark,
        f"test_{case.name}",
        _create_test_method(case),
    )


if __name__ == "__main__":
    unittest.main()
