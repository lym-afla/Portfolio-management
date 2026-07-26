import base64
import hashlib
import hmac
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync

from common.models import Accounts, Brokers
from services.broker_api import BybitAPI, OKXAPI, get_broker_api
from services.crypto_exchange import CryptoExchangeEvent
from core.crypto_exchange_clients import BybitClient, CryptoExchangeAPIError, OKXClient
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
