"""Tests for the OKX Trading History CSV import parser.

Covers:
- The CSV-to-payload adapter (``build_okx_csv_events``): spot trade pairing
  (two bill rows -> one event), option fill mapping, option settlement
  (expiration) mapping, and transfer skipping.
- Timezone conversion (UTC+3 wall-clock -> UTC ms-epoch).
- The full async parser (``parse_okx_trading_csv``) against a temp CSV fixture,
  verifying events persist via ``persist_crypto_exchange_event`` with
  ``import_provider="okx_csv"`` and dedup on re-import.

All monetary values use ``Decimal``.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from channels.db import database_sync_to_async

from common.models import Accounts, Brokers, Transactions
from services.importer import (
    OKX_CSV_IMPORT_PROVIDER,
    _okx_time_to_utc_ms,
    _parse_okx_csv_tz_offset,
    build_okx_csv_events,
    parse_okx_trading_csv,
)


# ---------------------------------------------------------------------------
# CSV fixtures
# ---------------------------------------------------------------------------

OKX_CSV_HEADER = (
    "\ufeffUID:652654290649420911,"
    "\ufeffAccount Type:Main,"
    "\ufeffTime Zone:UTC+3\n"
)
OKX_CSV_COLUMNS = (
    "\ufeffid,Order id,Time,Trade Type,Symbol,Action,Amount,Trading Unit,"
    "Filled Price,PnL,Fee,Fee Unit,Position Change,Position Balance,"
    "Balance Change,Balance,Balance Unit\n"
)


def _write_okx_csv(path, rows):
    """Write an OKX Trading History CSV with the BOM-prefixed metadata + columns.

    ``rows`` is a list of dicts whose keys match the OKX column names. Missing
    keys are emitted as empty fields. The leading BOM on each ``id`` mirrors the
    real export.
    """
    columns = [
        "id", "Order id", "Time", "Trade Type", "Symbol", "Action", "Amount",
        "Trading Unit", "Filled Price", "PnL", "Fee", "Fee Unit",
        "Position Change", "Position Balance", "Balance Change", "Balance",
        "Balance Unit",
    ]
    lines = [OKX_CSV_HEADER, OKX_CSV_COLUMNS]
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col, "")
            if col == "id" and value:
                value = f"\ufeff{value}"
            cells.append(str(value))
        lines.append(",".join(cells) + "\n")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.writelines(lines)


def _spot_buy_pair():
    """A BTC-USDT BUY order: two bill rows sharing one Order id.

    Base leg (Balance Unit=BTC, Action=Buy) carries the fill; quote leg
    (Balance Unit=USDT, Action=Sell) carries the fee. Mirrors the real export
    shape exactly (both rows have Trading Unit=BTC).
    """
    return [
        {
            "id": "3603866656859267073",
            "Order id": "3603866124417540096",
            "Time": "2026-05-27 21:19:55",
            "Trade Type": "Spot",
            "Symbol": "BTC-USDT",
            "Action": "Sell",
            "Amount": "5002.162499",
            "Trading Unit": "BTC",
            "Filled Price": "74837.4",
            "PnL": "0.0",
            "Fee": "0.000000",
            "Fee Unit": "USDT",
            "Position Change": "0.000000",
            "Position Balance": "0.000000",
            "Balance Change": "-5002.162499",
            "Balance": "0.000000",
            "Balance Unit": "USDT",
        },
        {
            "id": "3603866656859267072",
            "Order id": "3603866124417540096",
            "Time": "2026-05-27 21:19:55",
            "Trade Type": "Spot",
            "Symbol": "BTC-USDT",
            "Action": "Buy",
            "Amount": "0.066840",
            "Trading Unit": "BTC",
            "Filled Price": "74837.4",
            "PnL": "0.0",
            "Fee": "-0.000067",
            "Fee Unit": "BTC",
            "Position Change": "0.000000",
            "Position Balance": "0.000000",
            "Balance Change": "0.066774",
            "Balance": "0.000000",
            "Balance Unit": "BTC",
        },
    ]


# ---------------------------------------------------------------------------
# Timezone parsing / conversion
# ---------------------------------------------------------------------------


def test_parse_tz_offset_extracts_utc_plus_3():
    offset = _parse_okx_csv_tz_offset(OKX_CSV_HEADER)

    assert offset == timedelta(hours=3)


def test_parse_tz_offset_defaults_to_utc_when_missing():
    assert _parse_okx_csv_tz_offset("UID:123,Account Type:Main\n") == timedelta(0)


def test_okx_time_to_utc_ms_converts_utc_plus_3_to_utc_epoch():
    # 21:19:55 UTC+3 == 18:19:55 UTC on 2026-05-27.
    offset = timedelta(hours=3)
    ms = _okx_time_to_utc_ms("2026-05-27 21:19:55", offset)

    expected_dt = datetime(2026, 5, 27, 18, 19, 55, tzinfo=timezone.utc)
    assert ms == int(expected_dt.timestamp() * 1000)
    # Round-trip: the converted instant is 3h earlier than the wall clock.
    assert datetime.fromtimestamp(ms / 1000, tz=timezone.utc) == expected_dt


def test_okx_time_to_utc_ms_negative_offset():
    # UTC-5 wall clock should ADD 5h to reach UTC.
    ms = _okx_time_to_utc_ms("2026-01-02 00:00:00", timedelta(hours=-5))
    expected_dt = datetime(2026, 1, 2, 5, 0, 0, tzinfo=timezone.utc)

    assert ms == int(expected_dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# build_okx_csv_events: adapter
# ---------------------------------------------------------------------------


def _df_from_rows(rows):
    df = pd.DataFrame(rows, columns=[
        "id", "Order id", "Time", "Trade Type", "Symbol", "Action", "Amount",
        "Trading Unit", "Filled Price", "PnL", "Fee", "Fee Unit",
        "Position Change", "Position Balance", "Balance Change", "Balance",
        "Balance Unit",
    ])
    df.columns = [c.lstrip("\ufeff").strip() for c in df.columns]
    return df


def test_spot_pair_collapses_two_rows_into_one_event():
    df = _df_from_rows(_spot_buy_pair())
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, source_id = events[0]
    assert payload["__kind"] == "spot"
    # Base leg drives the payload (Balance Unit=BTC row, Action=Buy).
    assert payload["instId"] == "BTC-USDT"
    assert payload["side"] == "buy"
    assert payload["fillSz"] == "0.066840"
    assert payload["fillPx"] == "74837.4"
    assert payload["tradeId"] == "3603866656859267072"
    assert payload["ordId"] == "3603866124417540096"
    # Fee sourced from the fee-bearing leg (BTC leg, -0.000067).
    assert payload["fee"] == "-0.000067"
    assert payload["feeCcy"] == "BTC"
    # source_id is the base leg's id.
    assert source_id == "3603866656859267072"
    # Timestamp converted from UTC+3 to UTC ms-epoch.
    expected_dt = datetime(2026, 5, 27, 18, 19, 55, tzinfo=timezone.utc)
    assert payload["fillTime"] == str(int(expected_dt.timestamp() * 1000))


def test_spot_sell_order_base_leg_action_is_sell():
    """A SELL order's base leg carries Action=Sell (and thus side=sell)."""
    rows = [
        # quote leg (USDT received)
        {
            "id": "2235363508130193409", "Order id": "2235362236081676288",
            "Time": "2026-06-08 11:17:31", "Trade Type": "Spot",
            "Symbol": "TRUMP-USDT", "Action": "Buy", "Amount": "11.255449",
            "Trading Unit": "TRUMP", "Filled Price": "16.557", "PnL": "0.0",
            "Fee": "-0.011255", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "11.244193",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
        # base leg (TRUMP given up)
        {
            "id": "2235363508130193408", "Order id": "2235362236081676288",
            "Time": "2026-06-08 11:17:31", "Trade Type": "Spot",
            "Symbol": "TRUMP-USDT", "Action": "Sell", "Amount": "0.6798",
            "Trading Unit": "TRUMP", "Filled Price": "16.557", "PnL": "0.0",
            "Fee": "0.000000", "Fee Unit": "TRUMP", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-0.6798",
            "Balance": "0.0", "Balance Unit": "TRUMP",
        },
    ]
    df = _df_from_rows(rows)
    events, _ = build_okx_csv_events(df, timedelta(hours=3))

    assert len(events) == 1
    payload, source_id = events[0]
    assert payload["side"] == "sell"
    assert payload["fillSz"] == "0.6798"
    assert payload["tradeId"] == "2235363508130193408"
    # Fee comes from the USDT leg.
    assert payload["fee"] == "-0.011255"
    assert payload["feeCcy"] == "USDT"


def test_spot_order_with_multiple_fills_emits_one_event_per_base_leg():
    """A single Order id spanning N fills (N base legs + N quote legs) yields N events.

    Mirrors the real export where one order carries many individual fills; each
    base leg is a distinct trade keyed by its own ``id``.
    """
    rows = [
        # fill 1 - base leg (BTC, carries fee)
        {
            "id": "1000000000000000001", "Order id": "9999999999999999999",
            "Time": "2026-06-22 20:03:00", "Trade Type": "Spot",
            "Symbol": "BTC-USDT", "Action": "Buy", "Amount": "0.053791",
            "Trading Unit": "BTC", "Filled Price": "64702.8", "PnL": "0.0",
            "Fee": "-0.000054", "Fee Unit": "BTC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "0.053737",
            "Balance": "0.0", "Balance Unit": "BTC",
        },
        # fill 1 - quote leg (USDT)
        {
            "id": "1000000000000000002", "Order id": "9999999999999999999",
            "Time": "2026-06-22 20:03:00", "Trade Type": "Spot",
            "Symbol": "BTC-USDT", "Action": "Sell", "Amount": "138.342351",
            "Trading Unit": "BTC", "Filled Price": "64702.8", "PnL": "0.0",
            "Fee": "0.000000", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-138.342351",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
        # fill 2 - base leg (BTC, carries fee)
        {
            "id": "1000000000000000003", "Order id": "9999999999999999999",
            "Time": "2026-06-22 20:03:00", "Trade Type": "Spot",
            "Symbol": "BTC-USDT", "Action": "Buy", "Amount": "0.186056",
            "Trading Unit": "BTC", "Filled Price": "64702.8", "PnL": "0.0",
            "Fee": "-0.000186", "Fee Unit": "BTC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "0.185870",
            "Balance": "0.0", "Balance Unit": "BTC",
        },
        # fill 2 - quote leg (USDT)
        {
            "id": "1000000000000000004", "Order id": "9999999999999999999",
            "Time": "2026-06-22 20:03:00", "Trade Type": "Spot",
            "Symbol": "BTC-USDT", "Action": "Sell", "Amount": "2239.278500",
            "Trading Unit": "BTC", "Filled Price": "64702.8", "PnL": "0.0",
            "Fee": "0.000000", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-2239.278500",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    # Two base legs -> two events; quote legs are not emitted.
    assert len(events) == 2
    assert skipped == []
    trade_ids = {e[0]["tradeId"] for e in events}
    assert trade_ids == {"1000000000000000001", "1000000000000000003"}
    # Each event carries its own base-leg fee.
    fees = {e[0]["tradeId"]: e[0]["fee"] for e in events}
    assert fees["1000000000000000001"] == "-0.000054"
    assert fees["1000000000000000003"] == "-0.000186"


def test_usdc_usdt_convert_emits_fx_event():
    """USDC-USDT-CONVERT (stablecoin<->stablecoin) becomes an FX payload, not a
    spot trade. Side is inferred from Balance Change sign (empty Action)."""
    rows = [
        {  # USDC given up
            "id": "2602510860429074432", "Order id": "2602510860294856704",
            "Time": "2025-06-16 11:41:07", "Trade Type": "Spot",
            "Symbol": "USDC-USDT-CONVERT", "Action": "", "Amount": "103.836812",
            "Trading Unit": "USDC", "Filled Price": "0.993950", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-103.836812",
            "Balance": "0.0", "Balance Unit": "USDC",
        },
        {  # USDT received
            "id": "2602510860429074433", "Order id": "2602510860294856704",
            "Time": "2025-06-16 11:41:07", "Trade Type": "Spot",
            "Symbol": "USDC-USDT-CONVERT", "Action": "", "Amount": "103.208630",
            "Trading Unit": "USDC", "Filled Price": "0.993950", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "103.208630",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, _ = events[0]
    assert payload["__kind"] == "fx"
    assert payload["from_ccy"] == "USDC"
    assert payload["to_ccy"] == "USDT"
    assert payload["from_amount"] == "103.836812"
    assert payload["to_amount"] == "103.208630"


def test_usdc_usdt_spot_trade_emits_fx_event():
    """A normal USDC-USDT spot trade (NO -CONVERT suffix, Action=Buy/Sell) is
    still a stablecoin<->stablecoin conversion -> FX. Regression for OKX CSV
    Bug 2: previously only -CONVERT symbols triggered FX routing."""
    rows = [
        {  # USDT given up (negative Balance Change)
            "id": "2173842814334967810", "Order id": "2173842814301413376",
            "Time": "2025-01-19 14:59:24", "Trade Type": "Spot",
            "Symbol": "USDC-USDT", "Action": "Sell", "Amount": "100.00997897",
            "Trading Unit": "USDC", "Filled Price": "1.00220000", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-100.00997897",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
        {  # USDC received (positive Balance Change)
            "id": "2173842814334967809", "Order id": "2173842814301413376",
            "Time": "2025-01-19 14:59:24", "Trade Type": "Spot",
            "Symbol": "USDC-USDT", "Action": "Buy", "Amount": "99.79044000",
            "Trading Unit": "USDC", "Filled Price": "1.00220000", "PnL": "0.0",
            "Fee": "-0.09979044", "Fee Unit": "USDC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "99.69064956",
            "Balance": "0.0", "Balance Unit": "USDC",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, _ = events[0]
    assert payload["__kind"] == "fx"
    # from = USDT (negative leg), to = USDC (positive leg)
    assert payload["from_ccy"] == "USDT"
    assert payload["to_ccy"] == "USDC"
    # Amounts are GROSS (the trade fill quantities from the Amount column),
    # NOT the Balance Change (which is net of fee). The fee is captured
    # separately so it isn't double-subtracted by get_cash_flow_by_currency.
    assert payload["from_amount"] == "100.00997897"  # gross USDT (no fee on this leg)
    assert payload["to_amount"] == "99.79044000"  # gross USDC (NOT 99.69064956 net)
    # Fee captured from the fee-bearing leg (USDC leg), in its native currency.
    assert payload["fee"] == "-0.09979044"
    assert payload["fee_ccy"] == "USDC"


def test_btc_usdt_convert_emits_spot_event():
    """BTC-USDT-CONVERT (crypto<->stablecoin) is a normal purchase: emits a spot
    payload with side inferred from the base (BTC) leg's Balance Change sign."""
    rows = [
        {  # BTC received (buy)
            "id": "2893075670726385664", "Order id": "2893075670558613504",
            "Time": "2025-09-24 17:06:13", "Trade Type": "Spot",
            "Symbol": "BTC-USDT-CONVERT", "Action": "", "Amount": "0.002839",
            "Trading Unit": "BTC", "Filled Price": "113345.97", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "BTC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "0.002839",
            "Balance": "0.0", "Balance Unit": "BTC",
        },
        {  # USDT given up
            "id": "2893075670726385665", "Order id": "2893075670558613504",
            "Time": "2025-09-24 17:06:13", "Trade Type": "Spot",
            "Symbol": "BTC-USDT-CONVERT", "Action": "", "Amount": "321.819075",
            "Trading Unit": "BTC", "Filled Price": "113345.97", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-321.819075",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, _ = events[0]
    assert payload["__kind"] == "spot"
    assert payload["instId"] == "BTC-USDT"  # CONVERT suffix stripped
    assert payload["side"] == "buy"  # BTC Balance Change positive
    assert payload["fillSz"] == "0.002839"
    # Price is DERIVED from the actual quote movement / base amount
    # (321.819075 / 0.002839), NOT the CSV's approximate Filled Price
    # (113345.97).
    assert Decimal(payload["fillPx"]) == Decimal("321.819075") / Decimal("0.002839")
    # The actual quote settlement amount is passed directly so cash_flow
    # uses it instead of the approximate qty*price product.
    assert payload["quoteCashAmount"] == "321.819075"


def test_option_fill_maps_to_option_payload():
    row = {
        "id": "3604219617540087810", "Order id": "3604219617506533376",
        "Time": "2026-05-28 00:15:14", "Trade Type": "Option",
        "Symbol": "BTC-USD-260605-80000-C", "Action": "Sell", "Amount": "7.0",
        "Trading Unit": "cont", "Filled Price": "0.002200", "PnL": "0.0",
        "Fee": "-0.000011", "Fee Unit": "BTC", "Position Change": "0.007162",
        "Position Balance": "0.0", "Balance Change": "0.007162",
        "Balance": "0.0", "Balance Unit": "BTC",
    }
    df = _df_from_rows([row])
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, source_id = events[0]
    assert payload["__kind"] == "option_fill"
    assert payload["instId"] == "BTC-USD-260605-80000-C"
    assert payload["side"] == "sell"
    assert payload["fillSz"] == "7.0"
    assert payload["fillPx"] == "0.002200"
    assert payload["tradeId"] == "3604219617540087810"
    assert payload["ordId"] == "3604219617506533376"
    assert payload["fee"] == "-0.000011"
    assert payload["feeCcy"] == "BTC"
    assert source_id == "3604219617540087810"
    # UTC+3 00:15:14 -> UTC 21:15:14 previous day.
    expected_dt = datetime(2026, 5, 27, 21, 15, 14, tzinfo=timezone.utc)
    assert payload["fillTime"] == str(int(expected_dt.timestamp() * 1000))


def test_option_expiration_maps_to_settlement_payload():
    row = {
        "id": "3628711646064058370", "Order id": "0",
        "Time": "2026-06-05 11:00:34", "Trade Type": "Option",
        "Symbol": "BTC-USD-260605-80000-C", "Action": "Expired OTM",
        "Amount": "7.0", "Trading Unit": "cont", "Filled Price": "62703.943334",
        "PnL": "0.000154", "Fee": "0.000000", "Fee Unit": "BTC",
        "Position Change": "-0.007162", "Position Balance": "0.0",
        "Balance Change": "0.007162", "Balance": "0.0", "Balance Unit": "BTC",
    }
    df = _df_from_rows([row])
    events, _ = build_okx_csv_events(df, timedelta(hours=3))

    assert len(events) == 1
    payload, source_id = events[0]
    assert payload["__kind"] == "option_settlement"
    assert payload["ccy"] == "BTC"
    # balChg = Balance Change (collateral RELEASED, positive), NOT Position Change.
    assert payload["balChg"] == "0.007162"
    assert payload["px"] == "62703.943334"
    assert payload["billId"] == "3628711646064058370"
    assert payload["ordId"] == ""
    expected_dt = datetime(2026, 6, 5, 8, 0, 34, tzinfo=timezone.utc)
    assert payload["ts"] == str(int(expected_dt.timestamp() * 1000))


def test_transfer_rows_become_events_not_skipped():
    """Transfers are now imported: stablecoins route to cash (deposit/withdrawal),
    non-stablecoins route to crypto transfers. Nothing is skipped."""
    rows = [
        # non-stablecoin transfer out (BTC)
        {
            "id": "3679092537441165312", "Order id": "3679092536973701120",
            "Time": "2026-06-22 20:05:01", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "BTC", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-0.45849457", "Balance": "0.0", "Balance Unit": "BTC",
        },
        # stablecoin transfer out (USDT) -> withdrawal
        {
            "id": "3679091815014244352", "Order id": "3679091814748102656",
            "Time": "2026-06-22 20:04:40", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "USDT", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-300.00389139", "Balance": "0.0", "Balance Unit": "USDT",
        },
        # stablecoin transfer in (USDT) -> deposit
        {
            "id": "2173839971167281152", "Order id": "2173839971033657344",
            "Time": "2025-01-19 14:57:59", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer in", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "USDT", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "357.14000000", "Balance": "357.14", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []  # nothing skipped anymore
    assert len(events) == 3
    kinds = [e[0]["__kind"] for e in events]
    assert kinds == ["transfer", "transfer", "transfer"]
    # Stablecoin in -> deposit; stablecoin out -> withdrawal; BTC out -> transfer.
    cats = [e[0]["category"] for e in events]
    assert cats == ["transfer", "withdrawal", "deposit"]
    # Signed amount parsed from Balance Change, not Amount.
    amts = [e[0]["amount"] for e in events]
    assert amts == ["-0.45849457", "-300.00389139", "357.14000000"]
    ccys = [e[0]["ccy"] for e in events]
    assert ccys == ["BTC", "USDT", "USDT"]


def test_mixed_csv_emits_events_and_skips_transfers():
    """Spot pair + option fill + transfer together in one file."""
    df = _df_from_rows(_spot_buy_pair() + [
        {
            "id": "3604219617540087810", "Order id": "3604219617506533376",
            "Time": "2026-05-28 00:15:14", "Trade Type": "Option",
            "Symbol": "BTC-USD-260605-80000-C", "Action": "Sell", "Amount": "7.0",
            "Trading Unit": "cont", "Filled Price": "0.002200", "PnL": "0.0",
            "Fee": "-0.000011", "Fee Unit": "BTC", "Position Change": "0.007162",
            "Position Balance": "0.0", "Balance Change": "0.007162",
            "Balance": "0.0", "Balance Unit": "BTC",
        },
        {
            "id": "3679092537441165312", "Order id": "3679092536973701120",
            "Time": "2026-06-22 20:05:01", "Trade Type": "Transfer",
            "Symbol": "", "Action": "Transfer out", "Amount": "0",
            "Trading Unit": "cont", "Filled Price": "0.00000000", "PnL": "0.0",
            "Fee": "0.00000000", "Fee Unit": "BTC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-0.45849457",
            "Balance": "0.0", "Balance Unit": "BTC",
        },
    ])
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert len(events) == 3  # one spot, one option fill, one transfer
    assert {e[0]["__kind"] for e in events} == {"spot", "option_fill", "transfer"}
    assert skipped == []


# ---------------------------------------------------------------------------
# Full async parser against a temp CSV fixture (DB-backed)
# ---------------------------------------------------------------------------


@pytest.fixture
def okx_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Unified", native_id="okx-main")


async def _drain(async_gen):
    """Collect every yielded status dict from an async generator into a list."""
    out = []
    async for update in async_gen:
        out.append(update)
    return out


@database_sync_to_async
def _persisted_txs(user, account):
    """Return the list of Transactions for the user/account (async-safe read).

    Django forbids synchronous ORM calls inside an async test, so the post-
    import DB assertions go through ``database_sync_to_async``.
    """
    return list(Transactions.objects.filter(investor=user, account=account))


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_parser_persists_spot_trade_with_okx_csv_provider(tmp_path, user, okx_account):
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, _spot_buy_pair())

    updates = await _drain(
        parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False)
    )

    statuses = [u.get("status") for u in updates]
    # Initialization + progress + at least one transaction_saved + complete.
    assert statuses.count("initialization") >= 1
    assert "complete" in statuses
    saved = [u for u in updates if u.get("status") == "transaction_saved"]
    assert saved, "expected at least one transaction_saved update"

    # ONE row persisted under import_provider=okx_csv: the BTC base leg (the
    # real fill). The CSV's BTC fee on a BTC-USDT trade is CROSS-currency
    # relative to the USDT settlement; under the embedded multi-currency model
    # it attaches to the trade row's ``commission``/``commission_currency``
    # (commission=-0.000067, commission_currency=BTC) — it does NOT become a
    # separate row.
    txs = await _persisted_txs(user, okx_account)
    assert len(txs) == 1
    assert {t.import_provider for t in txs} == {OKX_CSV_IMPORT_PROVIDER}
    assert {t.import_event_type for t in txs} == {"trade"}
    # Base leg event id carries the base-leg CSV id.
    assert txs[0].import_event_id == "3603866656859267072:0"
    # The cross-currency BTC fee is embedded on the trade row's commission.
    assert txs[0].type == "Crypto trade in"
    assert txs[0].commission == Decimal("-0.000067")
    assert txs[0].commission_currency == "BTC"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_parser_dedups_on_reimport(tmp_path, user, okx_account):
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, _spot_buy_pair())

    await _drain(parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False))
    first_count = len(await _persisted_txs(user, okx_account))

    updates = await _drain(
        parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False)
    )

    # No new rows created on the second pass.
    assert len(await _persisted_txs(user, okx_account)) == first_count
    # The re-import yields duplicate_transaction (not transaction_saved).
    assert any(u.get("status") == "duplicate_transaction" for u in updates)
    assert not any(u.get("status") == "transaction_saved" for u in updates)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_parser_imports_transfers(tmp_path, user, okx_account):
    rows = _spot_buy_pair() + [
        {
            "id": "3679092537441165312", "Order id": "3679092536973701120",
            "Time": "2026-06-22 20:05:01", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "BTC", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-0.45849457", "Balance": "0.0", "Balance Unit": "BTC",
        },
    ]
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, rows)
    updates = await _drain(
        parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False)
    )
    complete = next(u for u in updates if u.get("status") == "complete")
    # 1 spot event (BTC base leg only — the BTC fee attaches to the trade row's
    # commission under the embedded model, no separate commission row) + 1
    # transfer event (1 leg) -> 2 persisted, 0 skipped.
    assert complete["data"]["skippedTransactions"] == 0
    assert complete["data"]["importedTransactions"] == 2
    txs = await _persisted_txs(user, okx_account)
    assert len(txs) == 2
    # The BTC transfer is a Crypto transfer out (quantity negative).
    transfer_tx = next(t for t in txs if t.type == "Crypto transfer out")
    assert transfer_tx.quantity == Decimal("-0.45849457")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_parser_imports_transfer_only(tmp_path, user, okx_account):
    """Transfer-only CSV: proves the transfer path end-to-end without depending
    on the spot pair (the spot quote-leg persistence is tracked separately and
    is unrelated to transfer import). Verifies both the non-stablecoin crypto
    transfer and the stablecoin cash-routing paths."""
    rows = [
        # non-stablecoin transfer out (BTC) -> Crypto transfer out
        {
            "id": "3679092537441165312", "Order id": "3679092536973701120",
            "Time": "2026-06-22 20:05:01", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "BTC", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-0.45849457", "Balance": "0.0", "Balance Unit": "BTC",
        },
        # stablecoin transfer in (USDT) -> Cash in (deposit)
        {
            "id": "2173839971167281152", "Order id": "2173839971033657344",
            "Time": "2025-01-19 14:57:59", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer in", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "USDT", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "357.14000000", "Balance": "357.14", "Balance Unit": "USDT",
        },
    ]
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, rows)
    updates = await _drain(
        parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False)
    )
    complete = next(u for u in updates if u.get("status") == "complete")
    # 2 transfer events (1 leg each), 0 skipped.
    assert complete["data"]["skippedTransactions"] == 0
    assert complete["data"]["importedTransactions"] == 2
    txs = await _persisted_txs(user, okx_account)
    assert len(txs) == 2
    # BTC out -> Crypto transfer out (negative quantity).
    btc_tx = next(t for t in txs if t.type == "Crypto transfer out")
    assert btc_tx.quantity == Decimal("-0.45849457")
    # USDT in -> Cash in (stablecoin cash leg: cash_flow positive, currency USDT).
    usdt_tx = next(t for t in txs if t.type == "Cash in")
    assert usdt_tx.cash_flow == Decimal("357.14000000")
    assert usdt_tx.currency == "USDT"
