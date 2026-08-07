"""Tests for constants module."""
from constants import ASSET_TYPE_CRYPTO, ASSET_TYPE_OPTION


def test_asset_type_constants():
    assert ASSET_TYPE_CRYPTO == "Crypto"
    assert ASSET_TYPE_OPTION == "Option"
