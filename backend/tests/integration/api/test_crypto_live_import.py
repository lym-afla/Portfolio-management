"""Live crypto import verification — only runs when RUN_LIVE_CRYPTO_TESTS=1.

Confirms real exchange payload shapes match the documented fixtures used in
unit tests. Skipped by default.
"""
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_CRYPTO_TESTS") != "1",
        reason="set RUN_LIVE_CRYPTO_TESTS=1 to run live crypto verification",
    ),
]


@pytest.mark.django_db
def test_live_bybit_option_symbols_parse():
    # Placeholder: replaced with a real fetch once venv + keys are available.
    # Asserts that every option symbol returned by ByBit's option-execution
    # endpoint parses without ValueError.
    pytest.skip("live discovery pending restored venv")
