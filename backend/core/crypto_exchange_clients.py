"""Signed REST clients for crypto exchange imports."""

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode

import requests


class CryptoExchangeAPIError(Exception):
    """Raised when a crypto exchange API request fails."""


def _encoded_query(params: Dict[str, Any]) -> str:
    """Return a deterministic query string for signing and transport."""
    return urlencode(sorted(params.items()))


_BYBIT_MAX_WINDOW_MS = 7 * 86400 * 1000


def _chunked_bybit_windows(params):
    """Yield successive param dicts with startTime/endTime chunked to <=7 days.

    ByBit's /v5/execution/list and /v5/account/transaction-log reject windows
    over 7 days. If params has both startTime and endTime (ms epoch strings or
    ints) spanning more than 7 days, yield consecutive 7-day sub-windows from
    oldest to newest. If either bound is missing or the span is <= 7 days,
    yield the original params once.
    """
    raw_start = params.get("startTime")
    raw_end = params.get("endTime")
    if raw_start is None or raw_end is None:
        yield params
        return
    try:
        start = int(raw_start)
        end = int(raw_end)
    except (TypeError, ValueError):
        yield params
        return
    if end - start <= _BYBIT_MAX_WINDOW_MS:
        yield params
        return
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + _BYBIT_MAX_WINDOW_MS, end)
        yield {**params, "startTime": str(chunk_start), "endTime": str(chunk_end)}
        chunk_start = chunk_end


@dataclass
class BybitClient:
    api_key: str
    api_secret: str
    testnet: bool = False
    recv_window: str = "5000"

    @property
    def base_url(self) -> str:
        if self.testnet:
            return "https://api-testnet.bybit.com"
        return "https://api.bybit.com"

    def _timestamp_ms(self) -> str:
        return str(int(time.time() * 1000))

    def _signed_headers(self, timestamp: str, payload: str) -> Dict[str, str]:
        message = f"{timestamp}{self.api_key}{self.recv_window}{payload}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "X-BAPI-SIGN": signature,
        }

    def get_private(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        query = _encoded_query(params)
        timestamp = self._timestamp_ms()
        headers = self._signed_headers(timestamp, query)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CryptoExchangeAPIError(f"Bybit request failed: {exc}") from exc

        if response.status_code >= 400:
            try:
                data = response.json()
            except ValueError:
                data = getattr(response, "text", "")
            raise CryptoExchangeAPIError(f"Bybit HTTP {response.status_code}: {data}")

        try:
            data = response.json()
        except ValueError as exc:
            raise CryptoExchangeAPIError(f"Invalid JSON from Bybit: {exc}") from exc

        if "retCode" not in data:
            raise CryptoExchangeAPIError(f"Malformed Bybit response: {data}")
        if data.get("retCode") != 0:
            message = data.get("retMsg") or data
            raise CryptoExchangeAPIError(f"Bybit API error: {message}")

        return data

    def iter_transaction_log(
        self, params: Optional[Dict[str, Any]] = None
    ) -> Iterable[Dict[str, Any]]:
        params = params or {}
        for window_params in _chunked_bybit_windows(params):
            cursor = ""
            while True:
                page_params = {**window_params, "limit": 50}
                if cursor:
                    page_params["cursor"] = cursor

                data = self.get_private("/v5/account/transaction-log", page_params)
                result = data.get("result", {})
                rows = result.get("list")
                if rows is None:
                    rows = result.get("log")
                if rows is None:
                    raise CryptoExchangeAPIError(f"Malformed Bybit transaction log response: {data}")
                for row in rows:
                    yield row

                cursor = result.get("nextPageCursor")
                if not cursor:
                    break

    def iter_executions(self, params: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
        params = params or {}
        for window_params in _chunked_bybit_windows(params):
            cursor = ""
            while True:
                page_params = {**window_params, "limit": 100}
                if cursor:
                    page_params["cursor"] = cursor

                data = self.get_private("/v5/execution/list", page_params)
                result = data.get("result", {})
                rows = result.get("list")
                if rows is None:
                    raise CryptoExchangeAPIError(f"Malformed Bybit execution response: {data}")
                for row in rows:
                    yield row

                cursor = result.get("nextPageCursor")
                if not cursor:
                    break

    def iter_deposits(self, params=None):
        cursor = ""
        params = params or {}
        while True:
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor

            data = self.get_private("/v5/asset/deposit/query-record", page_params)
            result = data.get("result", {})
            rows = result.get("rows")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed Bybit deposit response: {data}")
            for row in rows:
                yield row

            cursor = result.get("nextPageCursor")
            if not cursor:
                break

    def iter_withdrawals(self, params=None):
        cursor = ""
        params = params or {}
        while True:
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor

            data = self.get_private("/v5/asset/withdraw/query-record", page_params)
            result = data.get("result", {})
            rows = result.get("rows")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed Bybit withdrawal response: {data}")
            for row in rows:
                yield row

            cursor = result.get("nextPageCursor")
            if not cursor:
                break

    def iter_option_executions(self, params=None):
        params = {**(params or {}), "category": "option"}
        yield from self.iter_executions(params)

    def iter_option_settlements(self, params=None):
        params = {**(params or {}), "type": "Settlement"}
        yield from self.iter_transaction_log(params)


@dataclass
class OKXClient:
    api_key: str
    api_secret: str
    passphrase: str
    simulated_trading: bool = False
    base_url: str = "https://www.okx.com"

    def _timestamp_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _signed_headers(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = "",
    ) -> Dict[str, str]:
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                prehash.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if self.simulated_trading:
            headers["x-simulated-trading"] = "1"
        return headers

    def get_private(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        query = _encoded_query(params)
        request_path = f"{path}?{query}" if query else path
        timestamp = self._timestamp_iso()
        headers = self._signed_headers(timestamp, "GET", request_path, "")
        url = f"{self.base_url}{request_path}"

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CryptoExchangeAPIError(f"OKX request failed: {exc}") from exc

        if response.status_code >= 400:
            try:
                data = response.json()
            except ValueError:
                data = getattr(response, "text", "")
            raise CryptoExchangeAPIError(f"OKX HTTP {response.status_code}: {data}")

        try:
            data = response.json()
        except ValueError as exc:
            raise CryptoExchangeAPIError(f"Invalid JSON from OKX: {exc}") from exc

        if "code" not in data:
            raise CryptoExchangeAPIError(f"Malformed OKX response: {data}")
        if data.get("code") != "0":
            message = data.get("msg") or data
            raise CryptoExchangeAPIError(f"OKX API error: {message}")

        return data

    def iter_fills_history(
        self, params: Optional[Dict[str, Any]] = None
    ) -> Iterable[Dict[str, Any]]:
        after = None
        params = params or {}
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after

            data = self.get_private("/api/v5/trade/fills-history", page_params)
            rows = data.get("data")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed OKX fills response: {data}")
            for row in rows:
                yield row

            if not rows:
                break
            after = rows[-1].get("billId")
            if not after:
                raise CryptoExchangeAPIError(f"Missing OKX billId cursor in fills response: {rows[-1]}")

    def iter_deposits(self, params=None):
        after = None
        params = params or {}
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after

            data = self.get_private("/api/v5/asset/deposit-history", page_params)
            rows = data.get("data")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed OKX deposit response: {data}")
            for row in rows:
                yield row

            if not rows:
                break
            after = rows[-1].get("depId")
            if not after:
                raise CryptoExchangeAPIError(
                    f"Missing OKX depId cursor in deposit response: {rows[-1]}"
                )

    def iter_withdrawals(self, params=None):
        after = None
        params = params or {}
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after

            data = self.get_private("/api/v5/asset/withdrawal-history", page_params)
            rows = data.get("data")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed OKX withdrawal response: {data}")
            for row in rows:
                yield row

            if not rows:
                break
            after = rows[-1].get("wdId")
            if not after:
                raise CryptoExchangeAPIError(
                    f"Missing OKX wdId cursor in withdrawal response: {rows[-1]}"
                )

    def iter_earn_lending_history(self, params=None):
        after = None
        params = params or {}
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after

            data = self.get_private("/api/v5/finance/savings/lending-history", page_params)
            rows = data.get("data")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed OKX lending response: {data}")
            for row in rows:
                yield row

            if not rows:
                break
            after = rows[-1].get("billId")
            if not after:
                raise CryptoExchangeAPIError(
                    f"Missing OKX billId cursor in lending response: {rows[-1]}"
                )

    def iter_option_fills(self, params=None):
        params = {**(params or {}), "instType": "OPTION"}
        yield from self.iter_fills_history(params)

    def iter_option_settlements(self, params=None):
        # The dedicated ``/api/v5/account/options-settlement-history`` endpoint
        # returns HTTP 404. The real source is ``/api/v5/account/bills-archive``
        # filtered to ``instType=OPTION``.
        after = None
        params = {"instType": "OPTION", **(params or {})}
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after

            data = self.get_private("/api/v5/account/bills-archive", page_params)
            rows = data.get("data")
            if rows is None:
                raise CryptoExchangeAPIError(f"Malformed OKX options-settlement response: {data}")
            for row in rows:
                # bills-archive returns BOTH settlement rows and option-premium
                # trade rows for instType=OPTION. Only ``type == "3"`` rows are
                # settlements; ``type == "2"`` rows are the premium trades that
                # ``iter_option_fills`` already fetches via /api/v5/trade/fills
                # -history, so yielding them here would double-count premiums.
                if str(row.get("type")) == "3":
                    yield row

            if not rows:
                break
            after = rows[-1].get("billId")
            if not after:
                raise CryptoExchangeAPIError(
                    f"Missing OKX billId cursor in options-settlement response: {rows[-1]}"
                )
