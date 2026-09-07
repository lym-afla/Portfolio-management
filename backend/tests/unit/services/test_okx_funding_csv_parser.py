"""OKX Funding History CSV parser — row mapping + full async pipeline."""
from decimal import Decimal

import pytest
from channels.db import database_sync_to_async

from common.models import Accounts, Brokers, CustomUser, Transactions
from services.importer import (
    OKX_CSV_IMPORT_PROVIDER,
    _normalize_okx_funding_event,
    parse_okx_funding_csv,
)


# ---- CSV helpers (mirror test_okx_csv_parser.py's _write_okx_csv pattern) ----
FUNDING_COLUMNS = ["id", "Time", "Type", "Amount", "Before Balance", "After Balance", "Symbol"]


def _write_funding_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("\ufeffUID:652654290649420911,\ufeffAccount Type:Main,\ufeffTime Zone:UTC+3\n")
        fh.write("\ufeff" + ",".join(FUNDING_COLUMNS) + "\n")
        for r in rows:
            fh.write(",".join("\ufeff" + str(r.get(c, "")) for c in FUNDING_COLUMNS) + "\n")


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="fund-user", password="x")


@pytest.fixture
def funding_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")


@pytest.fixture
def trading_account(user):
    # Reuses the same broker if created, else makes one.
    broker, _ = Brokers.objects.get_or_create(investor=user, name="OKX", defaults={"country": "Crypto"})
    return Accounts.objects.create(broker=broker, name="OKX Trading", native_id="trading")


async def _drain(gen):
    return [u async for u in gen]


@database_sync_to_async
def _txs(user, account):
    return list(Transactions.objects.filter(investor=user, account=account).order_by("date", "id"))


# ---- row-to-event unit tests (no DB) ----
def test_internal_transfer_in_crypto_maps_to_transfer_in_with_group():
    payload = {
        "__kind": "funding", "category": "transfer", "event_type": "okx_internal_transfer",
        "ccy": "BTC", "amount": "0.45849457", "ts": "1750601102000",
        "billId": "103346514176", "group_id": "okx_xfer:btc:0.45849457:1750601102",
    }
    ev = _normalize_okx_funding_event(payload)
    assert ev.category == "transfer"
    assert ev.event_type == "okx_internal_transfer"
    assert ev.group_id == "okx_xfer:btc:0.45849457:1750601102"
    assert ev.provider_event_id == "csv_fund:103346514176"


def test_deposit_yield_stablecoin_maps_to_reward():
    payload = {
        "__kind": "funding", "category": "reward", "event_type": "okx_earn_yield",
        "ccy": "USDT", "amount": "0.01862035", "ts": "1750000000000",
        "billId": "103917829937", "group_id": "103917829937",
    }
    ev = _normalize_okx_funding_event(payload)
    assert ev.category == "reward"
    assert ev.event_type == "okx_earn_yield"


def test_earn_subscription_crypto_maps_to_transfer_out_exempt():
    payload = {
        "__kind": "funding", "category": "transfer", "event_type": "okx_earn_subscription",
        "ccy": "BTC", "amount": "-0.05912186", "ts": "1750600000000",
        "billId": "103346408767", "group_id": "103346408767",
    }
    ev = _normalize_okx_funding_event(payload)
    assert ev.event_type == "okx_earn_subscription"
    assert ev.legs[0]["asset"] == "BTC"


# ---- full async pipeline ----
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_funding_parser_persists_each_type(tmp_path, user, funding_account):
    rows = [
        {"id": "1", "Time": "2026-07-30 08:58:30", "Type": "Deposit yield", "Amount": "0.01862035", "Before Balance": "0.73387918", "After Balance": "0.75249953", "Symbol": "USDT"},
        {"id": "2", "Time": "2026-06-22 20:05:02", "Type": "From unified trading account", "Amount": "0.45849457", "Before Balance": "0", "After Balance": "0.45849457", "Symbol": "BTC"},
        {"id": "3", "Time": "2026-06-22 20:05:02", "Type": "Stake", "Amount": "-0.45849457", "Before Balance": "0.45849457", "After Balance": "0", "Symbol": "BTC"},
        {"id": "4", "Time": "2026-06-22 19:50:42", "Type": "Deposit", "Amount": "29994.781592", "Before Balance": "0", "After Balance": "29994.781592", "Symbol": "USDT"},
        {"id": "5", "Time": "2026-03-23 14:48:45", "Type": "Place an order", "Amount": "-400", "Before Balance": "400", "After Balance": "0", "Symbol": "USDT"},
    ]
    csv_path = tmp_path / "funding.csv"
    _write_funding_csv(csv_path, rows)

    updates = await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))
    assert "complete" in [u["status"] for u in updates]

    txs = await _txs(user, funding_account)
    assert len(txs) == 5
    by_event = {t.import_event_type for t in txs}
    assert by_event == {"okx_earn_yield", "okx_internal_transfer", "okx_earn_subscription", "okx_external_deposit", "okx_c2c_order"}
    # Lock the §4.2 funding Type -> Transaction.type mapping per row.
    by_type = {t.import_event_type: t.type for t in txs}
    assert by_type["okx_internal_transfer"] == "Crypto transfer in"   # BTC, From unified trading account
    assert by_type["okx_earn_subscription"] == "Crypto transfer out"  # BTC, Stake
    assert by_type["okx_earn_yield"] == "Interest income"             # USDT, Deposit yield (stablecoin reward)
    assert by_type["okx_external_deposit"] == "Cash in"               # USDT, external Deposit (stablecoin)
    assert by_type["okx_c2c_order"] == "Cash out"                     # USDT -400, Place an order
    # The internal-transfer BTC leg carries the synthesized group.
    btc_xfer = [t for t in txs if t.import_event_type == "okx_internal_transfer"][0]
    assert btc_xfer.type == "Crypto transfer in"
    assert btc_xfer.import_group_id.startswith("okx_xfer:btc:")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_funding_parser_dedups_on_reimport(tmp_path, user, funding_account):
    rows = [
        {"id": "1", "Time": "2026-07-30 08:58:30", "Type": "Deposit yield", "Amount": "0.01862035", "Before Balance": "0.73387918", "After Balance": "0.75249953", "Symbol": "USDT"},
    ]
    csv_path = tmp_path / "funding.csv"
    _write_funding_csv(csv_path, rows)

    await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))
    await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))

    txs = await _txs(user, funding_account)
    assert len(txs) == 1  # dedup on (provider, account, import_account_id, import_event_id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_unpriced_coin_yield_row_imports_without_error(tmp_path, user, funding_account):
    """A Deposit-yield row for a coin with no fiat price (BABY — no Yahoo
    quote) must import unpriced, not error the row. Root cause of the 176
    import errors on the real funding CSV: 'reward' was missing from the
    unpriced-tolerant category set in persist_crypto_exchange_event."""
    rows = [
        {"id": "10", "Time": "2026-07-30 08:51:04", "Type": "Deposit yield",
         "Amount": "2.20448012", "Before Balance": "1552.68",
         "After Balance": "1554.88", "Symbol": "BABY"},
    ]
    csv_path = tmp_path / "funding_baby.csv"
    _write_funding_csv(csv_path, rows)

    updates = await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))

    assert [u for u in updates if u.get("status") == "error"] == []
    txs = await _txs(user, funding_account)
    assert len(txs) == 1
    assert txs[0].type == "Crypto reward"
    assert txs[0].price is None  # unpriced, quantity still recorded


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_transfer_legs_persist_without_fiat_price(tmp_path, user, funding_account):
    """Transfer legs are position moves, not priced events. Even when the
    coin HAS a fiat price, persisting it alongside currency=coin makes value
    math double-multiply (price x get_fx_rate(coin->USD) = price^2) — the
    $2.1B closed-positions BTC bug."""
    from datetime import date

    from common.models import Prices
    from services.crypto_exchange import resolve_crypto_asset

    # Make BTC priceable: resolve the asset the persist layer will find and
    # seed a Prices row, so _quote_asset_fiat_price WOULD return 63952.
    btc = await database_sync_to_async(resolve_crypto_asset)("BTC", user)
    await database_sync_to_async(Prices.objects.create)(
        security=btc, date=date(2026, 6, 22), price=Decimal("63952.105469")
    )

    rows = [
        {"id": "20", "Time": "2026-06-22 20:05:02", "Type": "From unified trading account",
         "Amount": "0.45849457", "Before Balance": "0",
         "After Balance": "0.45849457", "Symbol": "BTC"},
        {"id": "21", "Time": "2026-06-22 20:05:02", "Type": "Stake",
         "Amount": "-0.45849457", "Before Balance": "0.45849457",
         "After Balance": "0", "Symbol": "BTC"},
    ]
    csv_path = tmp_path / "funding_xfer.csv"
    _write_funding_csv(csv_path, rows)

    await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))

    txs = await _txs(user, funding_account)
    assert len(txs) == 2
    for tx in txs:
        # Position moves carry no fiat price — valuation happens at calc
        # time via the Prices table / three-tier resolver.
        assert tx.price is None
        assert tx.currency == "BTC"  # coin denomination (balance-leak guard)
