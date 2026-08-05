import base64
import hashlib
import hmac
import time
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync

from common.models import Accounts, Brokers
from services.broker_api import BybitAPI, OKXAPI, get_broker_api
from services.crypto_exchange import CryptoExchangeEvent
from core.crypto_exchange_clients import (
    BybitClient,
    CryptoExchangeAPIError,
    OKXClient,
    _chunked_bybit_windows,
    _older_than_begin,
    _within_window,
)
from users.models import BybitApiToken, OKXApiToken


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=None, text=""):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error
        self.text = text

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def test_bybit_signature_uses_timestamp_key_window_and_query():
    client = BybitClient(api_key="key", api_secret="secret", testnet=True)
    headers = client._signed_headers(timestamp="1700000000000", payload="accountType=UNIFIED")
    expected = hmac.new(
        b"secret",
        b"1700000000000key5000accountType=UNIFIED",
        hashlib.sha256,
    ).hexdigest()

    assert headers["X-BAPI-API-KEY"] == "key"
    assert headers["X-BAPI-TIMESTAMP"] == "1700000000000"
    assert headers["X-BAPI-RECV-WINDOW"] == "5000"
    assert headers["X-BAPI-SIGN"] == expected


def test_okx_signature_uses_iso_timestamp_method_path_and_body():
    client = OKXClient(
        api_key="key", api_secret="secret", passphrase="pass", simulated_trading=True
    )
    timestamp = "2026-01-01T00:00:00.000Z"
    headers = client._signed_headers(timestamp, "GET", "/api/v5/account/balance?ccy=BTC", "")
    expected = base64.b64encode(
        hmac.new(
            b"secret",
            b"2026-01-01T00:00:00.000ZGET/api/v5/account/balance?ccy=BTC",
            hashlib.sha256,
        ).digest()
    ).decode()

    assert headers["OK-ACCESS-KEY"] == "key"
    assert headers["OK-ACCESS-PASSPHRASE"] == "pass"
    assert headers["OK-ACCESS-SIGN"] == expected
    assert headers["Content-Type"] == "application/json"
    assert headers["x-simulated-trading"] == "1"


def test_bybit_base_url_switches_between_testnet_and_production():
    assert BybitClient(api_key="key", api_secret="secret", testnet=True).base_url == (
        "https://api-testnet.bybit.com"
    )
    assert BybitClient(api_key="key", api_secret="secret", testnet=False).base_url == (
        "https://api.bybit.com"
    )


def test_bybit_get_private_signs_encoded_query(monkeypatch):
    client = BybitClient(api_key="key", api_secret="secret")
    monkeypatch.setattr(client, "_timestamp_ms", lambda: "1700000000000")
    captured = {}

    def fake_get(url, headers, timeout):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(payload={"retCode": 0, "result": {"ok": True}})

    monkeypatch.setattr("core.crypto_exchange_clients.requests.get", fake_get)

    data = client.get_private("/v5/execution/list", {"symbol": "BTC USDT", "category": "spot"})

    expected_query = "category=spot&symbol=BTC+USDT"
    expected_signature = hmac.new(
        b"secret",
        f"1700000000000key5000{expected_query}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert data == {"retCode": 0, "result": {"ok": True}}
    assert captured["url"] == "https://api.bybit.com/v5/execution/list?category=spot&symbol=BTC+USDT"
    assert captured["headers"]["X-BAPI-SIGN"] == expected_signature
    assert captured["timeout"] == 30


def test_okx_get_private_signs_encoded_request_path(monkeypatch):
    client = OKXClient(api_key="key", api_secret="secret", passphrase="pass")
    monkeypatch.setattr(client, "_timestamp_iso", lambda: "2026-01-01T00:00:00.000Z")
    captured = {}

    def fake_get(url, headers, timeout):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(payload={"code": "0", "data": [{"ok": True}]})

    monkeypatch.setattr("core.crypto_exchange_clients.requests.get", fake_get)

    data = client.get_private(
        "/api/v5/trade/fills-history", {"instId": "BTC USDT", "instType": "SPOT"}
    )

    request_path = "/api/v5/trade/fills-history?instId=BTC+USDT&instType=SPOT"
    expected_signature = base64.b64encode(
        hmac.new(
            b"secret",
            f"2026-01-01T00:00:00.000ZGET{request_path}".encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    assert data == {"code": "0", "data": [{"ok": True}]}
    assert captured["url"] == f"https://www.okx.com{request_path}"
    assert captured["headers"]["OK-ACCESS-SIGN"] == expected_signature
    assert captured["timeout"] == 30


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            FakeResponse(status_code=400, payload={"retCode": 10001, "retMsg": "bad request"}),
            "HTTP 400",
        ),
        (FakeResponse(status_code=502, json_error=ValueError("html"), text="<html>bad</html>"), "HTTP 502"),
        (FakeResponse(payload={"retCode": 10003, "retMsg": "invalid key"}), "invalid key"),
        (FakeResponse(payload={"result": {}}), "Malformed Bybit response"),
        (FakeResponse(payload=None, json_error=ValueError("bad json")), "Invalid JSON"),
    ],
)
def test_bybit_get_private_raises_api_error(monkeypatch, response, expected):
    client = BybitClient(api_key="key", api_secret="secret")
    monkeypatch.setattr(
        "core.crypto_exchange_clients.requests.get", lambda *args, **kwargs: response
    )

    with pytest.raises(CryptoExchangeAPIError, match=expected):
        client.get_private("/v5/execution/list", {"category": "spot"})


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            FakeResponse(status_code=401, payload={"code": "50113", "msg": "Invalid signature"}),
            "HTTP 401",
        ),
        (FakeResponse(status_code=403, json_error=ValueError("html"), text="<html>denied</html>"), "HTTP 403"),
        (FakeResponse(payload={"code": "51000", "msg": "Parameter error"}), "Parameter error"),
        (FakeResponse(payload={"data": []}), "Malformed OKX response"),
    ],
)
def test_okx_get_private_raises_api_error(monkeypatch, response, expected):
    client = OKXClient(api_key="key", api_secret="secret", passphrase="pass")
    monkeypatch.setattr(
        "core.crypto_exchange_clients.requests.get", lambda *args, **kwargs: response
    )

    with pytest.raises(CryptoExchangeAPIError, match=expected):
        client.get_private("/api/v5/trade/fills-history", {"instType": "SPOT"})


def test_bybit_transaction_log_paginates_next_page_cursor(monkeypatch):
    client = BybitClient(api_key="key", api_secret="secret")
    calls = []
    pages = [
        {"retCode": 0, "result": {"list": [{"id": "one"}], "nextPageCursor": "cursor-1"}},
        {"retCode": 0, "result": {"list": [{"id": "two"}], "nextPageCursor": ""}},
    ]

    def fake_get_private(path, params):
        calls.append((path, params))
        return pages.pop(0)

    monkeypatch.setattr(client, "get_private", fake_get_private)

    assert list(client.iter_transaction_log({"accountType": "UNIFIED"})) == [
        {"id": "one"},
        {"id": "two"},
    ]
    assert calls == [
        ("/v5/account/transaction-log", {"accountType": "UNIFIED", "limit": 50}),
        (
            "/v5/account/transaction-log",
            {"accountType": "UNIFIED", "limit": 50, "cursor": "cursor-1"},
        ),
    ]


def test_bybit_executions_paginates_next_page_cursor(monkeypatch):
    client = BybitClient(api_key="key", api_secret="secret")
    calls = []
    pages = [
        {"retCode": 0, "result": {"list": [{"execId": "one"}], "nextPageCursor": "cursor-1"}},
        {"retCode": 0, "result": {"list": [{"execId": "two"}], "nextPageCursor": None}},
    ]

    def fake_get_private(path, params):
        calls.append((path, params))
        return pages.pop(0)

    monkeypatch.setattr(client, "get_private", fake_get_private)

    assert list(client.iter_executions({"category": "spot"})) == [
        {"execId": "one"},
        {"execId": "two"},
    ]
    assert calls == [
        ("/v5/execution/list", {"category": "spot", "limit": 100}),
        ("/v5/execution/list", {"category": "spot", "limit": 100, "cursor": "cursor-1"}),
    ]


def test_okx_fills_history_paginates_after_cursor(monkeypatch):
    client = OKXClient(api_key="key", api_secret="secret", passphrase="pass")
    calls = []
    pages = [
        {"code": "0", "data": [{"billId": "bill-1", "tradeId": "trade-1"}]},
        {"code": "0", "data": [{"billId": "bill-2", "tradeId": "trade-2"}]},
        {"code": "0", "data": []},
    ]

    def fake_get_private(path, params):
        calls.append((path, params))
        return pages.pop(0)

    monkeypatch.setattr(client, "get_private", fake_get_private)

    assert list(client.iter_fills_history({"instType": "SPOT"})) == [
        {"billId": "bill-1", "tradeId": "trade-1"},
        {"billId": "bill-2", "tradeId": "trade-2"},
    ]
    assert calls == [
        ("/api/v5/trade/fills-history", {"instType": "SPOT"}),
        ("/api/v5/trade/fills-history", {"instType": "SPOT", "after": "bill-1"}),
        ("/api/v5/trade/fills-history", {"instType": "SPOT", "after": "bill-2"}),
    ]


@pytest.mark.parametrize(
    ("iterator_name", "page", "expected"),
    [
        ("iter_transaction_log", {"retCode": 0, "result": {}}, "Malformed Bybit transaction log"),
        ("iter_executions", {"retCode": 0, "result": {}}, "Malformed Bybit execution"),
    ],
)
def test_bybit_paginators_reject_malformed_success_payloads(
    monkeypatch, iterator_name, page, expected
):
    client = BybitClient(api_key="key", api_secret="secret")
    monkeypatch.setattr(client, "get_private", lambda path, params: page)

    with pytest.raises(CryptoExchangeAPIError, match=expected):
        list(getattr(client, iterator_name)({}))


def test_okx_fills_history_requires_bill_id_cursor(monkeypatch):
    client = OKXClient(api_key="key", api_secret="secret", passphrase="pass")
    monkeypatch.setattr(
        client,
        "get_private",
        lambda path, params: {"code": "0", "data": [{"tradeId": "trade-1"}]},
    )

    with pytest.raises(CryptoExchangeAPIError, match="Missing OKX billId cursor"):
        list(client.iter_fills_history({}))


def test_okx_fills_history_rejects_missing_data(monkeypatch):
    client = OKXClient(api_key="key", api_secret="secret", passphrase="pass")
    monkeypatch.setattr(client, "get_private", lambda path, params: {"code": "0"})

    with pytest.raises(CryptoExchangeAPIError, match="Malformed OKX fills response"):
        list(client.iter_fills_history({}))


async def _collect_transactions(api, account, date_from=None, date_to=None):
    return [
        event
        async for event in api.get_transactions(
            account,
            date_from=date_from,
            date_to=date_to,
        )
    ]


@pytest.mark.django_db
def test_get_broker_api_returns_bybit_and_okx_when_active_tokens_exist(user):
    bybit_broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    bybit_token = BybitApiToken.objects.create(
        user=user,
        broker=bybit_broker,
        api_key="bybit-key",
        testnet=True,
        is_active=True,
    )
    bybit_token.set_api_secret("bybit-secret", user)

    okx_broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    okx_token = OKXApiToken.objects.create(
        user=user,
        broker=okx_broker,
        api_key="okx-key",
        simulated_trading=True,
        is_active=True,
    )
    okx_token.set_credentials("okx-secret", "okx-pass", user)

    assert isinstance(async_to_sync(get_broker_api)(bybit_broker), BybitAPI)
    assert isinstance(async_to_sync(get_broker_api)(okx_broker), OKXAPI)


@pytest.mark.django_db(transaction=True)
def test_bybit_api_get_transactions_uses_active_token_and_normalizer(monkeypatch, user):
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")
    token = BybitApiToken.objects.create(
        user=user,
        broker=broker,
        api_key="bybit-key",
        testnet=True,
        is_active=True,
    )
    token.set_api_secret("bybit-secret", user)
    captured = {}

    class FakeBybitClient:
        def __init__(self, api_key, api_secret, testnet):
            captured["credentials"] = (api_key, api_secret, testnet)

        def iter_executions(self, params):
            captured["params"] = params
            yield {
                "execId": "exec-1",
                "orderId": "order-1",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "execQty": "0.1",
                "execPrice": "60000",
                "execFee": "3",
                "feeCurrency": "USDT",
                "execTime": "1767225600000",
            }

        def iter_option_executions(self, params):
            yield from []

        def iter_deposits(self, params):
            yield from []

        def iter_withdrawals(self, params):
            yield from []

        def iter_transaction_log(self, params):
            yield from []

        def iter_option_settlements(self, params):
            yield from []

    monkeypatch.setattr("services.broker_api.BybitClient", FakeBybitClient)

    api = BybitAPI()
    async_to_sync(api.connect)(user)
    events = async_to_sync(_collect_transactions)(
        api,
        account,
        date_from="2026-01-01",
        date_to="2026-01-02",
    )

    assert captured["credentials"] == ("bybit-key", "bybit-secret", True)
    assert captured["params"] == {
        "category": "spot",
        "startTime": 1767225600000,
        "endTime": 1767398399999,
    }
    assert len(events) == 1
    assert isinstance(events[0], CryptoExchangeEvent)
    assert events[0].provider == "bybit"
    assert events[0].legs[0]["quantity"] == Decimal("0.1")


@pytest.mark.django_db(transaction=True)
def test_okx_api_get_transactions_uses_active_token_and_normalizer(monkeypatch, user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Trading", native_id="okx-main")
    token = OKXApiToken.objects.create(
        user=user,
        broker=broker,
        api_key="okx-key",
        simulated_trading=True,
        is_active=True,
    )
    token.set_credentials("okx-secret", "okx-pass", user)
    captured = {}

    class FakeOKXClient:
        def __init__(self, api_key, api_secret, passphrase, simulated_trading):
            captured["credentials"] = (
                api_key,
                api_secret,
                passphrase,
                simulated_trading,
            )

        def iter_fills_history(self, params):
            captured["params"] = params
            yield {
                "tradeId": "trade-1",
                "ordId": "order-1",
                "instId": "BTC-USDT",
                "side": "sell",
                "fillSz": "0.2",
                "fillPx": "70000",
                "fee": "-0.0001",
                "feeCcy": "BTC",
                "fillTime": "1767225600000",
            }

        def iter_option_fills(self, params):
            yield from []

        def iter_deposits(self, params):
            yield from []

        def iter_withdrawals(self, params):
            yield from []

        def iter_earn_lending_history(self, params):
            yield from []

        def iter_option_settlements(self, params):
            yield from []

    monkeypatch.setattr("services.broker_api.OKXClient", FakeOKXClient)

    api = OKXAPI()
    async_to_sync(api.connect)(user)
    events = async_to_sync(_collect_transactions)(
        api,
        account,
        date_from="2026-01-01",
        date_to="2026-01-02",
    )

    assert captured["credentials"] == ("okx-key", "okx-secret", "okx-pass", True)
    assert captured["params"] == {
        "instType": "SPOT",
        "begin": 1767225600000,
        "end": 1767398399999,
    }
    assert len(events) == 1
    assert isinstance(events[0], CryptoExchangeEvent)
    assert events[0].provider == "okx"
    # Base-asset fee (BTC fee on a BTC-USDT sell) is CROSS-currency relative to
    # the USDT settlement, so under the real-price model (spec §5.3) the BTC fee
    # becomes a separate ``role="commission"`` leg. The base leg keeps the REAL
    # fill quantity (you sold 0.2) and the REAL fill price; the separate
    # commission leg carries the BTC fee quantity.
    base_leg = next(leg for leg in events[0].legs if leg.get("role") == "base")
    commission_leg = next(leg for leg in events[0].legs if leg.get("role") == "commission")
    assert base_leg["quantity"] == Decimal("-0.2")
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("-0.0001")


def test_bybit_iter_deposits_paginates_and_yields_rows(monkeypatch):
    client = BybitClient(api_key="k", api_secret="s")
    pages = [
        {"retCode": 0, "retMsg": "OK", "result": {"rows": [{"coin": "USDT", "txID": "d1"}], "nextPageCursor": "cursor-1"}},
        {"retCode": 0, "retMsg": "OK", "result": {"rows": [{"coin": "USDT", "txID": "d2"}], "nextPageCursor": ""}},
    ]
    calls = []

    def fake_get(path, params=None):
        calls.append((path, dict(params)))
        return pages.pop(0)

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_deposits({"limit": 50}))

    assert [r["txID"] for r in rows] == ["d1", "d2"]
    assert calls == [
        ("/v5/asset/deposit/query-record", {"limit": 50}),
        ("/v5/asset/deposit/query-record", {"limit": 50, "cursor": "cursor-1"}),
    ]


def test_bybit_iter_option_executions_passes_option_category(monkeypatch):
    client = BybitClient(api_key="k", api_secret="s")
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"retCode": 0, "retMsg": "OK", "result": {"list": [], "nextPageCursor": ""}}

    monkeypatch.setattr(client, "get_private", fake_get)
    list(client.iter_option_executions({"limit": 5}))

    assert captured["path"] == "/v5/execution/list"
    assert captured["params"]["category"] == "option"


def test_okx_iter_deposits_yields_data(monkeypatch):
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    page = {"code": "0", "msg": "", "data": [{"ccy": "BTC", "depId": "d1", "type": "4"}]}
    calls = {"n": 0}

    def fake_get(path, params=None):
        calls["n"] += 1
        # First call returns one row; subsequent calls return an empty page to
        # terminate the pagination loop (end of history reached).
        return page if calls["n"] == 1 else {"code": "0", "msg": "", "data": []}

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_deposits({}))

    assert [r["depId"] for r in rows] == ["d1"]


def test_okx_iter_deposits_requires_dep_id_cursor(monkeypatch):
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    monkeypatch.setattr(
        client,
        "get_private",
        lambda path, params=None: {"code": "0", "data": [{"ccy": "BTC"}]},
    )

    with pytest.raises(CryptoExchangeAPIError, match="Missing OKX depId cursor"):
        list(client.iter_deposits({}))


def test_okx_iter_withdrawals_yields_data(monkeypatch):
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    page = {"code": "0", "msg": "", "data": [{"ccy": "BTC", "wdId": "w1"}]}
    calls = {"n": 0}

    def fake_get(path, params=None):
        calls["n"] += 1
        # First call returns one row; subsequent calls return an empty page to
        # terminate the pagination loop (end of history reached).
        return page if calls["n"] == 1 else {"code": "0", "msg": "", "data": []}

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_withdrawals({}))

    assert [r["wdId"] for r in rows] == ["w1"]


def test_okx_iter_withdrawals_requires_wd_id_cursor(monkeypatch):
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    monkeypatch.setattr(
        client,
        "get_private",
        lambda path, params=None: {"code": "0", "data": [{"ccy": "BTC"}]},
    )

    with pytest.raises(CryptoExchangeAPIError, match="Missing OKX wdId cursor"):
        list(client.iter_withdrawals({}))


@pytest.mark.django_db(transaction=True)
async def test_bybit_api_get_transactions_merges_streams_and_tracks_failures(
    user, monkeypatch
):
    from common.models import Accounts, Brokers
    from users.models import BybitApiToken

    # This test is ``async def`` and sets up ORM fixtures directly. Allow
    # synchronous ORM calls from async code for the duration of this test only,
    # so setup queries don't need sync_to_async wrappers (scoped to avoid
    # leaking process-wide via a module-level env var).
    monkeypatch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")
    token = BybitApiToken.objects.create(
        user=user, broker=broker, api_key="k", is_active=True, testnet=False
    )
    token.set_api_secret("s", user)
    token.save()

    # Monkeypatch BybitClient iterators at the class level.
    from core.crypto_exchange_clients import BybitClient

    def fake_iter_executions(self, params):
        return iter([{
            "execId": "e1", "symbol": "BTCUSDT", "side": "Buy",
            "execQty": "0.1", "execPrice": "60000", "execTime": "300",
        }])

    def fake_iter_deposits(self, params):
        raise CryptoExchangeAPIError("Bybit HTTP 403: forbidden")

    def fake_iter_empty(self, params):
        return iter([])

    monkeypatch.setattr(BybitClient, "iter_executions", fake_iter_executions)
    monkeypatch.setattr(BybitClient, "iter_deposits", fake_iter_deposits)
    monkeypatch.setattr(BybitClient, "iter_withdrawals", fake_iter_empty)
    monkeypatch.setattr(BybitClient, "iter_option_executions", fake_iter_empty)
    monkeypatch.setattr(BybitClient, "iter_transaction_log", fake_iter_empty)
    monkeypatch.setattr(BybitClient, "iter_option_settlements", fake_iter_empty)

    api = BybitAPI()
    await api.connect(user)
    events = []
    async for event in api.get_transactions(account):
        events.append(event)

    # The trade event from iter_executions still yielded despite deposit failure.
    assert len(events) == 1
    assert events[0].provider_event_id == "e1"
    # The deposit endpoint failure was recorded, not raised.
    assert any("403" in msg for _, msg in api.partial_failures)


# --- Bug #4: ByBit 7-day window chunking -------------------------------------
#
# ByBit's /v5/execution/list and /v5/account/transaction-log reject windows
# over 7 days. _chunked_bybit_windows splits a too-wide window into
# consecutive <=7-day sub-windows (oldest first) so the merged stream stays
# time-sorted; deposits/withdrawals endpoints are unaffected.


_SEVEN_DAYS_MS = 7 * 86400 * 1000


def test_chunked_bybit_windows_short_span_yields_original_once():
    start = 1_700_000_000_000
    params = {"category": "spot", "startTime": start, "endTime": start + 5 * 86_400_000}

    windows = list(_chunked_bybit_windows(params))

    assert windows == [params]
    # Original params dict is yielded as-is (no mutation, no string coercion).
    assert windows[0]["startTime"] == start
    assert windows[0]["endTime"] == start + 5 * 86_400_000


def test_chunked_bybit_windows_eight_day_span_yields_two_chronological_windows():
    start = 1_700_000_000_000
    end = start + 8 * 86_400_000  # 8 days -> 7 + 1
    params = {"category": "spot", "startTime": start, "endTime": end}

    windows = list(_chunked_bybit_windows(params))

    assert len(windows) == 2
    # First window is a full 7 days; second is the remaining 1 day, clamped.
    assert windows[0] == {"category": "spot", "startTime": str(start), "endTime": str(start + _SEVEN_DAYS_MS)}
    assert windows[1] == {"category": "spot", "startTime": str(start + _SEVEN_DAYS_MS), "endTime": str(end)}
    # Chronological order, contiguous (next start == prev end).
    assert windows[0]["endTime"] == windows[1]["startTime"]
    # Last chunk clamped to the original end.
    assert windows[-1]["endTime"] == str(end)


def test_chunked_bybit_windows_twenty_one_day_span_yields_three_seven_day_windows():
    start = 1_700_000_000_000
    end = start + 21 * 86_400_000  # exactly 3 chunks of 7 days
    params = {"category": "spot", "startTime": start, "endTime": end}

    windows = list(_chunked_bybit_windows(params))

    assert len(windows) == 3
    for w in windows:
        assert int(w["endTime"]) - int(w["startTime"]) == _SEVEN_DAYS_MS
    # Contiguous and ordered.
    assert windows[0]["startTime"] == str(start)
    assert windows[0]["endTime"] == windows[1]["startTime"]
    assert windows[1]["endTime"] == windows[2]["startTime"]
    assert windows[2]["endTime"] == str(end)


def test_chunked_bybit_windows_missing_start_time_yields_params_once():
    params = {"category": "spot", "endTime": 1_700_000_000_000}

    windows = list(_chunked_bybit_windows(params))

    assert windows == [params]


def test_chunked_bybit_windows_handles_string_and_int_epoch_values():
    start = 1_700_000_000_000
    end = start + 10 * 86_400_000  # > 7 days

    # Strings (the form ByBit sends on the wire).
    str_windows = list(_chunked_bybit_windows({"startTime": str(start), "endTime": str(end)}))
    # Ints (the form _crypto_exchange_date_params produces).
    int_windows = list(_chunked_bybit_windows({"startTime": start, "endTime": end}))

    # Both produce the same chunk boundaries regardless of input type.
    assert [(w["startTime"], w["endTime"]) for w in str_windows] == (
        [(w["startTime"], w["endTime"]) for w in int_windows]
    )
    # Output bounds are always strings.
    for w in str_windows + int_windows:
        assert isinstance(w["startTime"], str)
        assert isinstance(w["endTime"], str)


def test_chunked_bybit_windows_unparseable_values_yields_params_once():
    params = {"startTime": "not-a-number", "endTime": 1_700_000_000_000}

    windows = list(_chunked_bybit_windows(params))

    assert windows == [params]


def test_iter_executions_with_wide_window_calls_get_private_once_per_chunk(monkeypatch):
    """A 30-day window must fan out into one get_private call per <=7-day chunk."""
    client = BybitClient(api_key="k", api_secret="s")
    calls = []

    def fake_get_private(path, params):
        calls.append((path, dict(params)))
        # Empty page terminates the pagination loop within each chunk.
        return {"retCode": 0, "result": {"list": [], "nextPageCursor": ""}}

    monkeypatch.setattr(client, "get_private", fake_get_private)

    # Use a recent start (within the 729-day history floor) so iter_executions'
    # max_history_days=729 clamp leaves the window intact and this test stays
    # focused on the 7-day chunking fan-out, not the clamp behavior.
    start = int(time.time() * 1000) - 100 * 86_400_000  # 100 days ago
    end = start + 30 * 86_400_000  # 30 days -> 5 chunks (7+7+7+7+2)
    rows = list(client.iter_executions({"category": "spot", "startTime": start, "endTime": end}))

    assert rows == []
    # 30 days splits into ceil(30/7) = 5 windows.
    assert len(calls) == 5
    assert all(path == "/v5/execution/list" for path, _ in calls)
    # Each call's window must be <= 7 days.
    for _, params in calls:
        span = int(params["endTime"]) - int(params["startTime"])
        assert span <= _SEVEN_DAYS_MS
    # Windows are chronological and contiguous.
    starts = [int(p["startTime"]) for _, p in calls]
    ends = [int(p["endTime"]) for _, p in calls]
    assert starts == sorted(starts)
    for i in range(len(calls) - 1):
        assert ends[i] == starts[i + 1]
    # First window starts at the original start; last window ends at the original end.
    assert starts[0] == start
    assert ends[-1] == end


# --- ByBit 30-day window chunking (deposits/withdrawals) ---------------------
#
# ByBit's /v5/asset/deposit/query-record and /v5/asset/withdraw/query-record
# reject windows over 30 days. _chunked_bybit_windows(params, max_days=30)
# splits a too-wide window into consecutive <=30-day sub-windows (oldest first).

_THIRTY_DAYS_MS = 30 * 86400 * 1000


def test_chunked_bybit_windows_thirty_day_span_yields_original_once():
    """A span of exactly max_days (30) must NOT chunk — it fits in one window."""
    start = 1_700_000_000_000
    end = start + 30 * 86_400_000  # exactly 30 days
    params = {"startTime": start, "endTime": end}

    windows = list(_chunked_bybit_windows(params, max_days=30))

    assert windows == [params]


def test_chunked_bybit_windows_thirty_day_max_yields_two_for_thirty_one_days():
    """A 31-day span (one day over the 30-day cap) chunks into 30 + 1."""
    start = 1_700_000_000_000
    end = start + 31 * 86_400_000  # 31 days -> 30 + 1
    params = {"startTime": start, "endTime": end}

    windows = list(_chunked_bybit_windows(params, max_days=30))

    assert len(windows) == 2
    assert windows[0] == {"startTime": str(start), "endTime": str(start + _THIRTY_DAYS_MS)}
    assert windows[1] == {"startTime": str(start + _THIRTY_DAYS_MS), "endTime": str(end)}
    # Contiguous and clamped to the original end.
    assert windows[0]["endTime"] == windows[1]["startTime"]
    assert windows[-1]["endTime"] == str(end)


def test_chunked_bybit_windows_thirty_day_max_yields_two_for_sixty_days():
    """A 60-day span chunks into exactly two 30-day windows."""
    start = 1_700_000_000_000
    end = start + 60 * 86_400_000  # 60 days -> 30 + 30
    params = {"startTime": start, "endTime": end}

    windows = list(_chunked_bybit_windows(params, max_days=30))

    assert len(windows) == 2
    for w in windows:
        assert int(w["endTime"]) - int(w["startTime"]) == _THIRTY_DAYS_MS
    # Contiguous, ordered, exact endpoints.
    assert windows[0]["startTime"] == str(start)
    assert windows[0]["endTime"] == windows[1]["startTime"]
    assert windows[1]["endTime"] == str(end)


def test_iter_deposits_with_wide_window_calls_get_private_once_per_chunk(monkeypatch):
    """A 60-day deposit window must fan out into one get_private call per <=30-day chunk."""
    client = BybitClient(api_key="k", api_secret="s")
    calls = []

    def fake_get(path, params):
        calls.append((path, dict(params)))
        # Empty page terminates the pagination loop within each chunk.
        return {"retCode": 0, "retMsg": "OK", "result": {"rows": [], "nextPageCursor": ""}}

    monkeypatch.setattr(client, "get_private", fake_get)

    start = 1_700_000_000_000
    end = start + 60 * 86_400_000  # 60 days -> 2 chunks (30 + 30)
    rows = list(client.iter_deposits({"startTime": start, "endTime": end}))

    assert rows == []
    # 60 days splits into ceil(60/30) = 2 windows.
    assert len(calls) == 2
    assert all(path == "/v5/asset/deposit/query-record" for path, _ in calls)
    # Each call's window must be <= 30 days.
    for _, params in calls:
        span = int(params["endTime"]) - int(params["startTime"])
        assert span <= _THIRTY_DAYS_MS
    # Windows are chronological and contiguous.
    starts = [int(p["startTime"]) for _, p in calls]
    ends = [int(p["endTime"]) for _, p in calls]
    assert starts == sorted(starts)
    for i in range(len(calls) - 1):
        assert ends[i] == starts[i + 1]
    # First window starts at the original start; last window ends at the original end.
    assert starts[0] == start
    assert ends[-1] == end


# --- ByBit 2-year history clamp (max_history_days) ---------------------------
#
# ByBit's /v5/execution/list and /v5/account/transaction-log reject queries
# older than ~730 days ("Can't query order earlier than 2 years"). Passing
# max_history_days=729 clamps startTime to no earlier than ~729 days ago so an
# over-long requested window silently truncates to available history instead of
# erroring. Deposits/withdrawals have NO such limit and must keep the default
# (None) so pre-2-year history is preserved.

_MS_PER_DAY = 86400 * 1000
_MS_PER_SEC = 1000


def test_chunked_bybit_windows_clamps_start_older_than_2_years():
    """A start >730 days ago is clamped to ~729 days ago (the safe floor)."""
    now_ms = int(time.time() * _MS_PER_SEC)
    floor_ms = now_ms - 729 * _MS_PER_DAY
    far_start = now_ms - 800 * _MS_PER_DAY  # well beyond 729-day floor
    end = now_ms + _MS_PER_DAY  # end is recent so the whole window isn't old
    params = {"category": "spot", "startTime": far_start, "endTime": end}

    windows = list(_chunked_bybit_windows(params, max_history_days=729))

    assert len(windows) >= 1
    clamped_start = int(windows[0]["startTime"])
    # Within a 60-second tolerance to absorb time.time() drift between the
    # helper's call and the test's expected-floor computation.
    assert abs(clamped_start - floor_ms) <= 60 * _MS_PER_SEC
    # End is preserved.
    assert windows[-1]["endTime"] == str(end)


def test_chunked_bybit_windows_no_clamp_when_start_within_history():
    """A start only 100 days ago must NOT be clamped (within the 729-day window)."""
    now_ms = int(time.time() * _MS_PER_SEC)
    start = now_ms - 100 * _MS_PER_DAY  # well within 729 days
    params = {"category": "spot", "startTime": start, "endTime": now_ms}

    windows = list(_chunked_bybit_windows(params, max_history_days=729))

    assert len(windows) >= 1
    assert int(windows[0]["startTime"]) == start  # unchanged


def test_chunked_bybit_windows_yields_nothing_when_whole_window_too_old():
    """If both start and end are older than 729 days, the window is empty."""
    now_ms = int(time.time() * _MS_PER_SEC)
    end = now_ms - 800 * _MS_PER_DAY  # end is itself beyond the floor
    start = end - 10 * _MS_PER_DAY
    params = {"category": "spot", "startTime": start, "endTime": end}

    windows = list(_chunked_bybit_windows(params, max_history_days=729))

    assert windows == []


def test_chunked_bybit_windows_no_clamp_when_max_history_days_none():
    """With max_history_days=None (deposits/withdrawals) very-old starts are preserved."""
    now_ms = int(time.time() * _MS_PER_SEC)
    far_start = now_ms - 1000 * _MS_PER_DAY  # well beyond 730 days
    end = far_start + 5 * _MS_PER_DAY  # short span, no chunking expected
    params = {"startTime": far_start, "endTime": end}

    windows = list(_chunked_bybit_windows(params))  # default max_history_days=None

    # Original params yielded verbatim — no clamping, no string coercion.
    assert windows == [params]


# --- Bug #5: OKX option settlements filter to type=3 -------------------------


def test_okx_iter_option_settlements_yields_only_type_3_rows(monkeypatch):
    """bills-archive returns settlement rows (type=3) AND premium rows (type=2).

    Premiums are already imported via iter_option_fills (fills-history), so
    only type=3 rows must be yielded here to avoid double-counting.
    """
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    calls = {"n": 0}

    def fake_get(path, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "code": "0",
                "data": [
                    # Settlement row — must be yielded.
                    {"billId": "settle-1", "type": "3", "subType": "172", "instId": "BTC-USD-260101-80000-C"},
                    # Premium trade row — must be filtered out (arrives via fills-history).
                    {"billId": "premium-1", "type": "2", "subType": "2", "execType": "T",
                     "ordId": "ord-1", "fillPx": "100", "fillIdxPx": "70000",
                     "instId": "BTC-USD-260101-80000-C"},
                ],
            }
        # Empty page terminates pagination.
        return {"code": "0", "data": []}

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_option_settlements({}))

    assert [r["billId"] for r in rows] == ["settle-1"]
    assert all(str(r["type"]) == "3" for r in rows)


# --- OKX deposit/withdrawal client-side date filter --------------------------
#
# OKX's /api/v5/asset/deposit-history and /api/v5/asset/withdrawal-history
# silently ignore the begin/end query params and return most-recent-N rows.
# iter_deposits / iter_withdrawals now filter client-side: yield only rows
# whose `ts` falls within [begin, end], and early-exit once a row's `ts`
# drops below `begin` (OKX returns rows newest-first).


def test_within_window_returns_true_when_no_bounds_supplied():
    """Missing begin/end means an open window — everything passes."""
    assert _within_window("1700000000000", None, None) is True
    assert _within_window(1700000000000, None, None) is True
    assert _within_window(None, None, None) is True


def test_within_window_accepts_string_and_int_inputs():
    """OKX echoes ts/begin/end as strings on the wire; helpers may pass ints."""
    begin = 1_700_000_000_000
    end = 1_700_000_010_000
    inside = 1_700_000_005_000

    # String row_ts with string bounds, string row_ts with int bounds,
    # int row_ts with string bounds, all-int inputs — all must agree.
    assert _within_window(str(inside), str(begin), str(end)) is True
    assert _within_window(str(inside), begin, end) is True
    assert _within_window(inside, str(begin), str(end)) is True
    assert _within_window(inside, begin, end) is True


def test_within_window_inclusive_bounds():
    """begin and end are inclusive — exact-boundary rows pass."""
    begin = 1_700_000_000_000
    end = 1_700_000_010_000

    assert _within_window(begin, begin, end) is True
    assert _within_window(end, begin, end) is True
    assert _within_window(begin - 1, begin, end) is False
    assert _within_window(end + 1, begin, end) is False


def test_within_window_only_begin_supplied():
    """end=None means open upper bound."""
    begin = 1_700_000_000_000
    assert _within_window(begin, begin, None) is True
    assert _within_window(begin + 10_000_000, begin, None) is True
    assert _within_window(begin - 1, begin, None) is False


def test_within_window_only_end_supplied():
    """begin=None means open lower bound."""
    end = 1_700_000_010_000
    assert _within_window(end, None, end) is True
    assert _within_window(end - 10_000_000, None, end) is True
    assert _within_window(end + 1, None, end) is False


def test_within_window_unparseable_row_ts_yields_true():
    """A row missing/unparseable ts cannot be filtered out conservatively."""
    assert _within_window("not-a-number", "1700000000000", "17000000001000") is True


def test_older_than_begin_returns_false_when_begin_missing():
    """No begin means no early-exit (we never want to drop data)."""
    assert _older_than_begin("1700000000000", None) is False
    assert _older_than_begin(None, "1700000000000") is False


def test_older_than_begin_accepts_string_and_int():
    begin = 1_700_000_000_000

    assert _older_than_begin(begin - 1, begin) is True
    assert _older_than_begin(str(begin - 1), str(begin)) is True
    assert _older_than_begin(begin, begin) is False  # boundary: NOT older
    assert _older_than_begin(begin + 1, begin) is False


def test_okx_iter_deposits_filters_rows_to_requested_window(monkeypatch):
    """Rows outside [begin, end] are skipped; rows inside are yielded."""
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    begin = 1_700_000_000_000
    end = 1_700_000_010_000
    # Newest-first: outside-above, inside, inside, outside-below. The
    # outside-below row triggers early-exit so pagination stops there.
    page = {
        "code": "0",
        "data": [
            {"depId": "above", "ts": str(end + 5_000)},  # after window -> skip
            {"depId": "in-1", "ts": str(end - 1_000)},  # inside -> yield
            {"depId": "in-2", "ts": str(begin + 1_000)},  # inside -> yield
            {"depId": "below", "ts": str(begin - 5_000)},  # before begin -> early-exit
        ],
    }

    def fake_get(path, params=None):
        return page

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_deposits({"begin": begin, "end": end}))

    assert [r["depId"] for r in rows] == ["in-1", "in-2"]


def test_okx_iter_deposits_early_exit_stops_pagination(monkeypatch):
    """A row older than `begin` terminates iteration entirely.

    OKX returns rows newest-first across pages, so once one row is too old
    every later row is too. We must NOT fetch the next page.
    """
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    begin = 1_700_000_000_000
    calls = {"n": 0}
    pages = [
        # Page 1: one row older than begin triggers early-exit.
        {"code": "0", "data": [{"depId": "too-old", "ts": str(begin - 1)}]},
        # Page 2 (must never be fetched): a row inside the window that would
        # be wrongly yielded if early-exit didn't fire.
        {"code": "0", "data": [{"depId": "would-be-yielded", "ts": str(begin + 1)}]},
    ]

    def fake_get(path, params=None):
        calls["n"] += 1
        return pages[min(calls["n"] - 1, len(pages) - 1)]

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_deposits({"begin": begin}))

    assert rows == []
    assert calls["n"] == 1  # pagination stopped after the first page


def test_okx_iter_deposits_without_window_yields_everything(monkeypatch):
    """Missing begin/end preserves the pre-filter behavior (yield all rows)."""
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    calls = {"n": 0}

    def fake_get(path, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"code": "0", "data": [{"depId": "d1", "ts": "1"}]}
        return {"code": "0", "data": []}

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_deposits({}))

    assert [r["depId"] for r in rows] == ["d1"]


def test_okx_iter_withdrawals_filters_rows_to_requested_window(monkeypatch):
    """Same client-side filter applies to withdrawals (wdId cursor)."""
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    begin = 1_700_000_000_000
    end = 1_700_000_010_000
    page = {
        "code": "0",
        "data": [
            {"wdId": "above", "ts": str(end + 5_000)},
            {"wdId": "in-1", "ts": str(end - 1_000)},
            {"wdId": "below", "ts": str(begin - 5_000)},  # early-exit
        ],
    }

    monkeypatch.setattr(client, "get_private", lambda path, params=None: page)
    rows = list(client.iter_withdrawals({"begin": begin, "end": end}))

    assert [r["wdId"] for r in rows] == ["in-1"]


def test_okx_iter_deposits_accepts_string_window_bounds(monkeypatch):
    """Bounds arrive from OKX as strings on the wire — int() tolerance."""
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    begin = 1_700_000_000_000
    end = 1_700_000_010_000
    page = {
        "code": "0",
        "data": [
            {"depId": "in", "ts": str(begin + 1_000)},
            {"depId": "below", "ts": str(begin - 1_000)},  # early-exit
        ],
    }

    monkeypatch.setattr(client, "get_private", lambda path, params=None: page)
    rows = list(client.iter_deposits({"begin": str(begin), "end": str(end)}))

    assert [r["depId"] for r in rows] == ["in"]


# --- partial_failures surfacing --------------------------------------------


def test_format_partial_failures_extracts_endpoint_and_error(user):
    """_format_partial_failures converts broker_api.partial_failures tuples
    into a JSON-serializable list of dicts for the frontend."""
    from transactions.views import _format_partial_failures

    class FakeBrokerAPI:
        def __init__(self, failures):
            self.partial_failures = failures

    broker_api = FakeBrokerAPI(
        [("spot_fills", "OKX HTTP 500: simulated 500"), ("deposits", "OKX HTTP 403")]
    )
    result = _format_partial_failures(broker_api)

    assert result == [
        {"endpoint": "spot_fills", "error": "OKX HTTP 500: simulated 500"},
        {"endpoint": "deposits", "error": "OKX HTTP 403"},
    ]


def test_format_partial_failures_handles_missing_attribute():
    """Brokers without partial_failures (e.g. Tinkoff) yield []."""
    from transactions.views import _format_partial_failures

    class TinkoffLikeAPI:
        pass

    assert _format_partial_failures(TinkoffLikeAPI()) == []
    assert _format_partial_failures(None) == []
