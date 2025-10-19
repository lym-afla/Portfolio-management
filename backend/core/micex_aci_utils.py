"""
Utility functions for fetching Accrued Coupon Interest (ACI) data from MICEX API.
Used as fallback when T-Bank API doesn't have coupon amounts for floating-rate bonds.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


def fetch_aci_from_micex(secid: str, target_date: date) -> Optional[Dict]:
    """
    Fetch ACI (Accrued Coupon Interest) from MICEX API for a specific date.

    Uses the MICEX history endpoint which provides ACCINT (accrued interest) values.
    Endpoint: https://iss.moex.com/iss/history/engines/stock/markets/bonds/boards/tqcb/securities/{secid} # noqa: E501

    Args:
        secid: MICEX security ID (e.g., "RU000A107BP5")
        target_date: The date for which to fetch ACI

    Returns:
        dict with:
            - 'aci_amount': Decimal - ACI amount in bond's nominal currency
            - 'currency': str - Currency code (e.g., 'RUB', 'USD')
            - 'date': date - The date this ACI is for
        Returns None if data not found or error occurs
    """
    if not secid:
        logger.warning("No MICEX secid provided for ACI fetch")
        return None

    try:
        # MICEX API provides historical data, so we fetch a small range around the target date
        from_date = target_date - timedelta(days=7)
        to_date = target_date

        url = (
            f"https://iss.moex.com/iss/history/engines/stock/markets/bonds/"
            f"boards/tqcb/securities/{secid}.json"
        )

        params = {
            "from": from_date.strftime("%Y-%m-%d"),
            "till": to_date.strftime("%Y-%m-%d"),
        }

        logger.debug(f"Fetching ACI from MICEX for {secid} on {target_date}: {url}")

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        # MICEX API structure: data['history']['data'] contains rows
        # data['history']['columns'] contains column names
        if "history" not in data or "data" not in data["history"]:
            logger.warning(f"No history data in MICEX response for {secid}")
            return None

        columns = data["history"]["columns"]
        rows = data["history"]["data"]

        if not rows:
            logger.warning(f"No data rows in MICEX response for {secid} on {target_date}")
            return None

        # Find column indices
        try:
            tradedate_idx = columns.index("TRADEDATE")
            accint_idx = columns.index("ACCINT")
            currency_idx = columns.index("CURRENCYID")
        except ValueError as e:
            logger.error(f"Required column not found in MICEX response: {e}")
            logger.debug(f"Available columns: {columns}")
            return None

        # Find the row closest to target_date (preferably exact match)
        target_date_str = target_date.strftime("%Y-%m-%d")
        matching_row = None

        # First, try to find exact date match
        for row in rows:
            if row[tradedate_idx] == target_date_str:
                matching_row = row
                break

        # If no exact match, use the most recent date before target_date
        if not matching_row:
            for row in reversed(rows):  # Rows are usually chronological
                row_date_str = row[tradedate_idx]
                if row_date_str <= target_date_str:
                    matching_row = row
                    break

        if not matching_row:
            logger.warning(f"No suitable data row found for {secid} on or before {target_date}")
            return None

        aci_value = matching_row[accint_idx]
        currency = matching_row[currency_idx]
        actual_date = matching_row[tradedate_idx]

        if aci_value is None:
            logger.warning(f"ACI value is None for {secid} on {actual_date}")
            return None

        # Convert to Decimal
        try:
            aci_amount = Decimal(str(aci_value))
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert ACI value to Decimal: {aci_value}, error: {e}")
            return None

        # Convert currency code if needed (MICEX uses 'SUR' for RUB)
        if currency == "SUR":
            currency = "RUB"

        logger.info(
            f"Successfully fetched ACI from MICEX for {secid}: "
            f"{aci_amount} {currency} on {actual_date}"
        )

        return {
            "aci_amount": aci_amount,
            "currency": currency,
            "date": actual_date,
        }

    except requests.RequestException as e:
        logger.error(f"MICEX API request failed for {secid}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching ACI from MICEX for {secid}: {e}", exc_info=True)
        return None
