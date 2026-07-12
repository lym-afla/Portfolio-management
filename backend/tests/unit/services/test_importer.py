"""Unit tests for ``services/importer.py``.

Focuses on the pure/utility functions that are testable without network
access:

- ``generate_dates_for_price_import`` -- pure date math.
- ``read_excel_file`` -- file I/O via Django ``default_storage``.
- ``_process_transaction_row`` -- row -> transaction dict mapping.
- ``transaction_exists`` / ``fx_transaction_exists`` -- duplicate checks.
- ``check_broker_token_active`` -- broker API lifecycle (mocked).
- ``match_tinkoff_broker_account`` -- native_id matching logic (mocked).

All money values use ``Decimal`` (never float). External network calls
(httpx, aiohttp, yfinance, the Tinkoff SDK, ``services.broker_api``) are
mocked -- no real HTTP requests are made.
"""

import io
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from channels.db import database_sync_to_async

from common.models import Accounts, Assets, Brokers, FXTransaction, Transactions
from constants import (
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_SELL,
)
from services.importer import (
    _process_transaction_row,
    check_broker_token_active,
    fx_transaction_exists,
    generate_dates_for_price_import,
    match_tinkoff_broker_account,
    read_excel_file,
    transaction_exists,
)

pytestmark = pytest.mark.django_db


# =============================================================================
# generate_dates_for_price_import -- pure date math, no DB, no network
# =============================================================================


class TestGenerateDatesForPriceImport:
    """Cover every frequency branch of ``generate_dates_for_price_import``."""

    def test_daily_skips_weekends(self):
        # 2023-01-02 (Mon) .. 2023-01-08 (Sun) => 5 weekdays.
        start = date(2023, 1, 2)
        end = date(2023, 1, 8)
        dates = generate_dates_for_price_import(start, end, "daily")

        assert dates == [
            date(2023, 1, 2),
            date(2023, 1, 3),
            date(2023, 1, 4),
            date(2023, 1, 5),
            date(2023, 1, 6),
        ]
        # No Saturday (7) or Sunday (8).
        assert all(d.weekday() < 5 for d in dates)

    def test_daily_single_day(self):
        # A single Friday.
        dates = generate_dates_for_price_import(
            date(2023, 1, 6), date(2023, 1, 6), "daily"
        )
        assert dates == [date(2023, 1, 6)]

    def test_daily_excludes_start_when_weekend(self):
        # 2023-01-07 is a Saturday; window ends the next day (Sunday).
        dates = generate_dates_for_price_import(
            date(2023, 1, 7), date(2023, 1, 8), "daily"
        )
        assert dates == []

    def test_weekly_picks_fridays(self):
        # 2023-01-02 is a Monday; first Friday is 2023-01-06, then 01-13, 01-20.
        dates = generate_dates_for_price_import(
            date(2023, 1, 2), date(2023, 1, 25), "weekly"
        )
        assert dates == [
            date(2023, 1, 6),
            date(2023, 1, 13),
            date(2023, 1, 20),
        ]
        assert all(d.weekday() == 4 for d in dates)

    def test_weekly_starting_on_friday_advances_to_next_friday(self):
        # 2023-01-06 is a Friday. The implementation forces current past start
        # when current <= start (days_until_friday == 0 on a Friday), so the
        # first emitted Friday is 2023-01-13, not the start date itself.
        dates = generate_dates_for_price_import(
            date(2023, 1, 6), date(2023, 1, 20), "weekly"
        )
        assert dates == [date(2023, 1, 13), date(2023, 1, 20)]

    def test_monthly_returns_last_day_of_each_month(self):
        # Start mid-January 2023; expect last day of Jan, Feb, Mar.
        dates = generate_dates_for_price_import(
            date(2023, 1, 15), date(2023, 3, 31), "monthly"
        )
        assert dates == [
            date(2023, 1, 31),
            date(2023, 2, 28),  # 2023 is not a leap year
            date(2023, 3, 31),
        ]

    def test_monthly_handles_leap_year_february(self):
        # 2024 is a leap year, so Feb has 29 days.
        dates = generate_dates_for_price_import(
            date(2024, 2, 1), date(2024, 2, 29), "monthly"
        )
        assert dates == [date(2024, 2, 29)]

    def test_quarterly_returns_quarter_end_dates(self):
        # Starting in January 2023 -> Q1 end is Mar 31, then Q2 end Jun 30.
        dates = generate_dates_for_price_import(
            date(2023, 1, 1), date(2023, 6, 30), "quarterly"
        )
        assert dates == [date(2023, 3, 31), date(2023, 6, 30)]

    def test_yearly_returns_year_end_dates(self):
        dates = generate_dates_for_price_import(
            date(2022, 6, 1), date(2024, 12, 31), "yearly"
        )
        assert dates == [
            date(2022, 12, 31),
            date(2023, 12, 31),
            date(2024, 12, 31),
        ]

    def test_yearly_with_end_before_first_year_end_returns_empty(self):
        # End date is before the first Dec 31.
        dates = generate_dates_for_price_import(
            date(2023, 1, 1), date(2023, 6, 1), "yearly"
        )
        assert dates == []

    def test_unsupported_frequency_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported frequency"):
            generate_dates_for_price_import(
                date(2023, 1, 1), date(2023, 12, 31), "hourly"
            )

    def test_start_after_end_returns_empty_for_all_frequencies(self):
        for freq in ("daily", "weekly", "monthly", "quarterly", "yearly"):
            dates = generate_dates_for_price_import(
                date(2023, 12, 31), date(2023, 1, 1), freq
            )
            assert dates == [], f"frequency={freq} should yield no dates"


# =============================================================================
# read_excel_file -- file I/O via Django default_storage
# =============================================================================


class TestReadExcelFile:
    """``read_excel_file`` reads from ``default_storage`` with header=3."""

    def _make_excel_bytes(self, rows):
        """Build an in-memory .xlsx file.

        The first three rows are deliberately blank filler so that
        ``pd.read_excel(header=3)`` treats row 4 (index 3) as the header.
        """
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        # Three filler rows so the real header lands on row index 3.
        ws.append(["filler", "filler", "filler", "filler", "filler", "filler"])
        ws.append(["", "", "", "", "", ""])
        ws.append(["", "", "", "", "", ""])
        # Header row + data rows with the exact columns read_excel_file reads.
        header = [
            "Date",
            "Description",
            "Stock Description",
            "Price",
            "Debit",
            "Credit",
        ]
        ws.append(header)
        for row in rows:
            ws.append(row)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read()

    def test_reads_valid_excel_and_returns_dataframe(self):
        payload = self._make_excel_bytes(
            [
                ["01-Jan-2023", "Buy", "Test Asset", 100, 1000, 0],
                ["02-Jan-2023", "Dividend", "Test Asset", 0, 0, 50],
            ]
        )

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=io.BytesIO(payload))
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("services.importer.default_storage.open", return_value=mock_file):
            df = read_excel_file("dummy.xlsx")

        assert list(df.columns) == [
            "Date",
            "Description",
            "Stock Description",
            "Price",
            "Debit",
            "Credit",
        ]
        assert len(df) == 2
        assert df.iloc[0]["Description"] == "Buy"
        assert df.iloc[1]["Description"] == "Dividend"

    def test_empty_file_raises_value_error(self):
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=io.BytesIO(b""))
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("services.importer.default_storage.open", return_value=mock_file):
            with pytest.raises(ValueError):
                read_excel_file("empty.xlsx")

    def test_generic_exception_raises_value_error_with_message(self):
        with patch(
            "services.importer.default_storage.open",
            side_effect=FileNotFoundError("missing"),
        ):
            with pytest.raises(ValueError, match="An error occurred while reading"):
                read_excel_file("missing.xlsx")


# =============================================================================
# transaction_exists / fx_transaction_exists -- duplicate detection
# =============================================================================


@pytest.fixture
def buy_transaction(user, account, asset):
    """Persist a Buy transaction for duplicate checks."""
    return Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type=TRANSACTION_TYPE_BUY,
        date=date(2023, 1, 15),
        quantity=Decimal("100"),
        price=Decimal("50.00"),
        commission=Decimal("-5.00"),
    )


class TestTransactionExists:
    """``transaction_exists`` builds a Q query over Transactions.

    The function is wrapped with ``database_sync_to_async`` so it returns a
    coroutine; tests await it. Async DB access over SQLite requires
    transactional mode.
    """

    pytestmark = [
        pytest.mark.django_db(transaction=True),
        pytest.mark.asyncio,
    ]

    async def test_returns_true_when_transaction_matches(self, buy_transaction, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "date": date(2023, 1, 15),
            "currency": "USD",
            "type": TRANSACTION_TYPE_BUY,
            "security": asset,
            "quantity": Decimal("100"),
            "price": Decimal("50.00"),
            "commission": Decimal("-5.00"),
        }
        assert await transaction_exists(data) is True

    async def test_returns_false_when_no_match(self, user, account, asset):
        data = {
            "investor": user,
            "account": account,
            "date": date(2099, 1, 1),  # far future, no match
            "currency": "USD",
            "type": TRANSACTION_TYPE_BUY,
            "security": asset,
            "quantity": Decimal("1"),
            "price": Decimal("1.00"),
        }
        assert await transaction_exists(data) is False

    async def test_ignores_optional_fields_that_are_none(self, buy_transaction, user, account, asset):
        # Optional fields set to None are skipped in the query, so this still
        # matches the persisted row (which has commission set).
        data = {
            "investor": user,
            "account": account,
            "date": date(2023, 1, 15),
            "currency": "USD",
            "type": TRANSACTION_TYPE_BUY,
            "security": asset,
            "quantity": Decimal("100"),
            "price": Decimal("50.00"),
            "commission": None,
            "aci": None,
        }
        assert await transaction_exists(data) is True

    async def test_missing_required_field_raises_value_error(self, user):
        data = {
            "investor": user,
            # account, date, currency, type omitted
        }
        with pytest.raises(ValueError, match="Required field 'account'"):
            await transaction_exists(data)


class TestFxTransactionExists:
    """``fx_transaction_exists`` rounds exchange_rate to model precision."""

    pytestmark = [
        pytest.mark.django_db(transaction=True),
        pytest.mark.asyncio,
    ]

    async def test_returns_true_for_matching_fx_transaction(self, fx_transaction, user, account):
        data = {
            "investor": user,
            "account": account,
            "date": date(2023, 2, 15),
            "from_currency": "USD",
            "to_currency": "EUR",
            "exchange_rate": Decimal("0.92"),
            "from_amount": Decimal("1000.00"),
            "to_amount": Decimal("920.00"),
            "commission": Decimal("2.00"),
        }
        assert await fx_transaction_exists(data) is True

    async def test_returns_false_when_no_match(self, user, account):
        data = {
            "investor": user,
            "account": account,
            "date": date(2099, 1, 1),
            "from_currency": "USD",
            "to_currency": "EUR",
            "exchange_rate": Decimal("0.92"),
        }
        assert await fx_transaction_exists(data) is False

    async def test_missing_required_field_raises_value_error(self, user):
        with pytest.raises(ValueError, match="Required field 'from_currency'"):
            await fx_transaction_exists(
                {
                    "investor": user,
                    "account": None,
                    "date": date(2023, 1, 1),
                    "to_currency": "EUR",
                    "exchange_rate": Decimal("1"),
                }
            )


# =============================================================================
# _process_transaction_row -- row -> transaction dict mapping
# =============================================================================


def _row(stock_description="Test Stock Corp", **overrides):
    """Build a pandas Series row resembling a Charles Stanley export.

    ``Stock Description`` is passed positionally because the column name
    contains a space and cannot be a Python keyword argument.
    """
    base = {
        "Date": "01-Jan-2023",
        "Description": "Buy",
        "Stock Description": stock_description,
        "Price": 100,
        "Debit": 0,
        "Credit": 0,
    }
    base.update(overrides)
    return pd.Series(base)


class TestProcessTransactionRow:
    """Cover each transaction-type branch and edge cases.

    Uses ``transaction=True`` because ``_process_transaction_row`` awaits
    ``transaction_exists`` (which runs DB I/O on a worker thread via
    ``database_sync_to_async``); SQLite needs transactional mode for that.
    """

    pytestmark = [
        pytest.mark.django_db(transaction=True),
        pytest.mark.asyncio,
    ]

    async def test_buy_transaction_computes_quantity_from_debit_and_price(
        self, user, account, asset
    ):
        # debit 1000 / price 100 => quantity 10.
        result, status = await _process_transaction_row(
            _row(Description="Buy", Debit=1000, Credit=0, Price=100),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_BUY
        assert result["quantity"] == Decimal("10")
        assert result["price"] == Decimal("100")
        assert result["currency"] == "GBP"
        assert result["investor"] is user
        assert result["account"] is account
        assert result["security"] == asset

    @pytest.mark.asyncio
    async def test_sell_transaction_computes_negative_quantity_from_credit(
        self, user, account, asset
    ):
        # credit 600 / price 100 => quantity -6.
        result, status = await _process_transaction_row(
            _row(Description="Sell", Debit=0, Credit=600, Price=100),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_SELL
        assert result["quantity"] == Decimal("-6")
        assert result["price"] == Decimal("100")

    @pytest.mark.asyncio
    async def test_dividend_sets_cash_flow_from_credit(self, user, account, asset):
        result, status = await _process_transaction_row(
            _row(Description="Dividend", Debit=0, Credit=75, Price=0),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_DIVIDEND
        assert result["cash_flow"] == Decimal("75")
        assert result["security"] == asset

    @pytest.mark.asyncio
    async def test_interest_income_sets_cash_flow(self, user, account):
        result, status = await _process_transaction_row(
            _row("", Description="Gross interest", Debit=0, Credit=25),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_INTEREST_INCOME
        assert result["cash_flow"] == Decimal("25")
        assert result["security"] is None

    @pytest.mark.asyncio
    async def test_cash_in_subscriptions(self, user, account):
        result, status = await _process_transaction_row(
            _row(
                "",
                Description="Stocks & Shares Subs",
                Debit=0,
                Credit=500,
            ),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_CASH_IN
        assert result["cash_flow"] == Decimal("500")

    @pytest.mark.asyncio
    async def test_cash_out_bacs_payment_negates_debit(self, user, account):
        result, status = await _process_transaction_row(
            _row(
                "",
                Description="BACS P'MNT",
                Debit=300,
                Credit=0,
            ),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_CASH_OUT
        # Cash out negates the debit.
        assert result["cash_flow"] == Decimal("-300")

    @pytest.mark.asyncio
    async def test_broker_commission_negates_debit(self, user, account):
        result, status = await _process_transaction_row(
            _row(
                "",
                Description="Platform Charge",
                Debit=120,
                Credit=0,
            ),
            user,
            account,
            "GBP",
        )
        assert status == "new"
        assert result["type"] == TRANSACTION_TYPE_BROKER_COMMISSION
        assert result["commission"] == Decimal("-120")

    @pytest.mark.asyncio
    async def test_skip_balance_rows(self, user, account):
        result, status = await _process_transaction_row(
            _row(Description="* BALANCE B/F *"), user, account, "GBP"
        )
        assert result is None
        assert status == "skipped"

    @pytest.mark.asyncio
    async def test_skip_rows_with_nan_date(self, user, account):
        result, status = await _process_transaction_row(
            _row(Date=pd.NA), user, account, "GBP"
        )
        assert result is None
        assert status == "skipped"

    @pytest.mark.asyncio
    async def test_unknown_security_requires_mapping(self, user, account, asset):
        # Security description does not match any investor asset => mapping.
        result, status = await _process_transaction_row(
            _row("Unknown Asset", Description="Buy", Debit=1000, Price=100),
            user,
            account,
            "GBP",
        )
        assert status == "mapping_required"
        assert result["mapping_details"]["security_description"] == "Unknown Asset"
        assert "transaction_details" in result

    @pytest.mark.asyncio
    async def test_duplicate_existing_transaction_is_detected(
        self, user, account, asset
    ):
        # Pre-create the same Buy the row would produce, so transaction_exists
        # returns True and the row is reported as duplicate. ``_process_transaction_row``
        # parses the row's Date string into a midnight pandas Timestamp; the
        # persisted row must use the same date so the duplicate Q query matches.
        await database_sync_to_async(Transactions.objects.create)(
            investor=user,
            account=account,
            security=asset,
            currency="GBP",
            type=TRANSACTION_TYPE_BUY,
            date=date(2023, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("100"),
        )
        result, status = await _process_transaction_row(
            _row(Description="Buy", Debit=1000, Credit=0, Price=100),
            user,
            account,
            "GBP",
        )
        assert status == "duplicate"
        assert result is None

    @pytest.mark.asyncio
    async def test_value_error_returns_error_status(self, user, account):
        # Price of 0 with a Buy would cause a divide-by-zero -> caught as
        # error (ZeroDivisionError is a subclass of ArithmeticError, caught by
        # the generic Exception handler and reported as "error").
        result, status = await _process_transaction_row(
            _row(Description="Buy", Debit=1000, Credit=0, Price=0),
            user,
            account,
            "GBP",
        )
        assert status == "error"
        assert result is None


# =============================================================================
# check_broker_token_active -- mocked broker_api lifecycle
# =============================================================================


def _make_get_broker_api(mock_api):
    """Build a replacement for ``_get_broker_api``.

    ``_get_broker_api()`` returns the real ``get_broker_api`` callable, which
    in turn is awaited with a broker to produce a broker_api instance. We
    reproduce that two-step shape with a plain function so the await in the
    code under test resolves cleanly.
    """

    async def _factory(_broker):
        return mock_api

    def _get_broker_api():
        return _factory

    return _get_broker_api


class TestCheckBrokerTokenActive:
    """``check_broker_token_active`` returns a bool based on broker_api state."""

    def _mock_api(self, connected=True, valid=True):
        mock_api = MagicMock()
        mock_api.connect = AsyncMock(return_value=connected)
        mock_api.validate_connection = AsyncMock(return_value=valid)
        mock_api.disconnect = AsyncMock(return_value=None)
        return mock_api

    @pytest.mark.asyncio
    async def test_returns_true_when_connect_and_validate_succeed(self, broker):
        mock_api = self._mock_api(connected=True, valid=True)
        with patch(
            "services.importer._get_broker_api",
            _make_get_broker_api(mock_api),
        ):
            result = await check_broker_token_active(broker)

        assert result is True
        mock_api.connect.assert_awaited_once_with(broker.investor)
        mock_api.validate_connection.assert_awaited_once()
        mock_api.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_connect_fails(self, broker):
        mock_api = self._mock_api(connected=False, valid=True)
        with patch(
            "services.importer._get_broker_api",
            _make_get_broker_api(mock_api),
        ):
            result = await check_broker_token_active(broker)

        assert result is False
        mock_api.validate_connection.assert_not_called()
        mock_api.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_validation_fails(self, broker):
        mock_api = self._mock_api(connected=True, valid=False)
        with patch(
            "services.importer._get_broker_api",
            _make_get_broker_api(mock_api),
        ):
            result = await check_broker_token_active(broker)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_api_initialization_returns_none(self, broker):
        # _factory returns None -> the ``if not broker_api`` branch fires.
        async def _factory(_broker):
            return None

        def _get_broker_api():
            return _factory

        with patch("services.importer._get_broker_api", _get_broker_api):
            result = await check_broker_token_active(broker)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_unexpected_exception(self, broker):
        def _get_broker_api():
            raise RuntimeError("boom")

        with patch("services.importer._get_broker_api", _get_broker_api):
            result = await check_broker_token_active(broker)
        assert result is False


# =============================================================================
# match_tinkoff_broker_account -- native_id matching logic
# =============================================================================


class _AccountType:
    """Stand-in for a protobuf enum whose str() includes ACCOUNT_TYPE_."""

    def __str__(self):
        return "ACCOUNT_TYPE_INVESTMENT"


class _AccountStatus:
    def __str__(self):
        return "ACCOUNT_STATUS_OPEN"


class _AccessLevel:
    def __str__(self):
        return "ACCOUNT_ACCESS_LEVEL_FULL_ACCESS"


def _tinkoff_account(acc_id, name="Invest account"):
    """Build a fake Tinkoff account object exposing the attributes used."""
    acc = MagicMock()
    acc.id = acc_id
    acc.name = name
    acc.type = _AccountType()
    acc.status = _AccountStatus()
    acc.opened_date = date(2023, 5, 1)
    acc.access_level = _AccessLevel()
    return acc


class TestMatchTinkoffBrokerAccount:
    """Cover matched / unmatched branches of ``match_tinkoff_broker_account``."""

    # These tests cross async/thread boundaries (database_sync_to_async) over
    # SQLite, so they need transactional DB access to avoid "database table is
    # locked" errors.
    pytestmark = [
        pytest.mark.django_db(transaction=True),
        pytest.mark.asyncio,
    ]

    def _patch_broker_api(self, connected=True):
        """Patch the broker_api lifecycle used by match_tinkoff_broker_account."""
        mock_api = MagicMock()
        mock_api.connect = AsyncMock(return_value=connected)
        mock_api.disconnect = AsyncMock(return_value=None)
        return (
            patch(
                "services.importer._get_broker_api",
                _make_get_broker_api(mock_api),
            ),
            mock_api,
        )

    def _patch_tinkoff_client(self, accounts):
        """Patch the t_tech Client context manager to return fake accounts."""
        accounts_response = MagicMock()
        accounts_response.accounts = accounts

        client = MagicMock()
        client.users.get_accounts.return_value = accounts_response

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patch("t_tech.invest.Client", mock_client_cls)

    async def test_matches_db_account_by_native_id(
        self, user, broker, account
    ):
        # The shared `account` fixture has no native_id; set one so it matches.
        account.native_id = "TINKOFF-123"
        account.is_active = True
        await database_sync_to_async(account.save)()

        api_patch, _ = self._patch_broker_api(connected=True)
        with api_patch, self._patch_tinkoff_client(
            [_tinkoff_account("TINKOFF-123")]
        ), patch(
            "services.importer.get_user_token", new=AsyncMock(return_value="tok")
        ):
            matched, unmatched_t, unmatched_db = await match_tinkoff_broker_account(
                broker, user
            )

        assert "TINKOFF-123" in matched
        assert matched["TINKOFF-123"]["db_account"]["id"] == account.id
        assert matched["TINKOFF-123"]["db_account"]["source"] == "database"
        assert matched["TINKOFF-123"]["tinkoff_account"]["name"] == "Invest account"
        # No unmatched on either side.
        assert unmatched_t == []
        assert unmatched_db == []

    async def test_unmatched_tinkoff_account_has_no_db_counterpart(
        self, user, broker, account
    ):
        # DB account has a different native_id.
        account.native_id = "DB-ONLY-456"
        account.is_active = True
        await database_sync_to_async(account.save)()

        api_patch, _ = self._patch_broker_api(connected=True)
        with api_patch, self._patch_tinkoff_client(
            [_tinkoff_account("TINKOFF-999")]
        ), patch(
            "services.importer.get_user_token", new=AsyncMock(return_value="tok")
        ):
            matched, unmatched_t, unmatched_db = await match_tinkoff_broker_account(
                broker, user
            )

        assert matched == {}
        assert [a["id"] for a in unmatched_t] == ["TINKOFF-999"]
        assert [a["native_id"] for a in unmatched_db] == ["DB-ONLY-456"]

    async def test_inactive_db_accounts_are_excluded_from_matching(
        self, user, broker
    ):
        # Only an inactive DB account exists -> query filters is_active=True.
        await database_sync_to_async(Accounts.objects.create)(
            broker=broker,
            name="Inactive Account",
            native_id="TINKOFF-123",
            is_active=False,
        )

        api_patch, _ = self._patch_broker_api(connected=True)
        with api_patch, self._patch_tinkoff_client(
            [_tinkoff_account("TINKOFF-123")]
        ), patch(
            "services.importer.get_user_token", new=AsyncMock(return_value="tok")
        ):
            matched, unmatched_t, unmatched_db = await match_tinkoff_broker_account(
                broker, user
            )

        assert matched == {}
        assert [a["id"] for a in unmatched_t] == ["TINKOFF-123"]
        # Inactive DB account is not returned.
        assert unmatched_db == []

    async def test_connection_failure_raises_value_error(self, broker, user):
        api_patch, _ = self._patch_broker_api(connected=False)
        with api_patch:
            with pytest.raises(ValueError, match="Failed to match broker accounts"):
                await match_tinkoff_broker_account(broker, user)
