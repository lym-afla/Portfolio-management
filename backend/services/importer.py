"""Broker import pipeline service.

Consolidates the former ``core/import_utils.py`` (Excel parsing, broker
parsers, security creators, price importers, account matching) and
``core/tinkoff_utils.py`` (Tinkoff/T-Bank API integration, operation-to-
transaction mapping, bond coupon/redemption handling) into a single module.

Merging the two files eliminates the circular import that existed between
them (each imported from the other). All former cross-module references are
now plain local function calls.

Public surface (preserved verbatim from the originals):
- Excel parsing: ``read_excel_file``, ``_process_transaction_row``,
  ``generate_dates_for_price_import``
- Charles Stanley parser: ``parse_charles_stanley_transactions``
- Galaxy parsers: ``parse_galaxy_account_security_transactions``,
  ``parse_galaxy_account_cash_flows``, ``_process_galaxy_securities``,
  ``_process_galaxy_transaction``
- Security creators: ``create_security_from_micex``,
  ``create_security_from_tinkoff``, ``_create_basic_tbank_asset``,
  ``_enhance_bond_metadata_from_tbank``, ``fetch_security_from_micex_targeted``
- Price importers: ``import_security_prices_from_ft``,
  ``import_security_prices_from_yahoo``, ``import_security_prices_from_micex``,
  ``import_security_prices_from_tbank``
- Account matching: ``match_tinkoff_broker_account``, ``check_broker_token_active``
- Shared helpers: ``get_investor``, ``get_broker``, ``get_account``,
  ``get_security``, ``transaction_exists``, ``fx_transaction_exists``,
  ``_find_security``
- Tinkoff/T-Bank: ``map_tinkoff_operation_to_transaction``,
  ``create_transaction_from_tinkoff``, ``fetch_and_cache_bond_coupon_schedule``,
  ``get_price_from_tbank``, ``save_bond_redemption_history``,
  ``get_security_by_uid``, ``get_bond_notional_at_date``,
  ``get_bond_initial_notional``, ``_find_or_create_security``,
  ``get_instrument_uid``, ``get_user_token``, ``verify_token_access``,
  ``get_account_info``

Async signatures are preserved: Tinkoff helpers use
``database_sync_to_async`` throughout.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Dict, List, Tuple

import aiohttp
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from channels.db import database_sync_to_async
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import Q
from fake_useragent import UserAgent
from fuzzywuzzy import process
from t_tech.invest import CandleInterval, Client, InstrumentType, OperationType
from t_tech.invest.exceptions import RequestError
from t_tech.invest.schemas import EventType, GetBondEventsRequest
from t_tech.invest.utils import quotation_to_decimal

from common.models import (
    Accounts,
    Assets,
    BondCouponSchedule,
    BondMetadata,
    Brokers,
    FutureMetadata,
    OptionMetadata,
    Prices,
    Transactions,
)
from services.asset_resolver import resolve_or_create_asset
from constants import (
    ASSET_TYPE_CHOICES,
    EXPOSURE_CHOICES,
    MUTUAL_FUNDS_IN_PENCES,
    TRANSACTION_TYPE_ASSET_TRANSFER,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_REPO,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)
from services.pricing import get_cumulative_split_factor
from users.models import TinkoffApiToken

# ``services.broker_api`` imports names from this module at its top level
# (``get_user_token`` etc.), so importing it eagerly here would create a
# circular import. ``get_broker_api`` is only used inside async functions
# below, so a deferred import is both safe and cycle-free.
def _get_broker_api():
    from services.broker_api import get_broker_api

    return get_broker_api

logger = logging.getLogger(__name__)

# Bounded executor for blocking I/O calls (yfinance, requests, etc.)
# Prevents unbounded thread creation when multiple price imports run concurrently.
_blocking_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="blocking-io")

CustomUser = get_user_model()


# =============================================================================
# Shared async DB helpers (formerly in core/import_utils.py)
# =============================================================================


@database_sync_to_async
def get_investor(investor_id):
    """Retrieve investor/user by ID.

    Args:
        investor_id: The ID of the investor to retrieve.

    Returns:
        CustomUser: The user instance.
    """
    return CustomUser.objects.get(id=investor_id)


@database_sync_to_async
def get_broker(account):
    """Get broker from account asynchronously."""
    return account.broker


@database_sync_to_async
def get_account(account_id: int) -> Accounts:
    """Retrieve an account by ID.

    Args:
        account_id: The ID of the account to retrieve.

    Returns:
        Accounts: The account instance.

    Raises:
        Accounts.DoesNotExist: If account doesn't exist.
    """
    return Accounts.objects.select_related("broker").get(id=account_id)


@database_sync_to_async
def get_security(security_id):
    """Retrieve a security/asset by ID.

    Args:
        security_id: The ID of the security to retrieve.

    Returns:
        Assets: The security instance, or None if not found.
    """
    try:
        return Assets.objects.get(id=security_id)
    except Assets.DoesNotExist:
        logger.error(f"Security with id {security_id} does not exist")
        return None


@database_sync_to_async
def transaction_exists(transaction_data):
    """Check if a transaction already exists in the database.

    Args:
        transaction_data: Dictionary containing transaction field values.

    Returns:
        bool: True if transaction exists, False otherwise.

    Raises:
        ValueError: If required fields are missing.
    """
    query = Q()
    required_fields = ["investor", "account", "date", "currency", "type"]
    optional_fields = [
        "security",
        "quantity",
        "price",
        "cash_flow",
        "commission",
        "aci",
    ]

    # Add required fields to the query
    for field in required_fields:
        if field not in transaction_data:
            raise ValueError(f"Required field '{field}' is missing from transaction_data")
        query &= Q(**{field: transaction_data[field]})

    # Add optional fields to the query if they exist
    for field in optional_fields:
        if field in transaction_data and transaction_data[field] is not None:
            query &= Q(**{field: transaction_data[field]})

    exists = Transactions.objects.filter(query).exists()

    return exists


@database_sync_to_async
def fx_transaction_exists(transaction_data):
    """Check if an FX transaction already exists."""
    from common.models import FXTransaction

    query = Q()
    required_fields = [
        "investor",
        "account",
        "date",
        "from_currency",
        "to_currency",
        "exchange_rate",
    ]
    optional_fields = ["from_amount", "to_amount", "commission", "commission_currency"]

    # Create a copy to avoid modifying the original
    data_copy = transaction_data.copy()

    # Get decimal_places from the model field dynamically
    exchange_rate_field = FXTransaction._meta.get_field("exchange_rate")
    decimal_places = exchange_rate_field.decimal_places

    # Round exchange_rate to match database precision
    if "exchange_rate" in data_copy and data_copy["exchange_rate"] is not None:
        data_copy["exchange_rate"] = round(Decimal(str(data_copy["exchange_rate"])), decimal_places)

    # Add required fields to the query
    for field in required_fields:
        if field not in data_copy:
            raise ValueError(f"Required field '{field}' is missing from FX transaction_data")
        query &= Q(**{field: data_copy[field]})

    # Add optional fields to the query if they exist
    for field in optional_fields:
        if field in data_copy and data_copy[field] is not None:
            query &= Q(**{field: data_copy[field]})

    return FXTransaction.objects.filter(query).exists()


# =============================================================================
# Excel parsing & Charles Stanley parser (formerly in core/import_utils.py)
# =============================================================================


def read_excel_file(file_path):
    """Read an Excel file and extract transaction data.

    Args:
        file_path: Path to the Excel file to read.

    Returns:
        DataFrame: Pandas DataFrame containing the transaction data.

    Raises:
        Exception: If file reading fails.
    """
    try:
        with default_storage.open(file_path, "rb") as file:
            df = pd.read_excel(
                file,
                header=3,
                usecols=[
                    "Date",
                    "Description",
                    "Stock Description",
                    "Price",
                    "Debit",
                    "Credit",
                ],
            )
        return df
    except pd.errors.EmptyDataError:
        raise ValueError("The uploaded file is empty or could not be read.")
    except Exception as e:
        raise ValueError(f"An error occurred while reading the file: {str(e)}")


@database_sync_to_async
def _find_security(security_description, investor):
    securities = list(Assets.objects.filter(investors=investor))

    # Check for exact match
    security = next((s for s in securities if s.name == security_description), None)

    # If no exact match, look for best match
    security_names = [security.name for security in securities]
    best_match = process.extractOne(security_description, security_names)

    if best_match:
        match_name, match_score = best_match
        if match_score == 100:  # Perfect match found
            security = next(s for s in securities if s.name == match_name)
            return security, None
        else:  # Close match found, but not perfect
            match_id = next(s.id for s in securities if s.name == match_name)
            return None, {
                "match_name": match_name,
                "match_score": match_score,
                "match_id": match_id,
            }

    # No match found
    return None, None


async def _process_transaction_row(row, investor, account, currency):
    quantity_decimal_places = Transactions._meta.get_field("quantity").decimal_places
    price_decimal_places = Transactions._meta.get_field("price").decimal_places

    try:
        if pd.isna(row["Date"]):
            return None, "skipped"

        # Keep as datetime to preserve time information
        transaction_date = pd.to_datetime(row["Date"], errors="coerce")
        # If no time component, set to midnight
        if (
            pd.isna(transaction_date.time())
            or transaction_date.time() == pd.Timestamp("00:00:00").time()
        ):
            transaction_date = transaction_date.replace(hour=0, minute=0, second=0, microsecond=0)
        description = row["Description"]
        security_description = row["Stock Description"]
        price = Decimal(str(row["Price"])) if not pd.isna(row["Price"]) else None
        debit = Decimal(str(row["Debit"])) if not pd.isna(row["Debit"]) else Decimal("0")
        credit = Decimal(str(row["Credit"])) if not pd.isna(row["Credit"]) else Decimal("0")

        SKIP_DESCRIPTIONS = {"* BALANCE B/F *", "Cash Transfers ISA"}
        COMMISSION_DESCRIPTIONS = {
            "Funds Platform Fee",
            "Govt Flat Rate Int Charge",
            "Platform Charge",
            "Stocks & Shares Custody Fee",
            "Stocks & Shares Platform Fee",
        }
        CASH_IN_DESCRIPTIONS = {
            "Stocks & Shares Subs",
            "ISA Subscription",
            "Sage Pay Debit Card",
            "DIRECT CREDIT",
            "WIRED",
        }
        CASH_OUT_DESCRIPTIONS = {"BACS P'MNT"}
        # Try to use regex for the below two. Relevant for Gross interest and Tax Credit
        INTEREST_INCOME_DESCRIPTIONS = {"Gross interest"}
        DIVIDEND_DESCRIPTIONS = {
            "Dividend",
            "Equalisation",
            "Tax Credit",
            "Tax Credit*",
        }

        if description in SKIP_DESCRIPTIONS:
            return None, "skipped"

        security, best_match = None, None

        if description in COMMISSION_DESCRIPTIONS:
            transaction_type = TRANSACTION_TYPE_BROKER_COMMISSION
        elif any(keyword in description for keyword in CASH_IN_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_CASH_IN
        elif any(keyword in description for keyword in CASH_OUT_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_CASH_OUT
        elif any(keyword in description for keyword in DIVIDEND_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_DIVIDEND
            security, best_match = await _find_security(security_description, investor)
        elif any(keyword in description for keyword in INTEREST_INCOME_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_INTEREST_INCOME
        elif pd.notna(security_description):
            security, best_match = await _find_security(security_description, investor)
            if debit > 0:
                transaction_type = TRANSACTION_TYPE_BUY
            elif credit > 0:
                transaction_type = TRANSACTION_TYPE_SELL
        else:
            return None, "skipped"

        transaction_data = {
            "investor": investor,
            "account": account,
            "security": security,
            "currency": currency,
            "type": transaction_type,
            "date": transaction_date,
        }

        if transaction_type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL]:
            if transaction_type == TRANSACTION_TYPE_BUY:
                quantity = Decimal(str(debit)) / price
            else:
                quantity = -Decimal(str(credit)) / price
            transaction_data.update(
                {
                    "quantity": round(quantity, quantity_decimal_places),
                    "price": round(Decimal(str(price)), price_decimal_places),
                }
            )
        elif transaction_type in [
            TRANSACTION_TYPE_INTEREST_INCOME,
            TRANSACTION_TYPE_DIVIDEND,
        ]:
            transaction_data["cash_flow"] = Decimal(str(credit))
        elif transaction_type == TRANSACTION_TYPE_CASH_IN:
            transaction_data["cash_flow"] = Decimal(str(credit))
        elif transaction_type == TRANSACTION_TYPE_CASH_OUT:
            transaction_data["cash_flow"] = -Decimal(str(debit))
        elif transaction_type == TRANSACTION_TYPE_BROKER_COMMISSION:
            transaction_data["commission"] = -Decimal(str(debit))

        NON_SECURITY_RELATED_TRANSACTION_TYPES = [
            TRANSACTION_TYPE_INTEREST_INCOME,
            TRANSACTION_TYPE_CASH_IN,
            TRANSACTION_TYPE_CASH_OUT,
            TRANSACTION_TYPE_BROKER_COMMISSION,
        ]

        exists = await transaction_exists(transaction_data)
        if exists:
            logger.debug(f"Transaction already exists. Duplicate: {transaction_data}")
            return None, "duplicate"

        if security is None and transaction_type not in NON_SECURITY_RELATED_TRANSACTION_TYPES:
            mapping_details = {
                "security_description": security_description,
                "best_match": best_match,
            }
            logger.debug(f"Mapping required for transaction: {transaction_data}")
            return {
                "mapping_details": mapping_details,
                "transaction_details": transaction_data,
            }, "mapping_required"

        logger.debug(f"Transaction processed successfully {transaction_type}, {transaction_data}")

        return transaction_data, "new"
    except ValueError as e:
        logger.error(f"ValueError in process_transaction_row {str(e)}, {row}")
        return None, "error"
    except Exception as e:
        logger.error(f"Unexpected error in process_transaction_row {str(e)}, {row}")
        return None, "error"


async def parse_charles_stanley_transactions(
    file_path, currency, account_id, user_id, confirm_every
):
    """Parse Charles Stanley transaction file.

    Refactored to ONLY yield messages without awaiting confirmations.

    Args:
        file_path: Path to the transaction file
        currency: Transaction currency
        account_id: ID of the broker account
        user_id: ID of the user
        confirm_every: Whether to confirm each transaction
    """
    yield {
        "status": "initialization",
        "message": "Opening and reading file",
    }
    logger.debug("Yielded progress message: Opening file and preparing for import")

    try:
        df = read_excel_file(file_path)
        if df.empty:
            raise ValueError("The Excel file is empty or could not be read.")
        df = df[df["Date"].notna()]
        total_rows = df.shape[0]
        logger.debug(f"File read successfully. Total rows: {total_rows}")
        yield {
            "status": "initialization",
            "message": "File read successfully. Preparing for import",
            "total_to_update": int(total_rows),
        }
    except Exception as e:
        error_message = f"Error reading Excel file: {str(e)}"
        logger.error(error_message)
        yield {"error": error_message}
        return

    try:
        investor = await get_investor(user_id)
        account = await get_account(account_id)
        logger.debug("Retrieved investor and broker account")
    except Exception as e:
        logger.error(f"Error getting investor or broker account: {str(e)}")
        yield {
            "error": (
                f"An unexpected error occurred while getting investor or broker account: "
                f"{str(e)}"
            )
        }
        return

    BATCH_SIZE = 1
    total_transactions = 0
    # imported_transactions = 0
    skipped_count = 0
    duplicate_count = 0
    import_errors = 0

    for index, row in df.iterrows():
        # if consumer.stop_event.is_set():
        #     logger.debug("Stop event detected. Breaking loop.")
        #     break

        try:
            total_transactions += 1
            transaction_data, status = await _process_transaction_row(
                row, investor, account, currency
            )

            logger.debug(f"Row {index + 1} processed. Status: {status}")
            logger.debug(f"Transaction data: {transaction_data}")

            if (index + 1) % BATCH_SIZE == 0 or index == total_rows - 1:
                progress = min(((index + 1) / total_rows) * 100, 100)
                yield {
                    "status": "progress",
                    "message": f"Processing transaction {index + 1} of {total_rows}",
                    "progress": progress,
                    "current": index + 1,
                }

            if status == "new":
                if confirm_every:
                    yield {
                        "status": "transaction_confirmation",
                        "data": transaction_data,
                    }
                    logger.debug("Yielded transaction_confirmation for row %d", index + 1)
                else:
                    yield {
                        "status": "add_transaction",
                        "data": transaction_data,
                    }
            elif status == "mapping_required":
                # Always yield for security mapping, regardless of confirm_every
                yield {
                    "status": "security_mapping",
                    "mapping_data": transaction_data.get("mapping_details"),
                    "transaction_data": transaction_data.get("transaction_details"),
                }
                logger.debug("Yielded security_mapping for row %d", index + 1)
            elif status == "skipped":
                skipped_count += 1
                logger.debug("Transaction skipped for row %d", index + 1)
            elif status == "duplicate":
                duplicate_count += 1
                logger.debug("Transaction duplicate for row %d", index + 1)
            else:
                logger.warning("Unknown status '%s' for row %d", status, index + 1)

        except InvalidOperation as e:
            logger.error(f"InvalidOperation in process_transaction_row: {str(e)}")
            yield {
                "error": f"An invalid operation occurred while processing a transaction: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error processing transaction at row {index + 1}: {str(e)}")
            logger.error(f"Row data: {row}")
            import_errors += 1
            yield {
                "error": (
                    f"An unexpected error occurred while processing a transaction "
                    f"at row {index + 1}: {str(e)}"
                )
            }

    yield {
        "status": "complete",
        "data": {
            "totalTransactions": total_transactions,
            "importedTransactions": 0,  # Filled in the consumer
            "skippedTransactions": skipped_count,
            "duplicateTransactions": duplicate_count,
            "importErrors": import_errors,
        },
    }
    logger.debug("Yielded completion of import process")


# =============================================================================
# OKX Trading History CSV parser
# =============================================================================
#
# Parses the user-exported OKX "Unified Bill History" CSV. The CSV is distinct
# from the live OKX REST API payloads: each spot trade spans two bill rows
# (base leg + quote leg, sharing one ``Order id``), options appear as either a
# single fill row or a single settlement row, and transfers are skipped.
#
# The adapter converts each row/pair into the SAME OKX payload dicts the live
# API normalizers in ``services/crypto_exchange.py`` consume, then persists via
# ``persist_crypto_exchange_event``. ``import_provider`` is set to ``okx_csv``
# (not ``okx``) so CSV imports dedup independently of API imports under the
# ``(investor, account, import_provider, import_account_id, import_event_id)``
# key.

OKX_CSV_IMPORT_PROVIDER = "okx_csv"


def _parse_okx_csv_tz_offset(line_one):
    """Extract the timezone offset (e.g. ``UTC+3``) from the CSV's metadata line.

    Returns a ``timedelta``. Defaults to ``timedelta(0)`` (UTC) when the field is
    missing or unparseable so import never hard-fails on an unexpected header.
    """
    if not line_one:
        return timedelta(0)
    text = line_one[0] if isinstance(line_one, (list, tuple)) else str(line_one)
    text = text.lstrip("\ufeff").strip()
    import re

    match = re.search(r"UTC\s*([+-])\s*(\d{1,2})(?::(\d{2}))?", text, re.IGNORECASE)
    if not match:
        return timedelta(0)
    sign = 1 if match.group(1) == "+" else -1
    hours = int(match.group(2))
    minutes = int(match.group(3)) if match.group(3) else 0
    return sign * timedelta(hours=hours, minutes=minutes)


def _okx_time_to_utc_ms(time_str, tz_offset):
    """Convert ``YYYY-MM-DD HH:MM:SS`` in the export's TZ to UTC ms-epoch.

    The OKX export timestamps are wall-clock in the account's display TZ (e.g.
    ``UTC+3``). To store UTC ms-epoch we parse the wall clock as that TZ, then
    convert to UTC.
    """
    naive = datetime.strptime(str(time_str).strip(), "%Y-%m-%d %H:%M:%S")
    local = naive.replace(tzinfo=timezone(tz_offset))
    return int(local.astimezone(timezone.utc).timestamp() * 1000)


def _strip_okx_bom(value):
    """Strip the UTF-8 BOM that OKX prepends to (nearly) every CSV cell."""
    if value is None:
        return value
    if isinstance(value, str):
        return value.lstrip("\ufeff").strip()
    return value


def _okx_base_currency(symbol):
    """Return the base currency from an OKX spot/option ``Symbol`` (``BTC-USDT`` -> ``BTC``)."""
    return str(symbol).split("-")[0]


def _normalize_okx_csv_event(payload):
    """Run the live-API OKX normalizer for ``payload`` and re-tag for CSV import.

    The shared normalizers hardcode ``provider="okx"`` (so API and CSV rows would
    share a dedup namespace). For CSV imports we override ``provider`` to
    ``okx_csv`` so a re-import of the same trade via the API does not silently
    dedup against the CSV row (and vice versa).
    """
    from services.crypto_exchange import (
        CryptoExchangeEvent,
        _single_leg,
        normalize_okx_option_fill,
        normalize_okx_option_settlement,
        normalize_okx_spot_fill,
    )

    kind = payload["__kind"]
    if kind == "transfer":
        ccy = payload["ccy"].upper()
        amount = Decimal(payload["amount"])
        category = payload["category"]
        return CryptoExchangeEvent(
            provider=OKX_CSV_IMPORT_PROVIDER,
            provider_event_id=f"csv_transfer:{payload['billId']}",
            group_id=payload["billId"],
            timestamp_ms=int(payload["ts"]),
            category=category,
            raw_type="transfer",
            legs=_single_leg(ccy, amount, ccy),
        )
    if kind == "spot":
        event = normalize_okx_spot_fill(payload)
    elif kind == "option_fill":
        event = normalize_okx_option_fill(payload)
    else:
        event = normalize_okx_option_settlement(payload)
    event.provider = OKX_CSV_IMPORT_PROVIDER
    return event


def _persist_okx_csv_fx_event(payload, investor, account):
    """Persist a stablecoin<->stablecoin CONVERT as an FXTransaction.

    Bypasses the crypto-event pipeline (no asset/price resolution) and saves
    via ``services.transactions.save_single_transaction`` with ``is_fx=True``.

    Returns ``"created"`` if a new FXTransaction was persisted, ``"duplicate"``
    if one already exists for this event id, or raises on a genuine error.
    """
    from common.models import FXTransaction
    from services.transactions import save_single_transaction

    provider = OKX_CSV_IMPORT_PROVIDER
    event_id = f"csv_fx:{payload['billId']}"
    import_account_id = account.native_id or str(account.id)

    # Explicit dedup (mirrors persist_crypto_exchange_event) so duplicates are
    # distinguishable from real save errors.
    if FXTransaction.objects.filter(
        investor=investor,
        account=account,
        import_provider=provider,
        import_account_id=import_account_id,
        import_event_id=event_id,
    ).exists():
        return "duplicate"

    from_amount = Decimal(payload["from_amount"])
    to_amount = Decimal(payload["to_amount"])
    rate = from_amount / to_amount if to_amount else Decimal("0")
    data = {
        "is_fx": True,
        "investor": investor,
        "account": account,
        "date": datetime.fromtimestamp(int(payload["ts"]) / 1000, tz=timezone.utc).replace(tzinfo=None),
        "from_currency": payload["from_ccy"],
        "to_currency": payload["to_ccy"],
        "from_amount": from_amount,
        "to_amount": to_amount,
        "exchange_rate": rate,
        "comment": f"provider={provider}; group_id={payload['billId']}",
        "import_provider": provider,
        "import_account_id": import_account_id,
        "import_event_id": event_id,
        "import_group_id": payload["billId"],
        "import_event_type": "fx",
    }
    # Carry the fee through in its native currency (no conversion — issue #30).
    fee = Decimal(payload.get("fee") or "0")
    fee_ccy = payload.get("fee_ccy") or ""
    if fee != 0 and fee_ccy:
        data["commission"] = fee
        data["commission_currency"] = fee_ccy
    result = save_single_transaction(data)
    if not result.get("success"):
        raise RuntimeError(f"FX save failed: {result.get('error')}")
    return "created"


def _okx_csv_fx_payload_from_rows(order_id, rows):
    """Build an FX (stablecoin<->stablecoin) payload from a paired set of CSV
    rows sharing one ``Order id``. The leg with negative ``Balance Change`` is
    the currency given up (from); the positive leg is received (to). Returns
    ``(payload, source_id)`` or ``None`` if the rows lack a signed leg pair
    (malformed). Used by both the -CONVERT path and the normal spot path when
    both legs settle in stablecoins.
    """
    from_row = to_row = None
    from_rid = to_rid = None
    fill_time = rows[0][2] if rows else None
    for r, rid, ft, _sym in rows:
        bal = Decimal(str(r.get("Balance Change") or "0"))
        if bal < 0:
            from_row, from_rid, fill_time = r, rid, ft
        elif bal > 0:
            to_row, to_rid, fill_time = r, rid, ft
    if from_row is None or to_row is None:
        return None  # malformed — no signed leg pair
    from_ccy = (from_row.get("Balance Unit") or "").upper()
    to_ccy = (to_row.get("Balance Unit") or "").upper()
    # Amounts are GROSS trade fill quantities (the Amount column), NOT Balance
    # Change (which is net of fee). Using net here double-subtracts the fee,
    # because get_cash_flow_by_currency applies commission on top of the amounts.
    # The from/to legs are identified by Balance Change sign (which way the
    # value moved), but the magnitude comes from Amount.
    from_amount = abs(Decimal(str(from_row.get("Amount") or "0")))
    to_amount = abs(Decimal(str(to_row.get("Amount") or "0")))
    # Capture the fee from whichever leg carries a non-zero Fee/Fee Unit.
    # The fee is kept in its native currency (not converted) — see issue #30.
    fee = Decimal("0")
    fee_ccy = ""
    for r, _rid, _ft, _sym in rows:
        leg_fee = Decimal(str(r.get("Fee") or "0"))
        if leg_fee != 0:
            fee = leg_fee
            fee_ccy = (_strip_okx_bom(r.get("Fee Unit")) or "").upper()
            break
    payload = {
        "__kind": "fx",
        "from_ccy": from_ccy,
        "to_ccy": to_ccy,
        "from_amount": str(from_amount),
        "to_amount": str(to_amount),
        "ts": str(fill_time),
        "billId": str(from_rid),
        "fee": str(fee),
        "fee_ccy": fee_ccy,
    }
    return (payload, str(from_rid))


def build_okx_csv_events(df, tz_offset):
    """Adapt a parsed OKX CSV DataFrame into OKX-API-shape event payloads.

    Walks the rows once, grouping spot rows by ``Order id`` (each spot trade is
    two bill rows: a base leg and a quote leg). Options are single-row events.
    Transfers are emitted as ``__kind="transfer"`` payloads: stablecoin
    (USDT/USDC) legs carry ``category="deposit"``/``"withdrawal"`` (Transfer
    in/out) so the existing cash-routing re-classifies them as Cash in/out;
    non-stablecoin legs carry ``category="transfer"`` (Crypto transfer in/out).

    The base/quote split is identified by ``Balance Unit`` (the bill's settled
    currency): the leg whose ``Balance Unit`` equals the symbol's base currency
    is the base leg. (The export labels every row's ``Trading Unit`` as the base
    currency, so ``Trading Unit`` cannot distinguish the legs; ``Balance Unit``
    can.)

    Yields ``(payload, source_id)`` tuples where ``payload`` carries a private
    ``__kind`` discriminator consumed by ``_normalize_okx_csv_event``.
    """
    spot_groups = {}
    convert_groups = {}
    events = []
    skipped_transfer_ids = []

    for _, row in df.iterrows():
        trade_type = str(row.get("Trade Type") or "").strip()
        action = str(row.get("Action") or "").strip()
        row_id = _strip_okx_bom(row.get("id"))
        order_id = _strip_okx_bom(row.get("Order id"))
        raw_symbol = row.get("Symbol")
        if raw_symbol is None or (isinstance(raw_symbol, float) and pd.isna(raw_symbol)):
            symbol_clean = ""
        else:
            symbol_clean = _strip_okx_bom(raw_symbol)
        fill_time = _okx_time_to_utc_ms(row["Time"], tz_offset)

        if trade_type == "Transfer":
            balance_unit = (_strip_okx_bom(row.get("Balance Unit")) or "").upper()
            action = str(row.get("Action") or "").strip().lower()
            # Transfer rows carry Amount=0; the signed movement is Balance Change.
            amount = Decimal(str(row.get("Balance Change") or "0"))
            is_stablecoin = balance_unit in {"USDT", "USDC"}
            if is_stablecoin:
                # Stablecoin in -> deposit (Cash in); out -> withdrawal (Cash out).
                category = "deposit" if "in" in action else "withdrawal"
            else:
                # Non-stablecoin (BTC/TRUMP) internal moves stay crypto transfers.
                category = "transfer"
            payload = {
                "__kind": "transfer",
                "category": category,
                "ccy": balance_unit,
                "amount": str(amount),
                "ts": str(fill_time),
                "billId": str(row_id),
            }
            events.append((payload, str(row_id)))
            continue

        if trade_type == "Spot":
            if symbol_clean.endswith("-CONVERT"):
                convert_groups.setdefault(order_id, []).append(
                    (row, row_id, fill_time, symbol_clean)
                )
                continue
            # Defer: collect all rows, then pair base+quote per Order id below.
            spot_groups.setdefault(order_id, []).append((row, row_id, fill_time, symbol_clean))
            continue

        if trade_type == "Option":
            amount = Decimal(str(row["Amount"]))
            filled_price = Decimal(str(row["Filled Price"]))
            fee = Decimal(str(row.get("Fee") or "0"))
            fee_unit = _strip_okx_bom(row.get("Fee Unit")) or "USD"

            if action.lower().startswith("expired"):
                # Option expiration/settlement. Delivered coin = Balance Unit,
                # signed delivered amount = Balance Change (the wallet balance
                # change, i.e. collateral released on OTM expiry is positive;
                # ITM delivery is negative for the writer), settlement px =
                # Filled Price. ``ordId`` is 0/empty for expiries; the
                # normalizer falls back to billId for the group id.
                # NOTE: Position Change tracks contracts, not coin flow, so it
                # has the wrong sign/magnitude for the delivered coin amount.
                ccy = _strip_okx_bom(row.get("Balance Unit")) or "USD"
                bal_chg = Decimal(str(row.get("Balance Change") or "0"))
                payload = {
                    "__kind": "option_settlement",
                    "ccy": ccy,
                    "balChg": str(bal_chg),
                    "px": str(filled_price),
                    "billId": str(row_id),
                    "ts": str(fill_time),
                    "ordId": str(order_id) if order_id and order_id != "0" else "",
                }
                events.append((payload, str(row_id)))
            else:
                # Option fill (Buy/Sell). Single row.
                payload = {
                    "__kind": "option_fill",
                    "instId": symbol_clean,
                    "side": action.lower(),
                    "fillSz": str(amount),
                    "fillPx": str(filled_price),
                    "fillTime": str(fill_time),
                    "tradeId": str(row_id),
                    "ordId": str(order_id) if order_id and order_id != "0" else "",
                    "fee": str(fee),
                    "feeCcy": fee_unit,
                }
                events.append((payload, str(row_id)))
            continue

        logger.debug("Skipping unhandled OKX CSV Trade Type=%s (id=%s)", trade_type, row_id)

    # Emit one spot_fill event per BASE leg. The base leg is the bill row whose
    # ``Balance Unit`` equals the instrument's base currency (e.g. BTC for
    # BTC-USDT); the export labels every row's ``Trading Unit`` as the base
    # currency, so only ``Balance Unit`` reliably distinguishes base from quote.
    # A single Order id can span many fills (the user's data has one order with
    # 10 base legs + 10 quote legs = 10 distinct trades), so each base leg
    # becomes its own event keyed by its own ``id``. Each base leg already
    # carries its own fee, so no cross-leg fee pairing is required; we only fall
    # back to a sibling leg's fee if the base leg's fee is blank.
    for order_id, rows in spot_groups.items():
        # A spot order whose EVERY leg settles in a stablecoin (USDT/USDC) is a
        # stablecoin<->stablecoin conversion = an FX transaction, regardless of
        # whether the symbol carries a -CONVERT suffix or the Action is empty.
        # Route the whole order to one FX event (mirrors the -CONVERT path).
        all_balance_units = {
            (_strip_okx_bom(r.get("Balance Unit")) or "").upper() for r, _rid, _ft, _sym in rows
        }
        if all_balance_units and all_balance_units.issubset({"USDT", "USDC"}):
            fx_payload = _okx_csv_fx_payload_from_rows(order_id, rows)
            if fx_payload is not None:
                events.append(fx_payload)
            else:
                for _r, rid, _ft, _sym in rows:
                    skipped_transfer_ids.append(rid)
            continue

        for row, row_id, fill_time, symbol_clean in rows:
            base_ccy = _okx_base_currency(symbol_clean)
            if _strip_okx_bom(row.get("Balance Unit")) != base_ccy:
                continue  # quote leg; the base leg of this fill is emitted separately

            # Skip conversion trades (e.g. ``BTC-USDT-CONVERT``): the shared
            # spot normalizer splits the instrument into exactly base-quote and
            # cannot represent a crypto-to-crypto conversion. Counted as skipped.
            if symbol_clean.count("-") != 1:
                skipped_transfer_ids.append(row_id)
                continue

            amount = Decimal(str(row["Amount"]))
            filled_price = Decimal(str(row["Filled Price"]))
            side = str(row.get("Action") or "").strip().lower()

            fee = Decimal(str(row.get("Fee") or "0"))
            fee_unit = _strip_okx_bom(row.get("Fee Unit")) or ""
            if fee == 0:
                # Fall back to a sibling leg that carries a non-zero fee.
                for sib_row, _sib_id, _ft, _sym in rows:
                    leg_fee = Decimal(str(sib_row.get("Fee") or "0"))
                    if leg_fee != 0:
                        fee = leg_fee
                        fee_unit = _strip_okx_bom(sib_row.get("Fee Unit")) or fee_unit
                        break

            # feeCcy: prefer the fee-bearing leg's unit; else the symbol's quote
            # currency; else the base symbol itself (normalizer falls back to quote).
            if fee_unit:
                fee_ccy = fee_unit
            elif "-" in symbol_clean:
                fee_ccy = symbol_clean.split("-")[-1]
            else:
                fee_ccy = symbol_clean

            payload = {
                "__kind": "spot",
                "instId": symbol_clean,
                "side": side,
                "fillSz": str(amount),
                "fillPx": str(filled_price),
                "fillTime": str(fill_time),
                "tradeId": str(row_id),
                "ordId": str(order_id),
                "fee": str(fee),
                "feeCcy": fee_ccy,
            }
            events.append((payload, str(row_id)))

    # CONVERT rows: stablecoin<->stablecoin = FX; crypto<->stablecoin = spot.
    for order_id, rows in convert_groups.items():
        # Recompute the underlying symbol (drop the -CONVERT suffix).
        sample_symbol = rows[0][3]
        underlying = sample_symbol[: -len("-CONVERT")]  # e.g. BTC-USDT or USDC-USDT
        units = {(rows[i][0].get("Balance Unit") or "").upper(): i for i in range(len(rows))}
        # Pair each row; classify by whether BOTH units are stablecoins.
        all_stablecoin = all(u in {"USDT", "USDC"} for u in units)
        if all_stablecoin:
            # FX (stablecoin<->stablecoin): reuse the shared FX-payload builder.
            fx = _okx_csv_fx_payload_from_rows(order_id, rows)
            if fx is not None:
                events.append(fx)
            else:
                for _r, rid, _ft, _sym in rows:
                    skipped_transfer_ids.append(rid)
            continue
        else:
            # crypto<->stablecoin: emit a spot payload from the base (crypto) leg.
            base, quote = underlying.split("-")
            for r, rid, ft, _sym in rows:
                unit = (r.get("Balance Unit") or "").upper()
                if unit != base:
                    continue
                bal = Decimal(str(r.get("Balance Change") or "0"))
                side = "buy" if bal > 0 else "sell"
                amount = abs(Decimal(str(r.get("Amount") or "0")))
                filled_price = Decimal(str(r.get("Filled Price") or "0"))
                fee = Decimal(str(r.get("Fee") or "0"))
                fee_unit = _strip_okx_bom(r.get("Fee Unit")) or ""
                fee_ccy = fee_unit if fee_unit else quote
                payload = {
                    "__kind": "spot",
                    "instId": underlying,
                    "side": side,
                    "fillSz": str(amount),
                    "fillPx": str(filled_price),
                    "fillTime": str(ft),
                    "tradeId": str(rid),
                    "ordId": str(order_id),
                    "fee": str(fee),
                    "feeCcy": fee_ccy,
                }
                events.append((payload, str(rid)))
                break

    return events, skipped_transfer_ids


async def parse_okx_trading_csv(file_path, account_id, user_id, confirm_every):
    """Parse an OKX Trading History CSV and persist canonical crypto events.

    Async generator mirroring ``parse_charles_stanley_transactions``: yields
    ``initialization`` / ``progress`` / ``transaction_saved`` / ``skipped`` /
    ``complete`` status dicts. Each event is normalized to an OKX-API-shape
    payload, persisted via ``persist_crypto_exchange_event`` (which dedups on
    ``import_provider="okx_csv"``), and the result yielded as
    ``transaction_saved``.

    Args:
        file_path: Path to the downloaded OKX Trading History CSV.
        account_id: ID of the target ``Accounts`` row (must belong to an OKX broker).
        user_id: ID of the owning investor.
        confirm_every: Unused for crypto events (they persist immediately, like
            the live API import path); accepted to match the parser signature.
    """
    yield {
        "status": "initialization",
        "message": "Opening and reading OKX Trading History CSV",
    }

    try:
        # Read the metadata line first to recover the export's timezone.
        with open(file_path, "r", encoding="utf-8-sig", newline="") as fh:
            first_line = fh.readline()
        tz_offset = _parse_okx_csv_tz_offset(first_line)

        df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")
        if df.empty:
            raise ValueError("The OKX CSV file is empty or could not be read.")
        # The BOM leaks into column names and cell values; normalize both.
        df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
        string_cols = df.select_dtypes(include=["string", "object"]).columns
        for col in string_cols:
            df[col] = df[col].map(_strip_okx_bom)

        events, skipped_transfer_ids = build_okx_csv_events(df, tz_offset)
        total_events = len(events)
        logger.debug(
            "OKX CSV read: %d events, %d transfers skipped", total_events, len(skipped_transfer_ids)
        )
        yield {
            "status": "initialization",
            "message": "OKX CSV read successfully. Preparing for import",
            "total_to_update": int(total_events),
        }
    except Exception as e:
        error_message = f"Error reading OKX CSV file: {str(e)}"
        logger.error(error_message)
        yield {"error": error_message}
        return

    try:
        investor = await get_investor(user_id)
        account = await get_account(account_id)
        logger.debug("Retrieved investor and OKX account")
    except Exception as e:
        logger.error(f"Error getting investor or account: {str(e)}")
        yield {
            "error": (
                f"An unexpected error occurred while getting investor or account: {str(e)}"
            )
        }
        return

    imported = 0
    duplicate = 0
    skipped = len(skipped_transfer_ids)
    import_errors = 0

    from services.crypto_exchange import persist_crypto_exchange_event

    for index, (payload, source_id) in enumerate(events):
        try:
            if payload.get("__kind") == "fx":
                outcome = await database_sync_to_async(_persist_okx_csv_fx_event)(
                    payload, investor, account
                )
                progress = min(((index + 1) / total_events) * 100, 100) if total_events else 100
                yield {
                    "status": "progress",
                    "message": f"Processing OKX event {index + 1} of {total_events}",
                    "progress": progress,
                    "current": index + 1,
                }
                if outcome == "created":
                    imported += 1
                    yield {
                        "status": "transaction_saved",
                        "message": "Saved OKX FX conversion",
                        "transaction": {"import_group_id": payload["billId"], "count": 1},
                    }
                else:  # "duplicate"
                    duplicate += 1
                    yield {
                        "status": "duplicate_transaction",
                        "message": f"OKX FX event already imported (id={source_id})",
                        "transaction": {"import_group_id": payload["billId"], "count": 0},
                    }
                continue

            event = _normalize_okx_csv_event(payload)  # re-tagged with okx_csv provider
            created = await database_sync_to_async(persist_crypto_exchange_event)(
                event, investor, account
            )

            progress = min(((index + 1) / total_events) * 100, 100) if total_events else 100
            yield {
                "status": "progress",
                "message": f"Processing OKX event {index + 1} of {total_events}",
                "progress": progress,
                "current": index + 1,
            }

            if created:
                imported += len(created)
                yield {
                    "status": "transaction_saved",
                    "message": f"Saved {len(created)} OKX transaction legs",
                    "transaction": {
                        "import_group_id": event.group_id,
                        "count": len(created),
                    },
                }
            else:
                duplicate += 1
                yield {
                    "status": "duplicate_transaction",
                    "message": f"OKX event already imported (id={source_id})",
                    "transaction": {"import_group_id": event.group_id, "count": 0},
                }
        except Exception as e:
            logger.error(f"Error processing OKX CSV event (id={source_id}): {str(e)}", exc_info=True)
            import_errors += 1
            yield {
                "status": "transaction_error",
                "message": f"Error processing OKX event (id={source_id}): {str(e)}",
                "error_detail": str(e),
            }

    yield {
        "status": "complete",
        "data": {
            "totalTransactions": total_events + skipped,
            "importedTransactions": imported,
            "skippedTransactions": skipped,
            "duplicateTransactions": duplicate,
            "importErrors": import_errors,
        },
    }
    logger.debug("Yielded completion of OKX CSV import process")


def generate_dates_for_price_import(start, end, frequency):
    """Generate a list of dates based on frequency for price import.

    Args:
        start: Start date for the range.
        end: End date for the range.
        frequency: The frequency of dates ('daily', 'weekly', 'monthly').

    Returns:
        list: List of date objects.
    """
    dates = []
    if frequency == "daily":
        current = start
        while current <= end:
            if current.weekday() < 5:  # Monday is 0, Friday is 4
                dates.append(current)
            current += timedelta(days=1)
    elif frequency == "weekly":
        # Find the next Friday
        days_until_friday = (4 - start.weekday()) % 7
        current = start + timedelta(days=days_until_friday)
        if current <= start:
            current += timedelta(
                days=7
            )  # Move to the next Friday if we're already on or past Friday
        while current <= end:
            dates.append(current)
            current += timedelta(days=7)
    elif frequency == "monthly":
        current = (
            start.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        )  # Last day of the start month
        while current <= end:
            dates.append(current)
            current = (
                (current + relativedelta(months=1)).replace(day=1)
                + relativedelta(months=1)
                - timedelta(days=1)
            )
    elif frequency == "quarterly":
        quarter_end_month = 3 * ((start.month - 1) // 3 + 1)
        current = (
            date(start.year, quarter_end_month, 1) + relativedelta(months=1) - timedelta(days=1)
        )
        while current <= end:
            dates.append(current)
            current = (
                (current + relativedelta(months=3)).replace(day=1)
                + relativedelta(months=1)
                - timedelta(days=1)
            )
    elif frequency == "yearly":
        current = date(start.year, 12, 31)
        while current <= end:
            dates.append(current)
            current = date(current.year + 1, 12, 31)
    else:
        raise ValueError(f"Unsupported frequency: {frequency}")

    return dates


# =============================================================================
# Price importers (formerly in core/import_utils.py)
# =============================================================================


async def import_security_prices_from_ft(security, dates):
    """Import security prices from Financial Times.

    Args:
        security: The security instance to import prices for.
        dates: List of dates to fetch prices for.

    Yields:
        dict: Status updates during the import process.

    Raises:
        Exception: If HTTP request or parsing fails.
    """
    url = security.update_link
    user_agent = UserAgent().random
    headers = {"User-Agent": user_agent}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                content = await response.text()
        except aiohttp.ClientError as e:
            yield {
                "security_name": security.name,
                "status": "error",
                "message": f"Error fetching data for {security.name}: {str(e)}",
            }
            return

        soup = BeautifulSoup(content, "html.parser")

        elem = soup.find("section", {"class": "mod-tearsheet-add-to-watchlist"})
        if elem and "data-mod-config" in elem.attrs:
            data = json.loads(elem["data-mod-config"])
            xid = data["xid"]

            for d in dates:
                result = {
                    "security_name": security.name,
                    "date": d.strftime("%Y-%m-%d"),
                    "status": "skipped",
                }

                # Check if a price already exists for this date
                price_exists_func = database_sync_to_async(
                    Prices.objects.filter(security=security, date=d).exists
                )
                price_exists = await price_exists_func()
                if price_exists:
                    yield result
                    continue

                end_date = d.strftime("%Y/%m/%d")
                start_date = (d - timedelta(days=7)).strftime("%Y/%m/%d")

                try:
                    async with session.get(
                        "https://markets.ft.com/data/equities/ajax/get-historical-prices",
                        params={
                            "startDate": start_date,
                            "endDate": end_date,
                            "symbol": xid,
                        },
                        headers=headers,
                        timeout=10,
                    ) as r:
                        r.raise_for_status()
                        data = await r.json()

                    df = pd.read_html(StringIO("<table>" + data["html"] + "</table>"))[0]
                    df.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
                    df["Date"] = pd.to_datetime(
                        df["Date"].apply(lambda x: x.split(",")[-2][1:] + x.split(",")[-1])
                    )

                    date_as_timestamp = pd.Timestamp(d)
                    df = df[df["Date"] <= date_as_timestamp]

                    if not df.empty:
                        latest_price = df.iloc[0]["Close"]
                        if security.name in MUTUAL_FUNDS_IN_PENCES:
                            latest_price = latest_price / 100
                        create_price_func = database_sync_to_async(Prices.objects.create)
                        await create_price_func(security=security, date=d, price=latest_price)
                        result["status"] = "updated"
                    else:
                        result["status"] = "error"
                        result["message"] = (
                            f"No data found for {d.strftime('%Y-%m-%d')}"
                        )
                except Exception as e:
                    result["status"] = "error"
                    result["message"] = (
                        f"Error processing data for {security.name}: {str(e)}"
                    )

                yield result

        else:
            yield {
                "security_name": security.name,
                "status": "error",
                "message": f"No data found for {security.name}",
            }


async def import_security_prices_from_yahoo(security, dates):
    """
    Import security prices from Yahoo Finance.

    Note: Modern yfinance uses curl_cffi internally to handle headers and browser mimicking.
    We let yfinance handle the session to avoid conflicts.
    """
    if not security.yahoo_symbol:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No Yahoo Finance symbol specified for {security.name}",
        }
        return

    for d in dates:
        result = {
            "security_name": security.name,
            "date": d.strftime("%Y-%m-%d"),
            "status": "skipped",
        }

        # Check if a price already exists for this date
        price_exists_func = database_sync_to_async(
            Prices.objects.filter(security=security, date=d).exists
        )
        price_exists = await price_exists_func()
        if price_exists:
            yield result
            continue

        end_date = (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = (d - pd.Timedelta(days=6)).strftime("%Y-%m-%d")

        try:
            # Use run_in_executor to run yfinance operations in a separate thread
            # Let yfinance handle the session internally (uses curl_cffi for browser mimicking)
            loop = asyncio.get_running_loop()
            ticker = await loop.run_in_executor(_blocking_executor, yf.Ticker, security.yahoo_symbol)
            # Set auto_adjust to False to get unadjusted close prices
            history = await loop.run_in_executor(
                _blocking_executor,
                lambda ticker=ticker, start_date=start_date, end_date=end_date: ticker.history(
                    start=start_date, end=end_date, auto_adjust=False
                ),
            )

            if not history.empty:
                # Use 'Close' for unadjusted close price
                latest_price = history["Close"].iloc[-1]
                create_price_func = database_sync_to_async(Prices.objects.create)
                await create_price_func(security=security, date=d, price=latest_price)
                result["status"] = "updated"
            else:
                result["status"] = "error"
                result["message"] = f"No data found for {d.strftime('%Y-%m-%d')}"
        except Exception as e:
            logger.exception(f"Unexpected error processing data for {security.name}")
            result["status"] = "error"
            result["message"] = f"Unexpected error: {str(e)}"

        yield result


async def import_security_prices_from_micex(security, dates):
    """Import security prices from Moscow Exchange (MICEX).

    Args:
        security: The security instance to import prices for.
        dates: List of dates to fetch prices for.

    Yields:
        dict: Status updates during the import process.
    """
    if not security.secid:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No MICEX symbol specified for {security.name}",
        }
        return

    for d in dates:
        result = {
            "security_name": security.name,
            "date": d.strftime("%Y-%m-%d"),
            "status": "skipped",
        }

        # Check if price already exists
        price_exists_func = database_sync_to_async(
            Prices.objects.filter(security=security, date=d).exists
        )
        price_exists = await price_exists_func()

        if price_exists:
            yield result
            continue

        # Get wide enough interval to fetch data
        target_date = pd.Timestamp(d)
        end_date = (target_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # Include next day
        start_date = (target_date - pd.Timedelta(days=7)).strftime("%Y-%m-%d")

        # # Constants for MICEX API
        # selected_engine = "stock"
        # selected_market = "shares"
        # selected_board = "TQBR"

        # Constants for MICEX API
        engine_stock = "stock"
        engine_etf = "stock"
        engine_bond = "stock"
        market_shares = "shares"
        market_etfs = "shares"
        market_bonds = "bonds"
        board_stocks = "TQBR"
        board_etfs = "TQTF"
        board_bonds = "TQCB"

        if security.type == ASSET_TYPE_CHOICES[0][0]:
            selected_engine = engine_stock
            selected_market = market_shares
            selected_board = board_stocks
        elif security.type == ASSET_TYPE_CHOICES[2][0]:
            selected_engine = engine_etf
            selected_market = market_etfs
            selected_board = board_etfs
        elif security.type == ASSET_TYPE_CHOICES[1][0]:
            selected_engine = engine_bond
            selected_market = market_bonds
            selected_board = board_bonds
        else:
            yield {
                "security_name": security.name,
                "status": "error",
                "message": f"Invalid instrument type: {security.type}",
            }
            return

        url = (
            f"https://iss.moex.com/iss/history/engines/{selected_engine}/markets/"
            f"{selected_market}/boards/{selected_board}/securities/{security.secid}.json"
            f"?from={start_date}&till={end_date}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        error_msg = f"MOEX API error: {response.status}"
                        yield {
                            "security_name": security.name,
                            "date": d.strftime("%Y-%m-%d"),
                            "status": "error",
                            "message": error_msg,
                        }
                        continue

                    data = await response.json()

            if "history" in data and data["history"]["data"]:
                df = pd.DataFrame(data["history"]["data"], columns=data["history"]["columns"])
                # Convert date strings to datetime
                df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"])
                df.set_index("TRADEDATE", inplace=True)
                df = df.sort_index()  # Ensure chronological order

                if not df.empty:
                    # Find the closest trading day (preference to previous days)
                    closest_date = None

                    # First try to find exact date
                    if target_date in df.index:
                        closest_date = target_date
                    else:
                        # Find the closest previous trading day
                        prev_dates = df.index[df.index <= target_date]
                        if not prev_dates.empty:
                            closest_date = prev_dates[-1]

                    if closest_date is not None:
                        price = df.loc[closest_date, "CLOSE"]
                        if pd.notna(price):
                            create_price_func = database_sync_to_async(Prices.objects.create)
                            await create_price_func(
                                security=security,
                                date=d,  # Use original date
                                price=float(price),
                            )
                            result.update(
                                {
                                    "status": "updated",
                                    "message": (
                                        f"Used price from {closest_date.strftime('%Y-%m-%d')}"
                                        if closest_date != target_date
                                        else None
                                    ),
                                }
                            )
                        else:
                            result.update(
                                {
                                    "status": "error",
                                    "message": "No closing price available for the closest date",
                                }
                            )
                    else:
                        result.update(
                            {
                                "status": "error",
                                "message": "No suitable trading day found in the date range",
                            }
                        )
                else:
                    result.update(
                        {
                            "status": "error",
                            "message": "No data available in the date range",
                        }
                    )
            else:
                result.update({"status": "error", "message": "No data available from MOEX"})

            yield result

        except Exception as e:
            logger.exception(f"Error fetching MOEX data for {security.name}")
            yield {
                "security_name": security.name,
                "date": d.strftime("%Y-%m-%d"),
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }


async def import_security_prices_from_tbank(security, dates, user):
    """
    Import security prices from T-Bank (Tinkoff) API.

    Args:
        security: Assets instance with tbank_instrument_uid
        dates: List of dates to fetch prices for
        user: CustomUser instance (to get API token)
    """
    if not security.tbank_instrument_uid:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No T-Bank instrument UID specified for {security.name}",
        }
        return

    for d in dates:
        result = {
            "security_name": security.name,
            "date": d.strftime("%Y-%m-%d"),
            "status": "skipped",
        }

        # Check if price already exists
        price_exists_func = database_sync_to_async(
            Prices.objects.filter(security=security, date=d).exists
        )
        price_exists = await price_exists_func()
        if price_exists:
            yield result
            continue

        # Get price from T-Bank API
        try:
            price = await get_price_from_tbank(security.tbank_instrument_uid, d, user)
            if price:
                # T-Bank provides split-adjusted prices. If there have been splits
                # after this date, we need to reverse the adjustment to store
                # the actual historical price.
                cumulative_factor = await database_sync_to_async(
                    get_cumulative_split_factor
                )(security, d)
                if cumulative_factor != Decimal("1"):
                    # Reverse the adjustment: if factor is 0.5 (2:1 split),
                    # the actual pre-split price was 2x the T-Bank adjusted price
                    original_price = price
                    price = price / cumulative_factor
                    logger.debug(
                        f"Reversed split adjustment for {security.name} on {d}: "
                        f"{original_price} -> {price} (factor: {cumulative_factor})"
                    )

                create_price_func = database_sync_to_async(Prices.objects.create)
                await create_price_func(security=security, date=d, price=price)
                result["status"] = "updated"
            else:
                result["status"] = "error"
                result["message"] = f"No price found for {d.strftime('%Y-%m-%d')}"
        except Exception as e:
            logger.error(f"Error fetching price for {security.name} on {d}: {str(e)}")
            result["status"] = "error"
            result["message"] = f"Error: {str(e)}"

        yield result


# =============================================================================
# Galaxy broker parsers (formerly in core/import_utils.py)
# =============================================================================


async def _process_galaxy_transaction(
    user, account, date, currency, transaction_type, cash_flow=None, commission=None
):
    """
    Process a Galaxy transaction.

    Args:
        user: User object
        account: Accounts object
        date: Transaction date
        currency: Transaction currency
        transaction_type: Type of transaction
        cash_flow: Cash flow amount
        commission: Commission amount
    """
    transaction_data = {
        "investor": user,
        "account": account,
        "date": date,
        "type": transaction_type,
        "currency": currency,
        "cash_flow": round(Decimal(cash_flow), 2) if cash_flow is not None else None,
        "commission": round(Decimal(commission), 2) if commission is not None else None,
    }

    exists = await transaction_exists(transaction_data)
    if exists:
        return "duplicate", transaction_data
    return "new", transaction_data


async def parse_galaxy_account_cash_flows(
    file_path, currency, account, user, confirm_every
):
    """Parse Galaxy broker account cash flows with async support and progress tracking."""
    yield {
        "status": "initialization",
        "message": "Opening and reading Galaxy cash flow file",
    }
    logger.debug("Yielded progress message: Opening Galaxy cash flow file")

    try:
        # Read the Excel file
        df = pd.read_excel(file_path, header=3)  # Line 4 has table headers
        if df.empty:
            raise ValueError("The Excel file is empty or could not be read.")
        df = df[df["Дата"].notna()]  # Filter out rows without dates
        total_rows = df.shape[0]
        logger.debug(f"File read successfully. Total rows: {total_rows}")

        yield {
            "status": "initialization",
            "message": "File read successfully. Preparing for import",
            "total_to_update": int(total_rows),
        }
    except Exception as e:
        error_message = f"Error reading Excel file: {str(e)}"
        logger.error(error_message)
        yield {"error": error_message}
        return

    BATCH_SIZE = 1
    total_transactions = 0
    skipped_count = 0
    duplicate_count = 0
    import_errors = 0

    # Iterate over each row in the DataFrame
    for index, row in df.iterrows():
        try:
            # Keep as datetime object to preserve time information
            date = row["Дата"]
            if not pd.isna(date):
                # Ensure it's a datetime object
                if not isinstance(date, pd.Timestamp):
                    date = pd.to_datetime(date)
            transactions_to_process = []

            # Collect all transactions from the row
            if pd.notna(row["Инвестиции"]):
                transaction_type = (
                    TRANSACTION_TYPE_CASH_IN if row["Инвестиции"] > 0 else TRANSACTION_TYPE_CASH_OUT
                )
                transactions_to_process.append(("cash_flow", transaction_type, row["Инвестиции"]))

            if pd.notna(row["Комиссия"]):
                transactions_to_process.append(
                    ("commission", TRANSACTION_TYPE_BROKER_COMMISSION, row["Комиссия"])
                )

            if "Tax" in row and pd.notna(row["Tax"]):
                transactions_to_process.append(("cash_flow", TRANSACTION_TYPE_TAX, row["Tax"]))

            total_transactions += len(transactions_to_process)

            # Process each transaction
            for trans_type, trans_name, value in transactions_to_process:
                kwargs = {trans_type: value}
                status, transaction_data = await _process_galaxy_transaction(
                    user=user,
                    account=account,
                    date=date,
                    currency=currency,
                    transaction_type=trans_name,
                    **kwargs,
                )

                if status == "duplicate":
                    duplicate_count += 1
                    logger.debug(f"Duplicate {trans_type} transaction found for row {index + 1}")
                else:
                    if confirm_every:
                        yield {
                            "status": "transaction_confirmation",
                            "data": transaction_data,
                        }
                    else:
                        yield {
                            "status": "add_transaction",
                            "data": transaction_data,
                        }

            # Report progress
            if (index + 1) % BATCH_SIZE == 0 or index == total_rows - 1:
                progress = min(((index + 1) / total_rows) * 100, 100)
                yield {
                    "status": "progress",
                    "message": f"Processing row {index + 1} of {total_rows}",
                    "progress": progress,
                    "current": index + 1,
                }

        except Exception as e:
            logger.error(f"Error processing row {index + 1}: {str(e)}")
            import_errors += 1
            yield {
                "error": f"An unexpected error occurred while processing row {index + 1}: {str(e)}"
            }

    # Final yield with import summary
    yield {
        "status": "complete",
        "data": {
            "totalTransactions": total_transactions,
            "importedTransactions": 0,  # Will be filled in the consumer
            "skippedTransactions": skipped_count,
            "duplicateTransactions": duplicate_count,
            "importErrors": import_errors,
        },
    }
    logger.debug("Yielded completion of Galaxy cash flow import process")


async def parse_galaxy_account_security_transactions(
    file_path, currency, account, user, confirm_every=False
):
    """Async generator for parsing Galaxy broker account security transactions."""
    try:
        # Send initialization message
        yield {
            "status": "initialization",
            # 'total_to_update': total_potential_transactions,
            "message": "Starting Galaxy transactions import",
        }

        df = pd.read_excel(file_path, header=None)

        # Find transactions_start once
        transactions_start = None
        for i in range(len(df.columns)):
            if pd.notna(df.iloc[1, i]):
                date_row_index = df[df.iloc[:, i] == "Дата"].index
                if date_row_index.size > 0:
                    transactions_start = date_row_index[0] + 1
                    break

        if transactions_start is None:
            yield {"error": "Could not find transaction start row in the file"}
            return

        quantity_field = Transactions._meta.get_field("quantity")
        quantity_decimal_places = quantity_field.decimal_places
        price_field = Transactions._meta.get_field("price")
        price_decimal_places = price_field.decimal_places

        yield {
            "status": "initialization",
            # 'total_to_update': total_potential_transactions,
            "message": "Starting security processing",
        }

        # Process securities first
        valid_columns = None
        async for update in _process_galaxy_securities(df, user):
            if update["status"] == "security_processing_complete":
                valid_columns = update["valid_columns"]
                yield {
                    "status": "progress",
                    "message": "Security processing complete",
                }
            else:
                yield update

        logger.debug(f"Valid columns: {valid_columns}")

        if not valid_columns:
            yield {
                "status": "complete",
                "data": {
                    "totalTransactions": 0,
                    "importedTransactions": 0,
                    "skippedTransactions": 0,
                    "duplicateTransactions": 0,
                    "importErrors": 0,
                    "message": "No valid securities found",
                },
            }
            return

        # Calculate total number of potential transactions
        total_columns = len(valid_columns)
        rows_per_security = len(df) - transactions_start
        total_potential_transactions = int(
            total_columns * rows_per_security
        )  # Convert to int for proper serialization

        yield {
            "status": "initialization",
            "total_to_update": total_potential_transactions,
            "message": f"Starting processing {total_potential_transactions} transactions",
        }

        # Now process transactions only for valid columns
        processed = 0
        import_errors = 0
        duplicate_count = 0

        for i in valid_columns:
            security_name = df.iloc[1, i]
            isin = df.iloc[2, i]
            logger.debug(f"Processing transactions for security: {security_name} ({isin})")

            try:
                security = await database_sync_to_async(Assets.objects.get)(
                    name=security_name, ISIN=isin, investors=user, accounts=account
                )
            except Assets.DoesNotExist:
                logger.debug(
                    "Security not found with all conditions, "
                    f"yielding creation request for {security_name}."
                )
                continue

            for row in range(transactions_start, len(df)):
                if pd.isna(df.iloc[row, i]):
                    processed += 1
                    continue

                try:
                    # Keep as datetime object to preserve time information
                    date = df.iloc[row, i]
                    if not pd.isna(date):
                        # Ensure it's a datetime object
                        if not isinstance(date, pd.Timestamp):
                            date = pd.to_datetime(date)
                    price = (
                        round(Decimal(df.iloc[row, i + 1]), price_decimal_places)
                        if not pd.isna(df.iloc[row, i + 1])
                        else None
                    )
                    quantity = (
                        round(Decimal(df.iloc[row, i + 2]), quantity_decimal_places)
                        if not pd.isna(df.iloc[row, i + 2])
                        else None
                    )
                    dividend = (
                        round(Decimal(df.iloc[row, i + 3]), 2)
                        if not pd.isna(df.iloc[row, i + 3])
                        else None
                    )
                    commission = (
                        round(Decimal(df.iloc[row, i + 4]), 2)
                        if not pd.isna(df.iloc[row, i + 4])
                        else None
                    )

                    if quantity is None and dividend is None and commission is None:
                        processed += 1
                        logger.debug(f"Skipping empty row for security: {security_name}")
                        continue

                    transaction_type = None
                    if quantity is not None:
                        transaction_type = (
                            TRANSACTION_TYPE_BUY if quantity > 0 else TRANSACTION_TYPE_SELL
                        )
                    elif dividend is not None:
                        transaction_type = TRANSACTION_TYPE_DIVIDEND

                    transaction_data = {
                        "investor": user,
                        "account": account,
                        "security": security,  # Use actual security object
                        "date": date,
                        "type": transaction_type,
                        "currency": currency,
                        "price": price,
                        "quantity": quantity,
                        "cash_flow": dividend,
                        "commission": commission,
                    }

                    # Check for duplicates
                    exists = await transaction_exists(transaction_data)

                    processed += 1
                    yield {
                        "status": "progress",
                        "current": processed,
                        "progress": (processed / total_potential_transactions) * 100,
                        "message": f"Processing transaction {processed}",
                    }

                    if exists:
                        duplicate_count += 1
                        continue

                    if confirm_every:
                        # processed += 1
                        yield {
                            "status": "transaction_confirmation",
                            "data": transaction_data,
                        }
                    else:
                        yield {
                            "status": "add_transaction",
                            "data": transaction_data,
                        }

                except Exception as e:
                    import_errors += 1
                    yield {"error": f"Error processing transaction: {str(e)}"}
                    continue

        yield {
            "status": "complete",
            "data": {
                "totalTransactions": total_potential_transactions,
                "importedTransactions": 0,
                "skippedTransactions": 0,
                "duplicateTransactions": duplicate_count,
                "importErrors": import_errors,
            },
        }

    except Exception as e:
        logger.error(f"Error in parse_galaxy_account_security_transactions: {str(e)}")
        yield {"status": "critical_error", "message": f"Error during import: {str(e)}"}


async def _process_galaxy_securities(df, user):
    """Process all securities in the Excel file before handling transactions."""
    security_columns = []

    logger.debug("Starting security processing phase")
    for i in range(len(df.columns)):
        if pd.notna(df.iloc[1, i]):
            security_name = df.iloc[1, i]
            isin = df.iloc[2, i]
            logger.debug(f"Processing security: {security_name} ({isin})")

            try:
                # First try to get security with all conditions
                security = await database_sync_to_async(Assets.objects.get)(
                    name=security_name,
                    ISIN=isin,
                    investors=user,
                )
                logger.debug(f"Found existing security with all relationships: {security}")
                security_columns.append(i)

                # Yield progress update
                yield {
                    "status": "progress",
                    "message": f"Checked existing security: {security_name}",
                    # 'security': security_name
                }

            except Assets.DoesNotExist:
                try:
                    # Check if security exists without relationships
                    security = await database_sync_to_async(Assets.objects.get)(
                        name=security_name, ISIN=isin
                    )

                    # Add relationships
                    @database_sync_to_async
                    def add_relationships(security, user):
                        security.investors.add(user)
                        return security

                    await add_relationships(security, user)
                    security_columns.append(i)
                    logger.debug(f"Added relationships for existing security: {security_name}")

                    # Yield progress update
                    yield {
                        "status": "progress",
                        "message": f"Added: {security_name}",
                        # 'security': security_name
                    }

                except Assets.DoesNotExist:
                    # Try to create security using MICEX data
                    security = await create_security_from_micex(
                        security_name,
                        isin,
                        user,
                        instrument_type=InstrumentType.INSTRUMENT_TYPE_SHARE,
                    )
                    if security:
                        security_columns.append(i)
                        yield {
                            "status": "progress",
                            "message": f"Created new security: {security_name}",
                            # 'security': security_name
                        }
                    else:
                        yield {
                            "status": "progress",
                            "message": f"Failed to create security: {security_name}",
                            # 'security': security_name,
                            # 'error': True
                        }
                        continue

    # Return list of valid column indices
    yield {
        "status": "security_processing_complete",
        "valid_columns": security_columns,
        "message": f"Found {len(security_columns)} valid securities",
    }


# =============================================================================
# Security creators (formerly in core/import_utils.py)
# =============================================================================


async def create_security_from_tinkoff(
    security_name,
    isin,
    ticker,
    user,
    instrument_type,
    instrument_uid=None,
    date_to_save=None,
):
    """
    Create a new security using T-Bank (Tinkoff) data with type-specific API methods.

    Used when security is not found in MICEX (e.g., matured bonds, delisted securities).
    Fetches comprehensive metadata using bond_by, share_by, etf_by, future_by, or option_by.

    Args:
        security_name: Name of the security from Tinkoff
        isin: ISIN code
        ticker: Ticker symbol
        user: CustomUser instance
        instrument_type: Tinkoff InstrumentType enum
        instrument_uid: Tinkoff instrument UID (required for fetching metadata)
        date_to_save: Date to save the bond redemption history

    Returns:
        Assets instance or None
    """
    try:
        logger.info(
            f"Creating security from T-Bank data: {security_name} ({isin}), UID: {instrument_uid}"
        )

        if not instrument_uid:
            logger.warning(f"No instrument_uid provided for {security_name}, creating basic asset")
            # Fallback to basic creation without metadata
            return await _create_basic_tbank_asset(
                security_name, isin, ticker, user, instrument_type, None
            )

        # Get T-Bank token
        token = await get_user_token(user)

        # Fetch instrument-specific data
        instrument_data = None

        try:
            with Client(token) as client:
                if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
                    response = client.instruments.bond_by(id_type=3, id=instrument_uid)
                    instrument_data = response.instrument
                elif instrument_type == InstrumentType.INSTRUMENT_TYPE_SHARE:
                    response = client.instruments.share_by(id_type=3, id=instrument_uid)
                    instrument_data = response.instrument
                elif instrument_type == InstrumentType.INSTRUMENT_TYPE_ETF:
                    response = client.instruments.etf_by(id_type=3, id=instrument_uid)
                    instrument_data = response.instrument
                elif instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES:
                    response = client.instruments.future_by(id_type=3, id=instrument_uid)
                    instrument_data = response.instrument
                elif instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION:
                    response = client.instruments.option_by(id_type=3, id=instrument_uid)
                    instrument_data = response.instrument
                else:
                    logger.warning(
                        f"Unsupported instrument type for {security_name}: {instrument_type}"
                    )
                    return await _create_basic_tbank_asset(
                        security_name,
                        isin,
                        ticker,
                        user,
                        instrument_type,
                        instrument_uid,
                    )
        except Exception as e:
            logger.error(f"Error fetching instrument data from T-Bank: {e}")
            return await _create_basic_tbank_asset(
                security_name, isin, ticker, user, instrument_type, instrument_uid
            )

        # Create asset with metadata
        @database_sync_to_async
        def create_asset_with_metadata():
            # Map to asset type
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_SHARE:
                asset_type = ASSET_TYPE_CHOICES[0][0]
                exposure = EXPOSURE_CHOICES[0][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_ETF:
                asset_type = ASSET_TYPE_CHOICES[2][0]
                exposure = EXPOSURE_CHOICES[0][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
                asset_type = ASSET_TYPE_CHOICES[1][0]
                exposure = EXPOSURE_CHOICES[1][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES:
                asset_type = ASSET_TYPE_CHOICES[4][0]
                exposure = EXPOSURE_CHOICES[4][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION:
                asset_type = ASSET_TYPE_CHOICES[5][0]
                exposure = EXPOSURE_CHOICES[4][0]
            else:
                asset_type = ASSET_TYPE_CHOICES[0][0]
                exposure = EXPOSURE_CHOICES[0][0]

            # Build bond metadata fields up front so the helper can upsert them
            # idempotently (and link the user) in a single call.
            bond_data = {}
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND and instrument_data:
                # Extract bond-specific fields
                if hasattr(instrument_data, "initial_nominal") and instrument_data.initial_nominal:
                    bond_data["initial_notional"] = quotation_to_decimal(
                        instrument_data.initial_nominal
                    )
                    # Capture the nominal currency from MoneyValue
                    if hasattr(instrument_data.initial_nominal, "currency"):
                        bond_data["nominal_currency"] = (
                            instrument_data.initial_nominal.currency.upper()
                        )

                if (
                    hasattr(instrument_data, "placement_date")
                    and instrument_data.placement_date
                ):
                    bond_data["issue_date"] = instrument_data.placement_date.date()

                if hasattr(instrument_data, "maturity_date") and instrument_data.maturity_date:
                    bond_data["maturity_date"] = instrument_data.maturity_date.date()

                if hasattr(instrument_data, "coupon_quantity_per_year"):
                    bond_data["coupon_frequency"] = (
                        instrument_data.coupon_quantity_per_year
                    )

                # Detect bond type from flags
                if hasattr(instrument_data, "floating_coupon_flag"):
                    if instrument_data.floating_coupon_flag:
                        bond_data["bond_type"] = "FLOATING"
                    elif bond_data.get("coupon_frequency", 0) == 0:
                        bond_data["bond_type"] = "ZERO_COUPON"
                    else:
                        bond_data["bond_type"] = "FIXED"

                # Amortization flag
                if hasattr(instrument_data, "amortization_flag"):
                    bond_data["is_amortizing"] = instrument_data.amortization_flag

            # Resolve-or-create the asset. The helper links the user (instead of
            # asset.investors.add) and upserts BondMetadata via update_or_create
            # (instead of the non-idempotent BondMetadata.objects.create).
            resolved_isin = isin if isin else instrument_data.isin
            result = resolve_or_create_asset(
                user=user,
                isin=resolved_isin,
                currency=instrument_data.currency,
                submitted_fields={
                    "type": asset_type,
                    "name": instrument_data.name,
                    "exposure": exposure,
                    "restricted": False,
                    "data_source": "TBANK",
                    "secid": instrument_data.ticker if hasattr(instrument_data, "ticker") else None,
                    "tbank_instrument_uid": instrument_uid,
                    **bond_data,
                },
                mode="silent",
            )
            asset = result.asset
            if result.created and bond_data:
                logger.info(f"Created BondMetadata from T-Bank for {asset.name}")

            # Create type-specific metadata (only futures/options here; bond
            # metadata is handled by resolve_or_create_asset above).
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES and instrument_data:
                future_data = {}

                if (
                    hasattr(instrument_data, "expiration_date")
                    and instrument_data.expiration_date
                ):
                    future_data["expiration_date"] = (
                        instrument_data.expiration_date.date()
                    )

                if hasattr(instrument_data, "basic_asset"):
                    future_data["underlying_asset"] = instrument_data.basic_asset

                if hasattr(instrument_data, "name"):
                    future_data["contract_name"] = instrument_data.name

                if hasattr(instrument_data, "lot"):
                    future_data["lot_size"] = Decimal(str(instrument_data.lot))

                if future_data:
                    FutureMetadata.objects.create(asset=asset, **future_data)
                    logger.info(f"Created FutureMetadata from T-Bank for {asset.name}")

            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION and instrument_data:
                option_data = {}

                if (
                    hasattr(instrument_data, "expiration_date")
                    and instrument_data.expiration_date
                ):
                    option_data["expiration_date"] = (
                        instrument_data.expiration_date.date()
                    )

                if hasattr(instrument_data, "strike_price") and instrument_data.strike_price:
                    option_data["strike_price"] = quotation_to_decimal(instrument_data.strike_price)

                if hasattr(instrument_data, "direction"):
                    # OptionDirection: CALL=1, PUT=2
                    option_data["option_type"] = "CALL" if instrument_data.direction == 1 else "PUT"

                if hasattr(instrument_data, "basic_asset"):
                    option_data["underlying_asset"] = instrument_data.basic_asset

                if option_data:
                    OptionMetadata.objects.create(asset=asset, **option_data)
                    logger.info(f"Created OptionMetadata from T-Bank for {asset.name}")

            return asset

        asset = await create_asset_with_metadata()
        logger.info(
            f"Successfully created asset from T-Bank with metadata: {asset.name} ({asset.ISIN})"
        )

        # For bonds, fetch and save redemption history to NotionalHistory
        if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND and instrument_uid:
            try:
                entries_count = await save_bond_redemption_history(
                    asset, instrument_uid, user, date_to_save
                )
                if entries_count > 0:
                    logger.info(
                        f"Saved {entries_count} bond redemption events for {asset.name} "
                        f"up to {date_to_save if date_to_save else datetime.now()}"
                    )
            except Exception as e:
                logger.warning(
                    f"Could not save bond redemption history for {asset.name}: {e}. "
                    f"This is not critical, continuing..."
                )

            # Fetch and cache bond coupon schedule for ACI calculations
            try:
                success = await fetch_and_cache_bond_coupon_schedule(
                    asset, user, force_refresh=False
                )
                if success:
                    logger.info(f"Successfully fetched and cached coupon schedule for {asset.name}")
                else:
                    logger.warning(f"Could not fetch coupon schedule for {asset.name}")
            except Exception as e:
                logger.warning(
                    f"Error fetching coupon schedule for {asset.name}: {e}. "
                    f"This is not critical, continuing..."
                )

        return asset

    except Exception as e:
        logger.error(f"Error creating security from T-Bank data: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


async def _create_basic_tbank_asset(
    security_name, isin, ticker, user, instrument_type, instrument_uid
):
    """Fallback: Create basic asset without metadata."""
    try:

        @database_sync_to_async
        def create_basic_asset():
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_SHARE:
                asset_type = ASSET_TYPE_CHOICES[0][0]
                exposure = EXPOSURE_CHOICES[0][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_ETF:
                asset_type = ASSET_TYPE_CHOICES[2][0]
                exposure = EXPOSURE_CHOICES[0][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
                asset_type = ASSET_TYPE_CHOICES[1][0]
                exposure = EXPOSURE_CHOICES[1][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES:
                asset_type = ASSET_TYPE_CHOICES[4][0]
                exposure = EXPOSURE_CHOICES[4][0]
            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION:
                asset_type = ASSET_TYPE_CHOICES[5][0]
                exposure = EXPOSURE_CHOICES[4][0]
            else:
                asset_type = ASSET_TYPE_CHOICES[0][0]
                exposure = EXPOSURE_CHOICES[0][0]

            result = resolve_or_create_asset(
                user=user,
                isin=isin,
                currency="RUB",
                submitted_fields={
                    "type": asset_type,
                    "ticker": ticker,
                    "name": security_name,
                    "exposure": exposure,
                    "restricted": False,
                    "data_source": "TBANK",
                    "secid": None,
                    "tbank_instrument_uid": instrument_uid,
                },
                mode="silent",
            )
            return result.asset

        return await create_basic_asset()
    except Exception as e:
        logger.error(f"Error in fallback asset creation: {e}")
        return None


async def _enhance_bond_metadata_from_tbank(asset, isin, user):
    """
    Enhance bond metadata with T-Bank API data.

    Fetches accurate amortization flag and coupon type (floating vs fixed).

    Args:
        asset: Assets instance
        isin: Bond ISIN
        user: User object for T-Bank API access

    Returns:
        str: instrument_uid if successful, None otherwise
    """
    try:
        # Get T-Bank token
        token = await get_user_token(user)

        # Fetch bond data from T-Bank using class_code + ISIN
        with Client(token) as client:
            try:
                # id_type=2 is for ticker which is ISIN for bonds
                # TQCB is the standard board for corporate bonds
                response = client.instruments.bond_by(id_type=2, id=isin, class_code="TQCB")
                bond_instrument = response.instrument

                # Update BondMetadata with T-Bank data
                @database_sync_to_async
                def update_bond_metadata():
                    try:
                        bond_meta = asset.bond_metadata
                        updated = False

                        # Update bond type from floating_coupon_flag
                        if hasattr(bond_instrument, "floating_coupon_flag"):
                            if bond_instrument.floating_coupon_flag:
                                bond_meta.bond_type = "FLOATING"
                                updated = True
                                logger.info(
                                    f"Updated bond type to FLOATING for {asset.name} "
                                    f"from T-Bank API"
                                )
                            elif bond_meta.bond_type == "FIXED":
                                # Keep as FIXED if not floating and not zero coupon
                                pass

                        # Update amortization flag (authoritative from T-Bank)
                        if hasattr(bond_instrument, "amortization_flag"):
                            bond_meta.is_amortizing = bond_instrument.amortization_flag
                            updated = True
                            logger.info(
                                f"Updated is_amortizing={bond_instrument.amortization_flag} "
                                f"for {asset.name} from T-Bank API"
                            )

                        # Update initial_notional if missing
                        if not bond_meta.initial_notional and hasattr(
                            bond_instrument, "initial_nominal"
                        ):
                            if bond_instrument.initial_nominal:
                                bond_meta.initial_notional = quotation_to_decimal(
                                    bond_instrument.initial_nominal
                                )
                                # Also capture nominal currency if available
                                if hasattr(bond_instrument.initial_nominal, "currency"):
                                    bond_meta.nominal_currency = (
                                        bond_instrument.initial_nominal.currency.upper()
                                    )
                                updated = True

                        if updated:
                            bond_meta.save()
                            logger.info(f"Enhanced BondMetadata for {asset.name} from T-Bank API")

                    except Exception as e:
                        logger.error(
                            f"Error updating BondMetadata for {asset.name}: {e}",
                            exc_info=True,
                        )

                await update_bond_metadata()

                # Return instrument_uid for further use
                return bond_instrument.uid if hasattr(bond_instrument, "uid") else None

            except Exception as e:
                # If bond not found in TQCB, try other boards or just log
                error_msg = str(e)
                if "50002" in error_msg or "not found" in error_msg.lower():
                    logger.info(
                        f"Bond {isin} not found in T-Bank TQCB board, "
                        f"keeping MICEX metadata for {asset.name}"
                    )
                else:
                    logger.warning(f"Error fetching bond from T-Bank for {asset.name}: {e}")
                return None

    except Exception as e:
        logger.error(
            f"Error enhancing bond metadata from T-Bank for {asset.name}: {e}",
            exc_info=True,
        )
        return None


async def fetch_security_from_micex_targeted(security_identifier, instrument_type):
    """
    Fetch security data from MICEX using targeted API endpoint.

    Args:
        security_identifier: ISIN for bonds, SECID for stocks/ETFs/futures/options
        instrument_type: InstrumentType enum

    Returns:
        dict: Security data or None if not found
    """
    try:
        # Use targeted endpoint
        url = f"https://iss.moex.com/iss/securities/{security_identifier}.json"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to fetch security from MICEX: {security_identifier}, "
                        f"status={response.status}"
                    )
                    return None

                data = await response.json()

                # Parse description data (contains main security info)
                if "description" not in data or not data["description"]["data"]:
                    logger.warning(f"No description data for security: {security_identifier}")
                    return None

                # Convert to dict for easier access
                desc_columns = data["description"]["columns"]
                desc_data = data["description"]["data"]

                security_info = {}
                for row in desc_data:
                    field_name = row[desc_columns.index("name")]
                    field_value = row[desc_columns.index("value")]
                    security_info[field_name] = field_value

                # Get the SECID if not already the identifier
                secid = security_info.get("SECID", security_identifier)

                logger.info(
                    f"Fetched security from MICEX: {security_info.get('NAME', security_identifier)}"
                )
                return {
                    "secid": secid,
                    "isin": security_info.get("ISIN"),
                    "name": security_info.get("NAME") or security_info.get("SHORTNAME"),
                    "short_name": security_info.get("SHORTNAME"),
                    "currency": (
                        "RUB"
                        if security_info.get("FACEUNIT") == "SUR"
                        else security_info.get("FACEUNIT", "RUB")
                    ),
                    "data": security_info,  # Full data for type-specific processing
                    "instrument_type": instrument_type,
                }

    except Exception as e:
        logger.error(f"Error fetching security from MICEX: {e}", exc_info=True)
        return None


async def create_security_from_micex(
    security_name, isin, user, instrument_type, ticker=None, date_to_save=None
):
    """
    Create a new security using targeted MICEX API request.

    Automatically creates metadata for bonds, futures, and options.

    Args:
        security_name: Name of the security
        isin: ISIN code
        user: User object
        instrument_type: InstrumentType enum
        ticker: Ticker symbol (for non-bonds, used for MICEX lookup)
    """
    try:
        # Determine the identifier to use
        # For bonds: use ISIN, for others: use ticker (more reliable for MICEX)
        if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
            identifier = isin
        else:
            # For stocks/ETFs/futures/options: use ticker if available, fallback to ISIN
            identifier = ticker if ticker else isin

        # Fetch security data from MICEX
        security_data = await fetch_security_from_micex_targeted(identifier, instrument_type)

        if not security_data:
            logger.warning(f"Security not found in MICEX: {security_name} ({isin})")
            return None

        # Determine asset type and exposure
        if instrument_type == InstrumentType.INSTRUMENT_TYPE_SHARE:
            asset_type = ASSET_TYPE_CHOICES[0][0]  # Stock
            exposure = EXPOSURE_CHOICES[0][0]  # Equity
        elif instrument_type == InstrumentType.INSTRUMENT_TYPE_ETF:
            asset_type = ASSET_TYPE_CHOICES[2][0]  # ETF
            exposure = EXPOSURE_CHOICES[0][0]  # Equity
        elif instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
            asset_type = ASSET_TYPE_CHOICES[1][0]  # Bond
            exposure = EXPOSURE_CHOICES[1][0]  # Fixed Income
        elif instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES:
            asset_type = ASSET_TYPE_CHOICES[4][0]  # Future
            exposure = EXPOSURE_CHOICES[4][0]  # Derivatives
        elif instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION:
            asset_type = ASSET_TYPE_CHOICES[5][0]  # Option
            exposure = EXPOSURE_CHOICES[4][0]  # Derivatives
        else:
            logger.error(f"Unsupported instrument type: {instrument_type}")
            return None

        # Create the asset
        @database_sync_to_async
        def create_asset_and_metadata():
            # Build bond metadata fields up front so the helper can upsert them
            # idempotently (and link the user) in a single call.
            data = security_data["data"]
            bond_data = {}
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
                # Parse dates
                if data.get("ISSUEDATE"):
                    try:
                        bond_data["issue_date"] = datetime.strptime(
                            data["ISSUEDATE"], "%Y-%m-%d"
                        ).date()
                    except (ValueError, TypeError):
                        pass

                if data.get("MATDATE"):
                    try:
                        bond_data["maturity_date"] = datetime.strptime(
                            data["MATDATE"], "%Y-%m-%d"
                        ).date()
                    except (ValueError, TypeError):
                        pass

                # Parse numeric fields
                if data.get("INITIALFACEVALUE"):
                    try:
                        bond_data["initial_notional"] = Decimal(str(data["INITIALFACEVALUE"]))
                    except (ValueError, TypeError, InvalidOperation):
                        pass

                if data.get("COUPONPERCENT"):
                    try:
                        bond_data["coupon_rate"] = Decimal(str(data["COUPONPERCENT"]))
                    except (ValueError, TypeError, InvalidOperation):
                        pass

                if data.get("COUPONFREQUENCY"):
                    try:
                        bond_data["coupon_frequency"] = int(data["COUPONFREQUENCY"])
                    except (ValueError, TypeError):
                        pass

                # Nominal currency from FACEUNIT
                if data.get("FACEUNIT"):
                    # MICEX uses 'SUR' for RUB in bond face values
                    nominal_curr = data["FACEUNIT"]
                    bond_data["nominal_currency"] = "RUB" if nominal_curr == "SUR" else nominal_curr

                # Determine if bond is amortizing (check if current face value < initial)
                if data.get("FACEVALUE") and data.get("INITIALFACEVALUE"):
                    try:
                        current_face = Decimal(str(data["FACEVALUE"]))
                        initial_face = Decimal(str(data["INITIALFACEVALUE"]))
                        bond_data["is_amortizing"] = current_face < initial_face
                    except (ValueError, TypeError, InvalidOperation):
                        bond_data["is_amortizing"] = False
                else:
                    bond_data["is_amortizing"] = False

                # Bond type - determine from coupon percent
                # Zero coupon bonds have COUPONPERCENT = 0
                # For floating vs fixed, we'll fetch from T-Bank API below
                if data.get("COUPONPERCENT"):
                    try:
                        coupon_pct = Decimal(str(data["COUPONPERCENT"]))
                        if coupon_pct == 0:
                            bond_data["bond_type"] = "ZERO_COUPON"
                        else:
                            # Default to FIXED, will be updated by T-Bank API below
                            bond_data["bond_type"] = "FIXED"
                    except (ValueError, TypeError, InvalidOperation):
                        bond_data["bond_type"] = "FIXED"
                else:
                    bond_data["bond_type"] = "FIXED"

            # Resolve-or-create the asset. The helper links the user (instead of
            # asset.investors.add) and upserts BondMetadata via update_or_create
            # (instead of the non-idempotent BondMetadata.objects.create).
            resolved_isin = security_data["isin"] or isin
            result = resolve_or_create_asset(
                user=user,
                isin=resolved_isin,
                currency=security_data["currency"],
                submitted_fields={
                    "type": asset_type,
                    "name": security_data["name"],
                    "ticker": ticker,
                    "exposure": exposure,
                    "restricted": False,
                    "data_source": "MICEX",
                    "secid": security_data["secid"],
                    **bond_data,
                },
                mode="silent",
            )
            asset = result.asset
            if result.created and bond_data:
                logger.info(f"Created BondMetadata for {asset.name}: {bond_data}")

            # Create type-specific metadata (only futures/options here; bond
            # metadata is handled by resolve_or_create_asset above).
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES:
                # Create FutureMetadata
                future_data = {}

                if data.get("LSTDELDATE"):
                    try:
                        future_data["expiration_date"] = datetime.strptime(
                            data["LSTDELDATE"], "%Y-%m-%d"
                        ).date()
                    except (ValueError, TypeError):
                        pass

                if data.get("ASSETCODE"):
                    future_data["underlying_asset"] = data["ASSETCODE"]

                if data.get("CONTRACTNAME"):
                    future_data["contract_name"] = data["CONTRACTNAME"]

                if data.get("LOTSIZE"):
                    try:
                        future_data["lot_size"] = Decimal(str(data["LOTSIZE"]))
                    except (ValueError, TypeError, InvalidOperation):
                        pass

                if future_data:
                    FutureMetadata.objects.create(asset=asset, **future_data)
                    logger.info(f"Created FutureMetadata for {asset.name}")

            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION:
                # Create OptionMetadata
                option_data = {}

                if data.get("LSTDELDATE"):
                    try:
                        option_data["expiration_date"] = datetime.strptime(
                            data["LSTDELDATE"], "%Y-%m-%d"
                        ).date()
                    except (ValueError, TypeError):
                        pass

                if data.get("STRIKE"):
                    try:
                        option_data["strike_price"] = Decimal(str(data["STRIKE"]))
                    except (ValueError, TypeError, InvalidOperation):
                        pass

                if data.get("OPTIONTYPE"):
                    option_data["option_type"] = "CALL" if data["OPTIONTYPE"] == "C" else "PUT"

                if data.get("ASSETCODE"):
                    option_data["underlying_asset"] = data["ASSETCODE"]

                if option_data:
                    OptionMetadata.objects.create(asset=asset, **option_data)
                    logger.info(f"Created OptionMetadata for {asset.name}")

            return asset

        asset = await create_asset_and_metadata()
        logger.info(
            f"Created new asset from MICEX: {asset.name} ({asset.ISIN}) "
            f"with metadata and user relationships"
        )

        # For bonds, also fetch from T-Bank API to get accurate amortization and coupon type
        if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
            instrument_uid = await _enhance_bond_metadata_from_tbank(asset, isin, user)

            # If we got the instrument_uid, also save bond redemption history
            if instrument_uid:
                asset.tinkoff_instrument_uid = instrument_uid
                asset.save()

                # Save bond redemption history
                try:
                    entries_count = await save_bond_redemption_history(
                        asset, instrument_uid, user, date_to_save
                    )
                    if entries_count > 0:
                        logger.info(
                            f"Saved {entries_count} bond redemption events for {asset.name} "
                            f"up to {date_to_save if date_to_save else datetime.now()}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Could not save bond redemption history for {asset.name}: {e}. "
                        f"This is not critical, continuing..."
                    )

                # Fetch and cache bond coupon schedule for ACI calculations
                try:
                    success = await fetch_and_cache_bond_coupon_schedule(
                        asset, user, force_refresh=False
                    )
                    if success:
                        logger.info(
                            f"Successfully fetched and cached coupon schedule for {asset.name}"
                        )
                    else:
                        logger.warning(f"Could not fetch coupon schedule for {asset.name}")
                except Exception as e:
                    logger.warning(
                        f"Error fetching coupon schedule for {asset.name}: {e}. "
                        f"This is not critical, continuing..."
                    )

        return asset

    except Exception as e:
        logger.error(f"Error creating security from MICEX: {str(e)}", exc_info=True)
        return None


# =============================================================================
# Account matching (formerly in core/import_utils.py)
# =============================================================================


async def match_tinkoff_broker_account(
    broker: Brokers, user
) -> Tuple[Dict[str, Dict], List[Dict], List[Dict]]:
    """
    Match broker accounts with existing database accounts.

    Args:
        broker: Brokers model instance
        user: CustomUser instance

    Returns:
        Tuple of:
        - matched_pairs: Dict with matched accounts {"tinkoff_account_id": matched_db_account}
        - unmatched_tinkoff: List of unmatched Tinkoff accounts
        - unmatched_db: List of unmatched database accounts
    """
    try:
        # Get broker API instance
        broker_api = await _get_broker_api()(broker)
        if not broker_api:
            raise ValueError(f"Failed to initialize API for broker {broker.name}")

        # Connect to broker API
        connected = await broker_api.connect(user)
        if not connected:
            raise ValueError(f"Failed to connect to {broker.name} API")

        try:
            # Get accounts from Tinkoff API using proper context manager pattern
            from t_tech.invest import Client

            token = await get_user_token(user)

            tinkoff_accounts = []

            with Client(token) as client:
                accounts_response = client.users.get_accounts()

                for acc in accounts_response.accounts:
                    tinkoff_accounts.append(
                        {
                            "id": acc.id,
                            "name": acc.name,
                            "type": str(acc.type).replace("ACCOUNT_TYPE_", ""),
                            "status": str(acc.status).replace("ACCOUNT_STATUS_", ""),
                            "opened_date": acc.opened_date.strftime("%Y-%m-%d"),
                            "access_level": str(acc.access_level),
                        }
                    )

            # Get existing database accounts
            db_accounts = await database_sync_to_async(list)(
                Accounts.objects.filter(broker=broker, is_active=True).values(
                    "id", "name", "native_id", "comment"
                )
            )

            # Initialize result containers
            matched_pairs = {}
            unmatched_tinkoff = []
            unmatched_db = db_accounts.copy()  # Start with all DB accounts as unmatched

            # Find matches by native_id
            for tinkoff_acc in tinkoff_accounts:
                matched_db_account = None

                for db_acc in db_accounts:
                    if db_acc["native_id"] == tinkoff_acc["id"]:
                        matched_db_account = {
                            "id": db_acc["id"],
                            "name": db_acc["name"],
                            "native_id": db_acc["native_id"],
                            "comment": db_acc["comment"],
                            "source": "database",
                        }
                        # Remove matched DB account from unmatched list
                        unmatched_db.remove(db_acc)  # Remove matched DB account directly
                        break  # Stop searching after finding the first match

                if matched_db_account:
                    matched_pairs[tinkoff_acc["id"]] = {
                        "tinkoff_account": tinkoff_acc,
                        "db_account": matched_db_account,
                    }
                else:
                    unmatched_tinkoff.append(tinkoff_acc)

            # Format unmatched lists for frontend
            formatted_unmatched_tinkoff = [
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "type": acc["type"],
                    "status": acc["status"],
                    "opened_date": acc["opened_date"],
                    "source": "tinkoff",
                }
                for acc in unmatched_tinkoff
            ]

            formatted_unmatched_db = [
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "native_id": acc["native_id"],
                    "comment": acc["comment"],
                    "source": "database",
                }
                for acc in unmatched_db
            ]

            return matched_pairs, formatted_unmatched_tinkoff, formatted_unmatched_db

        finally:
            await broker_api.disconnect()

    except Exception as e:
        logger.error(f"Error matching broker accounts: {str(e)}")
        raise ValueError(f"Failed to match broker accounts: {str(e)}")


async def check_broker_token_active(broker: Brokers) -> bool:
    """
    Check if broker has an active token by attempting to connect to the API.

    Args:
        broker: Broker object to check

    Returns:
        bool: True if token is active, False otherwise
    """
    try:
        # Get broker API instance
        broker_api = await _get_broker_api()(broker)
        if not broker_api:
            logger.error(f"Failed to initialize {broker.name} API")
            return False

        # Try to connect
        try:
            is_connected = await broker_api.connect(broker.investor)
            if is_connected:
                is_valid = await broker_api.validate_connection()
                return is_valid
            return False

        finally:
            # Always disconnect after checking
            await broker_api.disconnect()

    except Exception as e:
        logger.error(f"Error checking broker token: {str(e)}")
        return False


# =============================================================================
# Tinkoff / T-Bank helpers (formerly in core/tinkoff_utils.py)
# =============================================================================


async def get_user_token(user, sandbox_mode=False):
    """Get user's Tinkoff API token."""
    try:
        token = await database_sync_to_async(TinkoffApiToken.objects.get)(
            user=user, token_type="read_only", sandbox_mode=sandbox_mode, is_active=True
        )
        return token.get_token(user)
    except TinkoffApiToken.DoesNotExist:
        raise ValueError("No active Tinkoff API token found for user")
    except Exception as e:
        logger.error(f"Error getting Tinkoff token: {str(e)}")
        raise


async def get_bond_initial_notional(instrument_uid, user):
    """
    Fetch the initial notional value of a bond from T-Bank API.

    Args:
        instrument_uid: T-Bank instrument UID for the bond
        user: CustomUser instance (to get API token)

    Returns:
        Decimal: The initial notional value per bond, or None if not found.
    """
    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return None

        with Client(token) as client:
            response = client.instruments.bond_by(id_type=3, id=instrument_uid)
            if response.instrument and response.instrument.initial_nominal:
                initial_notional = quotation_to_decimal(response.instrument.initial_nominal)
                logger.debug(f"Fetched initial notional for {instrument_uid}: {initial_notional}")
                return initial_notional
            else:
                logger.warning(f"No initial_nominal found in bond response for {instrument_uid}")
                return None

    except RequestError as e:
        logger.error(f"T-Bank API error fetching bond info for {instrument_uid}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error fetching initial notional for {instrument_uid}: {str(e)}")
        return None


async def get_bond_notional_at_date(instrument_uid, date, user, initial_notional):
    """
    Calculate the remaining notional value of a bond at a given date based on redemption history.

    Uses T-Bank's bond events API to fetch all MTY (maturity/redemption) events and calculates
    the remaining notional by subtracting all redemptions that occurred before or on the given date.

    Bond Event Structure:
    - event.value (Quotation): Percentage of par redeemed (e.g., 12.5% or 0.125)
    - event.pay_one_bond (MoneyValue): Actual cash paid per bond
    - event.event_date: Date of redemption
    - event.operation_type: 'OA' (partial amortization), 'CA' (call option), 'CM' (full maturity)

    Example:
        If a bond with 1000 initial notional had two redemptions:
        - 2022-08-19: 12.5% redeemed
        - 2022-11-18: 12.5% redeemed

        On 2022-12-01, remaining notional = 1000 * (1 - 0.125 - 0.125) = 750

    Args:
        instrument_uid: T-Bank instrument UID for the bond
        date: The date for which to calculate notional (datetime.date or datetime)
        user: CustomUser instance (to get API token)
        initial_notional: Initial par value of the bond

    Returns:
        Decimal: The remaining notional value per bond at the given date
    """
    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return initial_notional

        # Convert date to datetime if needed
        if isinstance(date, datetime):
            target_date = date
        else:
            # Use timezone-aware datetime to avoid warnings
            from django.utils import timezone

            target_date = timezone.make_aware(datetime.combine(date, datetime.min.time()))

        logger.debug(
            f"Fetching bond events for instrument {instrument_uid} up to {target_date.date()}"
        )

        with Client(token) as client:
            # Fetch all MTY (maturity/redemption) events from inception to target date
            request = GetBondEventsRequest(
                from_=datetime(1980, 1, 1),
                to=target_date,
                instrument_id=instrument_uid,
                type=EventType.EVENT_TYPE_MTY,
            )

            response = client.instruments.get_bond_events(request)

            if not response.events:
                logger.debug(
                    f"No redemption events found for bond {instrument_uid}, using initial notional"
                )
                return initial_notional

            # Calculate total redeemed amount
            total_redeemed_percentage = Decimal(0)

            for event in response.events:
                if event.event_date.date() <= target_date.date():
                    # event.value is a Quotation representing percentage of par redeemed
                    redeemed_pct = quotation_to_decimal(event.value)
                    total_redeemed_percentage += redeemed_pct

                    logger.debug(
                        f"Redemption on {event.event_date.date()}: "
                        f"{redeemed_pct}% (pay_one_bond: {event.pay_one_bond.units})"
                    )

            # Calculate remaining notional
            remaining_percentage = Decimal(100) - total_redeemed_percentage

            remaining_notional = initial_notional * (remaining_percentage / Decimal(100))

            logger.info(
                f"Bond {instrument_uid} at {target_date.date()}: "
                f"redeemed {total_redeemed_percentage}%, "
                f"remaining notional: {remaining_notional} (from {initial_notional})"
            )

            return remaining_notional

    except RequestError as e:
        logger.error(f"T-Bank API error fetching bond events for {instrument_uid}: {str(e)}")
        return initial_notional
    except Exception as e:
        logger.error(f"Error calculating bond notional for {instrument_uid} at {date}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return initial_notional


async def fetch_and_cache_bond_coupon_schedule(asset: Assets, user, force_refresh=False):
    """
    Fetch bond coupon schedule from T-Bank API and cache it in BondCouponSchedule model.

    For fixed-rate bonds, schedule is cached indefinitely as it doesn't change.
    Use force_refresh=True for floating-rate bonds or when coupon_amount is None.

    Args:
        asset: Assets instance (must be a bond with tbank_instrument_uid)
        user: CustomUser instance (to get API token)
        force_refresh: If True, delete existing schedule and fetch fresh data
                      (use when coupon_amount is empty for floating-rate bonds)

    Returns:
        bool: True if schedule was fetched and cached successfully, False otherwise
    """

    from channels.db import database_sync_to_async

    # Get asset data in sync context (cache frequently used fields)
    asset_name = await database_sync_to_async(lambda: asset.name)()
    is_bond = await database_sync_to_async(lambda: asset.is_bond)()

    if not is_bond:
        logger.warning(f"Asset {asset_name} is not a bond")
        return False

    # Check if asset has T-Bank instrument UID
    has_uid = await database_sync_to_async(lambda: asset.tbank_instrument_uid)()

    if not has_uid:
        # Try to get instrument UID from T-Bank API
        instrument_uid = await get_instrument_uid(asset, user)
        if instrument_uid:
            # Save the UID to the asset
            @database_sync_to_async
            def save_uid():
                asset.tbank_instrument_uid = instrument_uid
                asset.save()

            await save_uid()
            # Update has_uid flag since we just saved it
            has_uid = instrument_uid
        else:
            logger.warning(f"Bond {asset_name} has no T-Bank instrument UID")
            return False

    try:
        # Check if we already have a schedule
        # For fixed-rate bonds, schedule doesn't change so we cache indefinitely
        if not force_refresh:
            schedule_exists = await database_sync_to_async(
                lambda: BondCouponSchedule.objects.filter(asset=asset).exists()
            )()

            if schedule_exists:
                logger.debug(f"Coupon schedule exists for {asset_name}, skipping fetch")
                return True

        # Fetch from T-Bank API
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return False

        bond_meta = await database_sync_to_async(lambda: asset.bond_metadata)()
        if not bond_meta:
            logger.warning(f"No bond metadata for {asset_name}")
            return False

        # Determine date range (from issue_date or 1 year ago, to maturity or 5 years ahead)
        from_date = bond_meta.issue_date or (datetime.now().date() - timedelta(days=365))
        to_date = bond_meta.maturity_date or (datetime.now().date() + timedelta(days=365 * 5))

        logger.info(f"Fetching coupon schedule for {asset_name} from {from_date} to {to_date}")

        # Get instrument UID (either from earlier check or from freshly saved value)
        if not has_uid:
            has_uid = await database_sync_to_async(lambda: asset.tbank_instrument_uid)()

        with Client(token) as client:
            from django.utils import timezone

            response = client.instruments.get_bond_coupons(
                instrument_id=has_uid,
                from_=timezone.make_aware(datetime.combine(from_date, datetime.min.time())),
                to=timezone.make_aware(datetime.combine(to_date, datetime.max.time())),
            )

            if not response.events:
                logger.warning(f"No coupon events found for bond {asset_name}")
                return False

            # Delete existing schedule if refreshing
            if force_refresh:
                deleted_count = await database_sync_to_async(
                    lambda: BondCouponSchedule.objects.filter(asset=asset).delete()[0]
                )()
                logger.debug(f"Deleted {deleted_count} existing coupon schedule entries")

            # Cache the coupon schedule
            coupons_created = 0
            for coupon in response.events:
                coupon_amount = None
                coupon_currency = None
                if hasattr(coupon, "pay_one_bond") and coupon.pay_one_bond:
                    coupon_amount = quotation_to_decimal(coupon.pay_one_bond)
                    coupon_currency = coupon.pay_one_bond.currency

                # Convert coupon type enum to user-friendly string
                coupon_type_str = None
                if hasattr(coupon, "coupon_type"):
                    coupon_type_mapping = {
                        0: "Unspecified",
                        1: "Constant",
                        2: "Floating",
                        3: "Discount",
                        4: "Mortgage",
                        5: "Fixed",
                        6: "Variable",
                        7: "Other",
                    }
                    raw_type = coupon.coupon_type
                    try:
                        type_key = int(raw_type)
                    except (ValueError, TypeError):
                        # SDK may return enum strings like 'FIXED' — map directly
                        type_key = str(raw_type).upper()
                        coupon_type_str = type_key.title() if type_key else "Unknown"
                    if coupon_type_str is None:
                        coupon_type_str = coupon_type_mapping.get(type_key, "Unknown")

                # Create or update coupon schedule entry using database_sync_to_async
                await database_sync_to_async(BondCouponSchedule.objects.update_or_create)(
                    asset=asset,
                    coupon_number=coupon.coupon_number,
                    defaults={
                        "coupon_start_date": coupon.coupon_start_date.date(),
                        "coupon_end_date": coupon.coupon_end_date.date(),
                        "payment_date": coupon.coupon_date.date(),
                        "coupon_amount": coupon_amount,
                        "coupon_currency": coupon_currency,
                        "coupon_type": coupon_type_str,
                    },
                )
                coupons_created += 1

            logger.info(f"Successfully cached {coupons_created} coupon periods for {asset_name}")
            return True

    except RequestError as e:
        logger.error(f"T-Bank API error fetching coupon schedule for {asset_name}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error fetching coupon schedule for {asset_name}: {str(e)}", exc_info=True)
        return False


async def save_bond_redemption_history(security, instrument_uid, user, date_to_save=None):
    """
    Fetch and save all bond redemption history to NotionalHistory model.

    This function fetches all MTY (maturity/redemption) events for a bond from T-Bank API
    and creates NotionalHistory entries for each redemption event.

    Args:
        security: Assets instance (the bond)
        instrument_uid: T-Bank instrument UID for the bond
        date_to_save: The date until which to save redemption history
        user: CustomUser instance (to get API token)

    Returns:
        int: Number of NotionalHistory entries created
    """
    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return 0

        # Get bond metadata to get initial notional
        bond_meta = await database_sync_to_async(lambda: security.bond_metadata)()
        if not bond_meta or not bond_meta.initial_notional:
            logger.warning(f"No bond metadata with initial_notional for {security.name}")
            return 0

        initial_notional = bond_meta.initial_notional

        with Client(token) as client:
            # Fetch all MTY events from inception to now
            request = GetBondEventsRequest(
                from_=datetime(1980, 1, 1),
                # to=date_to_save if date_to_save else datetime.now(),
                instrument_id=instrument_uid,
                type=EventType.EVENT_TYPE_MTY,
            )

            response = client.instruments.get_bond_events(request)

            if not response.events:
                logger.info(f"No redemption events found for bond {security.name}")
                return 0

            # Sort events by date
            sorted_events = sorted(response.events, key=lambda e: e.event_date)

            # Track cumulative notional changes
            current_notional = initial_notional
            entries_created = 0

            @database_sync_to_async
            def create_notional_history_entry(
                event_date, notional_per_unit, change_amount, operation_type
            ):
                from common.models import NotionalHistory

                # Determine change reason based on operation_type
                if operation_type in ["CM", "OM"]:
                    change_reason = "MATURITY"
                else:
                    change_reason = "REDEMPTION"

                _, created = NotionalHistory.objects.update_or_create(
                    asset=security,
                    date=event_date,
                    change_reason=change_reason,
                    defaults={
                        "notional_per_unit": notional_per_unit,
                        "change_amount": change_amount,
                        "comment": (
                            f"Auto-imported from T-Bank API (operation_type: {operation_type})",
                        ),
                    },
                )
                return created

            for event in sorted_events:
                # event.value is percentage redeemed
                redeemed_pct = quotation_to_decimal(event.value)

                # Calculate absolute change amount
                # redeemed_pct is already a percentage
                change_amount = -initial_notional * (redeemed_pct / Decimal(100))

                current_notional += change_amount

                # Create NotionalHistory entry
                created = await create_notional_history_entry(
                    event.event_date.date(),
                    current_notional,
                    change_amount,
                    event.operation_type,
                )

                if created:
                    entries_created += 1
                    logger.info(
                        f"Created NotionalHistory for {security.name} "
                        f"on {event.event_date.date()}: "
                        f"notional={current_notional}, change={change_amount}"
                    )

            logger.info(f"Saved {entries_created} NotionalHistory entries for {security.name}")
            return entries_created

    except RequestError as e:
        logger.error(f"T-Bank API error fetching bond events for {instrument_uid}: {str(e)}")
        return 0
    except Exception as e:
        logger.error(f"Error saving bond redemption history for {security.name}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0


async def get_security_by_uid(instrument_uid, user, position_uid=None, name=None):
    """
    Get security details from Tinkoff API using instrument_uid.

    Falls back to find_instrument if get_instrument_by fails.

    Args:
        instrument_uid: Tinkoff instrument UID
        user: CustomUser instance
        position_uid: Optional position UID for fallback search
        name: Optional name for fallback search

    Returns:
        List of tuples (name, ISIN, instrument type, ticker) or empty list if not found.
    """
    token = await get_user_token(user)
    try:
        with Client(token) as client:
            instrument = client.instruments.get_instrument_by(
                id_type=3, id=instrument_uid
            )  # id_type=3 is uid
            return [
                (
                    instrument.instrument.name,
                    instrument.instrument.isin,
                    instrument.instrument.instrument_kind,
                    instrument.instrument.ticker,
                )
            ]
    except RequestError as e:
        error_message = str(e)
        if "40002" in error_message:
            logger.error("Insufficient privileges for Tinkoff API token")
            return []
        elif "40003" in error_message:
            logger.error("Invalid or expired Tinkoff API token")
            return []
        elif "50002" in error_message:
            logger.warning(f"Instrument not found by UID {instrument_uid}, trying fallback methods")

            # Try fallback with position_uid or name
            if position_uid or name:
                try:
                    with Client(token) as client:
                        # Try position_uid first as it's more specific
                        query = position_uid if position_uid else name
                        logger.info(f"Searching instrument with query: {query}")

                        result = client.instruments.find_instrument(query=query)

                        if result.instruments:
                            if len(result.instruments) == 1:
                                # Single match - use it
                                found = result.instruments[0]
                                logger.info(f"Found single match: {found.name} ({found.isin})")
                                return [
                                    (
                                        found.name,
                                        found.isin,
                                        found.instrument_kind,
                                        found.ticker,
                                    )
                                ]
                            else:
                                # Multiple matches - try to find exact match by position_uid
                                if position_uid:
                                    for inst in result.instruments:
                                        if inst.position_uid == position_uid:
                                            logger.info(
                                                f"Found match by position_uid: {inst.name} "
                                                f"({inst.isin})"
                                            )
                                            return [
                                                (
                                                    inst.name,
                                                    inst.isin,
                                                    inst.instrument_kind,
                                                    inst.ticker,
                                                )
                                            ]

                                # No exact match, return all found
                                logger.warning(
                                    f"Multiple instruments found ({len(result.instruments)})"
                                )
                                securities_found = []
                                for _, inst in enumerate(result.instruments):
                                    securities_found.append(
                                        (
                                            inst.name,
                                            inst.isin,
                                            inst.instrument_kind,
                                            inst.ticker,
                                        )
                                    )
                                return securities_found
                        else:
                            logger.error(f"No instruments found with query: {query}")
                            return []

                except Exception as fallback_error:
                    logger.error(f"Fallback search failed: {str(fallback_error)}")
                    return []
            else:
                logger.error("No position_uid or name provided for fallback search")
                return []
        else:
            logger.error(f"Tinkoff API error: {error_message}")
            return []
    except Exception as e:
        logger.error(f"Error getting security details from Tinkoff: {str(e)}")
        return []


async def _find_or_create_security(
    instrument_uid, investor, position_uid=None, name=None, date_to_save=None
) -> tuple[Assets | None, str]:
    """
    Find existing security or create new one using Tinkoff API data.

    Args:
        instrument_uid: Tinkoff instrument UID
        investor: CustomUser instance
        position_uid: Optional position UID for fallback search
        name: Optional security name for fallback search

    Returns:
        tuple: (Assets instance, str status)
    """
    # Get security details from Tinkoff
    securities_found = await get_security_by_uid(instrument_uid, investor, position_uid, name)
    if not securities_found or len(securities_found) == 0:
        return None, "Could not get security details from Tinkoff"

    # Resolve existing securities: find by ISIN, then use the helper to link+fill.
    # If the loop finds nothing, fall through to create_security_from_micex below.
    for sec in securities_found:
        candidate_isin = sec[1]

        @database_sync_to_async
        def _find_existing():
            return Assets.objects.filter(ISIN=candidate_isin).first()

        existing = await _find_existing()
        if existing is None:
            continue
        result = await database_sync_to_async(resolve_or_create_asset)(
            user=investor,
            isin=candidate_isin,
            currency=existing.currency,
            submitted_fields={},
            mode="silent",
        )
        status_str = (
            "existing_with_relationships"
            if not result.linked
            else "existing_added_relationships"
        )
        return result.asset, status_str

    # No existing security matched any ISIN — create from MICEX data.
    if len(securities_found) == 1:
        # Create new security using MICEX data
        # securities_found tuple: (name, isin, instrument_kind, ticker)
        security_name = securities_found[0][0]
        security_isin = securities_found[0][1]
        security_type = securities_found[0][2]
        security_ticker = securities_found[0][3] if len(securities_found[0]) > 3 else None

        found_security = await create_security_from_micex(
            security_name,
            security_isin,
            investor,
            security_type,
            ticker=security_ticker,
            date_to_save=date_to_save,
        )

        if found_security:
            return found_security, "created_new_from_micex"

        # Fallback to T-Bank data if MICEX fails (e.g., matured bonds, delisted securities)
        logger.warning(
            f"MICEX creation failed for {security_name} ({security_isin}), "
            f"falling back to T-Bank data"
        )
        found_security = await create_security_from_tinkoff(
            security_name,
            security_isin,
            security_ticker,
            investor,
            security_type,
            instrument_uid,  # Pass the T-Bank instrument UID
            date_to_save=date_to_save,
        )

        if found_security:
            return found_security, "created_new_from_tbank"

        return None, "failed_to_create"


async def map_tinkoff_operation_to_transaction(operation, investor, account):
    """
    Map a Tinkoff API operation to our Transaction model format.

    Args:
        operation: Tinkoff API OperationItem
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        dict: Transaction data ready for creating a Transaction or FXTransaction instance.
    """
    # Initialize base transaction data
    transaction_data = {
        "investor": investor,
        "account": account,
        "date": operation.date,  # Keep full datetime from T-Bank API
        "comment": operation.description,
    }

    # Check if this is an FX transaction
    is_fx_transaction = (
        operation.instrument_kind == InstrumentType.INSTRUMENT_TYPE_CURRENCY
        and operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]
    )

    logger.debug(f"==== Processing operation ID: {operation.id} ====")
    logger.debug(f"  Instrument kind: {operation.instrument_kind}")
    logger.debug(
        f"  Is currency: {operation.instrument_kind == InstrumentType.INSTRUMENT_TYPE_CURRENCY}"
    )
    logger.debug(f"  Operation type: {operation.type}")
    logger.debug(
        "  Is buy/sell: "
        f"{operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]}"
    )
    logger.debug(f"  >> IS FX TRANSACTION: {is_fx_transaction} <<")

    if is_fx_transaction:
        # This is an FX transaction
        transaction_data["is_fx"] = True

        # Extract currency being traded from operation name or instrument_uid
        # The 'name' field contains the currency name (e.g., "Доллар США" for USD)
        currency_map = {
            "Доллар США": "USD",
            "Евро": "EUR",
            "Фунт стерлингов": "GBP",
            "Швейцарский франк": "CHF",
            "Юань": "CNY",
        }

        to_currency = None
        # Try to extract from name
        for key, value in currency_map.items():
            if key in operation.name:
                to_currency = value
                break

        # Fallback: try to get from instrument details
        if not to_currency and operation.instrument_uid:
            securities_found = await get_security_by_uid(
                operation.instrument_uid,
                investor,
                operation.position_uid,
                operation.name,
            )
            if len(securities_found) == 1:
                name = securities_found[0][0]
                for key, value in currency_map.items():
                    if name and key in name:
                        to_currency = value
                        break

        # Determine from_currency and to_currency based on operation type
        if operation.type == OperationType.OPERATION_TYPE_BUY:
            # Buying foreign currency, paying with account currency
            transaction_data["from_currency"] = operation.payment.currency.upper()
            transaction_data["to_currency"] = to_currency or "USD"  # Default to USD if unknown
            transaction_data["from_amount"] = abs(quotation_to_decimal(operation.payment))
            transaction_data["to_amount"] = Decimal(str(operation.quantity))
        else:  # SELL
            # Selling foreign currency, receiving account currency
            transaction_data["from_currency"] = to_currency or "USD"
            transaction_data["to_currency"] = operation.payment.currency.upper()
            transaction_data["from_amount"] = Decimal(str(operation.quantity))
            transaction_data["to_amount"] = abs(quotation_to_decimal(operation.payment))

        # Calculate exchange rate
        if transaction_data.get("from_amount") and transaction_data.get("to_amount"):
            transaction_data["exchange_rate"] = (
                transaction_data["from_amount"] / transaction_data["to_amount"]
            )

        # Handle commission
        if operation.commission and operation.commission.units != 0:
            transaction_data["commission"] = -1 * abs(
                quotation_to_decimal(operation.commission)
            )
            transaction_data["commission_currency"] = (
                operation.commission.currency.upper()
            )

        logger.debug(
            f"✓ FX transaction created: {transaction_data['from_currency']} "
            f"-> {transaction_data['to_currency']}, "
            f"Rate: {transaction_data.get('exchange_rate', 'N/A')}"
        )

        return transaction_data

    # Regular (non-FX) transaction handling
    # Map operation type
    operation_type_mapping = {
        OperationType.OPERATION_TYPE_BUY: TRANSACTION_TYPE_BUY,
        OperationType.OPERATION_TYPE_SELL: TRANSACTION_TYPE_SELL,
        OperationType.OPERATION_TYPE_DIVIDEND: TRANSACTION_TYPE_DIVIDEND,
        OperationType.OPERATION_TYPE_DIVIDEND_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_OVERNIGHT: TRANSACTION_TYPE_REPO,
        OperationType.OPERATION_TYPE_COUPON: TRANSACTION_TYPE_COUPON,
        OperationType.OPERATION_TYPE_TAX_CORRECTION: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_OUTPUT: TRANSACTION_TYPE_CASH_OUT,
        OperationType.OPERATION_TYPE_INPUT: TRANSACTION_TYPE_CASH_IN,
        OperationType.OPERATION_TYPE_SERVICE_FEE: TRANSACTION_TYPE_BROKER_COMMISSION,
        OperationType.OPERATION_TYPE_BOND_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_BENEFIT_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_INPUT_SECURITIES: TRANSACTION_TYPE_ASSET_TRANSFER,
        OperationType.OPERATION_TYPE_OUTPUT_SECURITIES: TRANSACTION_TYPE_ASSET_TRANSFER,
        OperationType.OPERATION_TYPE_BOND_REPAYMENT: TRANSACTION_TYPE_BOND_REDEMPTION,
        OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL: TRANSACTION_TYPE_BOND_MATURITY,
    }

    if operation.type == OperationType.OPERATION_TYPE_BROKER_FEE:
        return "Separate entry for transaction broker fee"

    # Check if this is an asset transfer operation (before type mapping)
    is_asset_transfer = operation.type in [
        OperationType.OPERATION_TYPE_INPUT_SECURITIES,
        OperationType.OPERATION_TYPE_OUTPUT_SECURITIES,
    ]

    transaction_data["type"] = operation_type_mapping.get(operation.type)
    if not transaction_data["type"]:
        return None  # Skip unsupported operation types

    if is_asset_transfer:
        transaction_data["is_asset_transfer"] = True
        logger.debug(f"Detected asset transfer operation: {operation.type}")

    # Handle currency
    if operation.payment and operation.payment.currency:
        transaction_data["currency"] = operation.payment.currency.upper()

    # Handle security matching
    if operation.instrument_uid:
        security, status = await _find_or_create_security(
            operation.instrument_uid,
            investor,
            operation.position_uid,
            operation.name,
            date_to_save=operation.date.date(),
        )
        if security:
            transaction_data["security"] = security
            logger.debug(f"Security matched: {security.name} (status: {status})")
        else:
            logger.warning(f"Could not match security for operation {operation.id}")
            # Get security info for potential creation
            securities_found = await get_security_by_uid(
                operation.instrument_uid,
                investor,
                operation.position_uid,
                operation.name,
            )
            if len(securities_found) == 1:
                name = securities_found[0][0]
                isin = securities_found[0][1]
                instrument_type = securities_found[0][2]

                # Mark this transaction as needing security mapping
                transaction_data["needs_security_mapping"] = True
                if name and isin:
                    transaction_data["security_description"] = name
                    transaction_data["isin"] = isin
                    transaction_data["instrument_type"] = instrument_type
                else:
                    transaction_data["security_description"] = operation.name
                    transaction_data["instrument_type"] = operation.instrument_type
                transaction_data["security"] = None
            else:
                raise ValueError(f"Multiple securities found for operation {operation.id}")

    # Handle bond redemption operations
    if operation.type in [
        OperationType.OPERATION_TYPE_BOND_REPAYMENT,
        OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL,
    ]:
        # Note: T-Bank API returns quantity=0 for bond redemptions
        # The actual redemption information is in the payment field
        # We don't change quantity for amortizing bonds - the notional changes instead

        # Payment represents the cash received from redemption
        if operation.payment:
            cash_received = quotation_to_decimal(operation.payment)
            transaction_data["cash_flow"] = cash_received

            # For bond redemptions, we need to infer the notional change
            # The payment is typically: number_of_bonds * notional_redeemed_per_bond
            # Since we don't have the quantity, we'll store the total cash as notional_change
            # This will need to be adjusted manually or via bond metadata
            transaction_data["notional_change"] = cash_received

        # Set quantity to None since T-Bank doesn't provide it
        # The bond position doesn't change in terms of number of bonds held
        transaction_data["quantity"] = None

        # Price isn't meaningful for amortizing redemptions
        # It's the notional being returned, not a market transaction
        transaction_data["price"] = None

        logger.debug(
            f"Bond redemption: cash_flow={transaction_data.get('cash_flow')}, "
            f"notional_change={transaction_data.get('notional_change')}"
        )

    # Handle quantity and price for buy/sell operations (including asset transfers)
    elif operation.type in [
        OperationType.OPERATION_TYPE_BUY,
        OperationType.OPERATION_TYPE_SELL,
        OperationType.OPERATION_TYPE_INPUT_SECURITIES,
        OperationType.OPERATION_TYPE_OUTPUT_SECURITIES,
    ]:
        # For regular buy/sell, use the operation price
        # For asset transfers, price might be 0, will be set later to buy-in/market price
        if operation.price:
            actual_price = quotation_to_decimal(operation.price)

            # For bonds, convert price to percentage of par
            # Use bond events API to determine notional based on redemption history
            if security and security.type == "Bond":
                try:
                    # Get initial notional from T-Bank API
                    initial_notional = await get_bond_initial_notional(
                        operation.instrument_uid, investor
                    )

                    if not initial_notional:
                        # Fallback to bond metadata
                        bond_meta = await database_sync_to_async(lambda: security.bond_metadata)()
                        if bond_meta and bond_meta.initial_notional:
                            initial_notional = bond_meta.initial_notional
                        else:
                            logger.warning(
                                f"Could not determine initial notional for bond {security.name}, "
                                f"storing actual price: {actual_price}"
                            )
                            transaction_data["price"] = actual_price
                            raise ValueError("No initial notional available")

                    # Calculate notional at transaction date based on redemption history
                    notional = await get_bond_notional_at_date(
                        operation.instrument_uid,
                        operation.date.date(),
                        investor,
                        initial_notional,
                    )

                    if notional and notional > 0:
                        # Convert actual price to percentage: (actual_price / notional) * 100
                        price_percentage = (actual_price / notional) * Decimal(100)

                        transaction_data["price"] = price_percentage
                        transaction_data["notional"] = notional
                        logger.info(
                            f"Bond transaction: actual_price={actual_price}, "
                            f"notional={notional}, percentage={price_percentage:.2f}%"
                        )
                    else:
                        logger.warning(
                            f"Could not determine notional for bond {security.name}, "
                            f"storing actual price: {actual_price}"
                        )
                        transaction_data["price"] = actual_price
                except Exception as e:
                    logger.error(
                        f"Error converting bond price to percentage: {e}. "
                        f"Using actual price: {actual_price}"
                    )
                    transaction_data["price"] = actual_price
            else:
                # For non-bonds, use actual price as-is
                transaction_data["price"] = actual_price

        aci = operation.accrued_int

        if operation.type in [
            OperationType.OPERATION_TYPE_BUY,
            OperationType.OPERATION_TYPE_INPUT_SECURITIES,
        ]:
            transaction_data["quantity"] = Decimal(str(operation.quantity))
            if quotation_to_decimal(aci) != 0:
                transaction_data["aci"] = -1 * abs(quotation_to_decimal(aci))
        else:  # SELL or OUTPUT_SECURITIES
            transaction_data["quantity"] = -1 * Decimal(str(operation.quantity))
            if quotation_to_decimal(aci) != 0:
                transaction_data["aci"] = abs(quotation_to_decimal(aci))
            if is_asset_transfer:
                transaction_data["needs_price_calculation"] = True

    else:
        # Handle payment/cash flow
        if operation.payment:
            payment = quotation_to_decimal(operation.payment)
            transaction_data["cash_flow"] = payment

    # Handle commission
    if operation.commission and operation.commission.units != 0:
        transaction_data["commission"] = -1 * abs(quotation_to_decimal(operation.commission))

    return transaction_data


async def create_transaction_from_tinkoff(operation, investor, account):
    """
    Create a Transaction instance from Tinkoff operation data if it doesn't exist.

    Args:
        operation: Tinkoff API OperationItem
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        tuple: (Transaction instance or None, str status message).
    """
    transaction_data = await map_tinkoff_operation_to_transaction(operation, investor, account)

    if not transaction_data:
        return None, "Unsupported operation type"

    # Check if similar transaction already exists
    # All dates are now naive datetime objects for consistent comparison

    transaction_date = transaction_data["date"]

    # Ensure the transaction date is naive (strip timezone if present)
    if hasattr(transaction_date, "tzinfo") and transaction_date.tzinfo is not None:
        transaction_date = transaction_date.replace(tzinfo=None)

    # Check for existing transactions within a reasonable time window (1 minute)
    # to handle potential timestamp differences

    time_window = timedelta(minutes=1)

    existing = await database_sync_to_async(Transactions.objects.filter)(
        investor=investor,
        account=account,
        date__date__gte=transaction_date - time_window,
        date__date__lte=transaction_date + time_window,
        type=transaction_data["type"],
        quantity=transaction_data.get("quantity"),
        price=transaction_data.get("price"),
        cash_flow=transaction_data.get("cash_flow"),
    ).first()

    if existing:
        logger.debug(f"Transaction already exists: {existing}")
        return None, "Transaction already exists"

    # Create new transaction
    try:
        transaction = await database_sync_to_async(Transactions.objects.create)(**transaction_data)
        logger.info(f"Transaction created successfully: {transaction}")
        return transaction, "Transaction created successfully"
    except Exception as e:
        return None, f"Error creating transaction: {str(e)}"


# New utility functions for token management
async def verify_token_access(user, required_access="read_only"):
    """
    Verify if user has valid token with required access level.

    Args:
        user: CustomUser instance
        required_access: str, access level required ('read_only' or 'full_access')

    Returns:
        bool: True if token is valid and has required access.
    """
    try:
        token = await get_user_token(user)
        with Client(token):
            return True
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        return False


async def get_account_info(user):
    """
    Get user's Tinkoff account information.

    Args:
        user: CustomUser instance

    Returns:
        dict: Account information or None if failed
    """
    try:
        token = await get_user_token(user)
        with Client(token) as client:
            accounts = client.users.get_accounts()
            return {
                "accounts": [
                    {
                        "id": acc.id,
                        "type": acc.type.name,
                        "name": acc.name,
                        "status": acc.status.name,
                    }
                    for acc in accounts.accounts
                ]
            }
    except Exception as e:
        logger.error(f"Failed to get account info: {str(e)}")
        return None


async def get_price_from_tbank(instrument_uid: str, date: datetime.date, user):
    """
    Get the closing price for a security from T-Bank (Tinkoff) API for a specific date.

    Optimized to fetch minimal data: starts with 1 day, expands only if needed.

    Args:
        instrument_uid: T-Bank instrument UID
        date: datetime.date object for which to fetch the price
        user: CustomUser instance (to get API token)

    Returns:
        Decimal: The closing price, or None if not found
    """

    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return None

        logger.debug(f"Fetching price for instrument {instrument_uid} on {date}")

        # Convert target date to timezone-aware datetime (UTC)
        target_dt = datetime.combine(date, datetime.min.time(), tzinfo=timezone.utc)

        # Try progressively larger date ranges: 1 day, 7 days, 14 days
        lookback_days = [1, 7, 14]

        with Client(token) as client:
            from django.utils import timezone

            for days_back in lookback_days:
                # Convert naive dates to timezone-aware for API call
                # Tinkoff API expects timezone-aware datetime objects
                from_dt = date - timedelta(days=days_back)
                to_dt = date

                from_dt = datetime.combine(
                    from_dt, datetime.min.time(), tzinfo=timezone.utc
                )
                to_dt = datetime.combine(
                    to_dt, datetime.max.time(), tzinfo=timezone.utc
                )

                logger.debug(
                    f"Attempt with {days_back} day(s) lookback: "
                    f"from {from_dt} to {to_dt}"
                )

                try:
                    response = client.market_data.get_candles(
                        instrument_id=instrument_uid,
                        from_=from_dt,
                        to=to_dt,
                        interval=CandleInterval.CANDLE_INTERVAL_DAY,
                    )

                    if response.candles and len(response.candles) > 0:
                        # Find exact match first, then most recent before target date
                        selected_candle = None
                        exact_match = None

                        for candle in response.candles:
                            candle_date = candle.time.date()

                            # Check for exact date match
                            if candle_date == date:
                                exact_match = candle
                                break

                            # Track the most recent candle before or on target date
                            if candle.time <= to_dt:
                                if (
                                    selected_candle is None
                                    or candle.time > selected_candle.time
                                ):
                                    selected_candle = candle

                        # Prefer exact match, fall back to most recent
                        final_candle = exact_match if exact_match else selected_candle

                        if final_candle:
                            close_price = quotation_to_decimal(final_candle.close)
                            logger.info(
                                f"Fetched price for {instrument_uid} on "
                                f"{final_candle.time.date()}: {close_price} "
                                f"(requested: {date}, {'exact' if exact_match else 'closest'})"
                            )
                            return close_price

                    # If we got a response but no suitable candles, try next range
                    logger.debug(
                        f"No suitable candle in {days_back}-day range, " f"trying larger range..."
                    )

                except RequestError as e:
                    # API error on this attempt, try next range
                    logger.warning(
                        f"API error with {days_back}-day lookback: {str(e)}, "
                        f"trying larger range..."
                    )
                    continue

            # Exhausted all attempts
            logger.warning(
                f"No candle data found for instrument {instrument_uid} "
                f"on or before {date} (tried up to {max(lookback_days)} days back)"
            )
            return None

    except RequestError as e:
        logger.error(f"T-Bank API error fetching price for {instrument_uid} on {date}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error fetching price from T-Bank for {instrument_uid} on {date}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


async def get_instrument_uid(asset: Assets, user):
    """Get instrument UID from T-Bank API.

    Args:
        asset: Assets instance
        user: CustomUser instance

    Returns:
        str: Instrument UID or None if not found
    """
    from channels.db import database_sync_to_async

    token = await get_user_token(user)
    if not token:
        logger.error("No T-Bank API token found for user")
        return None

    # Get asset data in sync context
    asset_isin = await database_sync_to_async(lambda: asset.ISIN)()
    asset_type = await database_sync_to_async(lambda: asset.type)()

    with Client(token) as client:
        instruments = client.instruments.find_instrument(query=asset_isin).instruments

        if asset_type == "Bond":
            return instruments[0].uid if instruments else None
        elif asset_type == "ETF":
            for instrument in instruments:
                if instrument.class_code == "TQTF":
                    return instrument.uid
        elif asset_type == "Share":
            for instrument in instruments:
                if instrument.class_code == "TQBR":
                    return instrument.uid

        return None
