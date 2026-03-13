"""
Utility functions for importing transaction and account data from external sources.

This module provides functions to parse Excel files, validate data, and import
transactions from various broker formats.
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
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
from t_tech.invest import Client, InstrumentType
from t_tech.invest.utils import quotation_to_decimal

from common.models import (
    Accounts,
    Assets,
    BondMetadata,
    Brokers,
    FutureMetadata,
    OptionMetadata,
    Prices,
    Transactions,
)
from constants import (
    ASSET_TYPE_CHOICES,
    EXPOSURE_CHOICES,
    MUTUAL_FUNDS_IN_PENCES,
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)
from core.broker_api_utils import get_broker_api
from core.tinkoff_utils import get_user_token, save_bond_redemption_history

# logger = structlog.get_logger(__name__)
logger = logging.getLogger(__name__)

CustomUser = get_user_model()


@database_sync_to_async
def get_investor(investor_id):
    """
    Retrieve investor/user by ID.

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
    """
    Retrieve an account by ID.

    Args:
        account_id: The ID of the account to retrieve.

    Returns:
        Accounts: The account instance.

    Raises:
        Accounts.DoesNotExist: If account doesn't exist.
    """
    return Accounts.objects.get(id=account_id)


@database_sync_to_async
def get_security(security_id):
    """
    Retrieve a security/asset by ID.

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
    """
    Check if a transaction already exists in the database.

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
    """
    Parse Charles Stanley transaction file.

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
                        result["message"] = f"No data found for {d.strftime('%Y-%m-%d')}"
                except Exception as e:
                    result["status"] = "error"
                    result["message"] = f"Error processing data for {security.name}: {str(e)}"

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
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(None, yf.Ticker, security.yahoo_symbol)
            # Set auto_adjust to False to get unadjusted close prices
            history = await loop.run_in_executor(
                None,
                lambda: ticker.history(  # noqa: B023
                    start=start_date,  # noqa: B023
                    end=end_date,  # noqa: B023
                    auto_adjust=False,  # noqa: B023
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
    from core.tinkoff_utils import get_price_from_tbank

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


async def parse_galaxy_account_cash_flows(file_path, currency, account, user, confirm_every):
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

            # Create main asset
            asset = Assets.objects.create(
                type=asset_type,
                ISIN=isin if isin else instrument_data.isin,
                name=instrument_data.name,
                currency=instrument_data.currency,
                exposure=exposure,
                restricted=False,
                data_source="TBANK",
                secid=instrument_data.ticker if hasattr(instrument_data, "ticker") else None,
                tbank_instrument_uid=instrument_uid,
            )
            asset.investors.add(user)

            # Create type-specific metadata
            if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND and instrument_data:
                bond_data = {}

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

                if hasattr(instrument_data, "placement_date") and instrument_data.placement_date:
                    bond_data["issue_date"] = instrument_data.placement_date.date()

                if hasattr(instrument_data, "maturity_date") and instrument_data.maturity_date:
                    bond_data["maturity_date"] = instrument_data.maturity_date.date()

                if hasattr(instrument_data, "coupon_quantity_per_year"):
                    bond_data["coupon_frequency"] = instrument_data.coupon_quantity_per_year

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

                if bond_data:
                    BondMetadata.objects.create(asset=asset, **bond_data)
                    logger.info(f"Created BondMetadata from T-Bank for {asset.name}")

            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES and instrument_data:
                future_data = {}

                if hasattr(instrument_data, "expiration_date") and instrument_data.expiration_date:
                    future_data["expiration_date"] = instrument_data.expiration_date.date()

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

                if hasattr(instrument_data, "expiration_date") and instrument_data.expiration_date:
                    option_data["expiration_date"] = instrument_data.expiration_date.date()

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
                from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule

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

            asset = Assets.objects.create(
                type=asset_type,
                ISIN=isin,
                ticker=ticker,
                name=security_name,
                currency="RUB",
                exposure=exposure,
                restricted=False,
                data_source="TBANK",
                secid=None,
                tbank_instrument_uid=instrument_uid,
            )
            asset.investors.add(user)
            return asset

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
            # Create main asset
            asset = Assets.objects.create(
                type=asset_type,
                ISIN=security_data["isin"] or isin,
                name=security_data["name"],
                ticker=ticker,
                currency=security_data["currency"],
                exposure=exposure,
                restricted=False,
                data_source="MICEX",
                secid=security_data["secid"],
            )
            asset.investors.add(user)

            # Create type-specific metadata
            data = security_data["data"]

            if instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
                # Create BondMetadata
                bond_data = {}

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

                # Create BondMetadata if we have any data
                if bond_data:
                    BondMetadata.objects.create(asset=asset, **bond_data)
                    logger.info(f"Created BondMetadata for {asset.name}: {bond_data}")

            elif instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES:
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
                    from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule

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
        broker_api = await get_broker_api(broker)
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
        broker_api = await get_broker_api(broker)
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
