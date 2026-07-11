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
        cursor = ""
        params = params or {}
        while True:
            page_params = {**params, "limit": 50}
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
        cursor = ""
        params = params or {}
        while True:
            page_params = {**params, "limit": 100}
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
        params = params or {}
        data = self.get_private("/v5/asset/deposit/query-record", params)
        rows = data.get("result", {}).get("rows")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed Bybit deposit response: {data}")
        for row in rows:
            yield row

    def iter_withdrawals(self, params=None):
        params = params or {}
        data = self.get_private("/v5/asset/withdraw/query-record", params)
        rows = data.get("result", {}).get("rows")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed Bybit withdrawal response: {data}")
        for row in rows:
            yield row

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

    def iter_asset_deposits_withdrawals(self, params=None):
        params = params or {}
        data = self.get_private("/api/v5/asset/deposit-withdraw", params)
        rows = data.get("data")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed OKX deposit-withdraw response: {data}")
        for row in rows:
            yield row

    def iter_earn_lending_history(self, params=None):
        params = params or {}
        data = self.get_private("/api/v5/finance/savings/lending-history", params)
        rows = data.get("data")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed OKX lending response: {data}")
        for row in rows:
            yield row

    def iter_option_fills(self, params=None):
        params = {**(params or {}), "instType": "OPTION"}
        yield from self.iter_fills_history(params)

    def iter_option_settlements(self, params=None):
        params = params or {}
        data = self.get_private("/api/v5/account/options-settlement-history", params)
        rows = data.get("data")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed OKX options-settlement response: {data}")
        for row in rows:
            yield row
