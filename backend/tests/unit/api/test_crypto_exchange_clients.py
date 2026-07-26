import base64
import hashlib
import hmac
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
    assert events[0].legs[0]["quantity"] == Decimal("-0.2001")


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

    start = 1_700_000_000_000
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
