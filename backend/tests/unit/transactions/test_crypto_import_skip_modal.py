"""Tests for the crypto-broker import flow.

These cover the fix for the bug where OKX/ByBit imports wrongly popped up the
Tinkoff account-matching modal:

- ``services.broker_api.is_crypto_broker`` -- detects crypto brokers by their
  active ByBit/OKX tokens.
- ``services.broker_api.get_broker_api`` -- dispatch order: crypto tokens take
  precedence over a Tinkoff token so a mixed broker resolves to the crypto API.
- ``transactions.consumers.TransactionConsumer.start_api_import`` -- crypto
  brokers skip the modal and call ``process_account_matches`` directly, while
  Tinkoff brokers keep the original ``match_tinkoff_broker_account`` flow.

All money values use ``Decimal``. No real HTTP / SDK calls are made: token
secrets are written via the real encryption path but never decrypted here, and
the Tinkoff matcher / import paths are mocked on the consumer.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from channels.db import database_sync_to_async

from common.models import Accounts, Brokers
from services.broker_api import BybitAPI, OKXAPI, TinkoffAPI, get_broker_api, is_crypto_broker
from transactions.consumers import TransactionConsumer
from users.models import BybitApiToken, OKXApiToken, TinkoffApiToken

# These tests cross async/thread boundaries (database_sync_to_async) over
# SQLite, so they need transactional DB access to avoid "database table is
# locked" errors (same pattern as tests/unit/services/test_importer.py).
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_bybit_token(user, broker, *, is_active=True):
    """Create a Bybit token. save() auto-activates new rows, so force the
    requested state explicitly after the first save."""
    token = BybitApiToken(
        user=user,
        broker=broker,
        api_key="bybit-key",
        testnet=False,
        is_active=is_active,
    )
    token.set_api_secret("bybit-secret", user)
    if not is_active:
        token.is_active = False
        token.save(update_fields=["is_active"])
    return token


def _make_okx_token(user, broker, *, is_active=True):
    """Create an OKX token. save() auto-activates new rows, so force the
    requested state explicitly after the first save."""
    token = OKXApiToken(
        user=user,
        broker=broker,
        api_key="okx-key",
        simulated_trading=False,
        is_active=is_active,
    )
    token.set_credentials("okx-secret", "okx-passphrase", user)
    if not is_active:
        token.is_active = False
        token.save(update_fields=["is_active"])
    return token


def _make_tinkoff_token(user, broker, *, is_active=True):
    """Create a Tinkoff token (encrypted blob written directly to avoid the
    SDK validation path). Tinkoff save() auto-activates new rows."""
    token = TinkoffApiToken(
        user=user,
        broker=broker,
        token_type="read_only",
        sandbox_mode=False,
    )
    token.set_token("tinkoff-token", user)
    if not is_active:
        token.is_active = False
        token.save(update_fields=["is_active"])
    return token


# ---------------------------------------------------------------------------
# is_crypto_broker
# ---------------------------------------------------------------------------


class TestIsCryptoBroker:
    """is_crypto_broker should key off active ByBit/OKX tokens only."""

    async def test_true_for_active_okx_token(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="OKX", country="Crypto"
        )
        await database_sync_to_async(_make_okx_token)(user, broker, is_active=True)

        result = await is_crypto_broker(broker)
        assert result is True

    async def test_true_for_active_bybit_token(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Bybit", country="Crypto"
        )
        await database_sync_to_async(_make_bybit_token)(user, broker, is_active=True)

        result = await is_crypto_broker(broker)
        assert result is True

    async def test_false_for_tinkoff_only_broker(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Tinkoff", country="RU"
        )
        await database_sync_to_async(_make_tinkoff_token)(user, broker, is_active=True)

        result = await is_crypto_broker(broker)
        assert result is False

    async def test_false_for_broker_with_no_tokens(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Empty", country="US"
        )

        result = await is_crypto_broker(broker)
        assert result is False

    async def test_inactive_crypto_token_is_not_crypto(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="OKX", country="Crypto"
        )
        await database_sync_to_async(_make_okx_token)(user, broker, is_active=False)

        result = await is_crypto_broker(broker)
        assert result is False


# ---------------------------------------------------------------------------
# get_broker_api dispatch order
# ---------------------------------------------------------------------------


class TestGetBrokerApiDispatch:
    """get_broker_api must prefer crypto tokens over Tinkoff (dispatch-order fix)."""

    async def test_okx_token_wins_over_tinkoff_token(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Mixed", country="Crypto"
        )
        await database_sync_to_async(_make_tinkoff_token)(user, broker, is_active=True)
        await database_sync_to_async(_make_okx_token)(user, broker, is_active=True)

        api = await get_broker_api(broker)
        assert isinstance(api, OKXAPI)

    async def test_bybit_token_wins_over_tinkoff_token(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Mixed", country="Crypto"
        )
        await database_sync_to_async(_make_tinkoff_token)(user, broker, is_active=True)
        await database_sync_to_async(_make_bybit_token)(user, broker, is_active=True)

        api = await get_broker_api(broker)
        assert isinstance(api, BybitAPI)

    async def test_tinkoff_only_broker_returns_tinkoff_api(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Tinkoff", country="RU"
        )
        await database_sync_to_async(_make_tinkoff_token)(user, broker, is_active=True)

        api = await get_broker_api(broker)
        assert isinstance(api, TinkoffAPI)


# ---------------------------------------------------------------------------
# TransactionConsumer.start_api_import
# ---------------------------------------------------------------------------


def _make_consumer():
    """Build a TransactionConsumer without going through the Channels stack.

    __init__ creates a TransactionViewSet and asyncio primitives, which is all
    we need; the WebSocket ``send`` is overridden per-test.
    """
    return TransactionConsumer()


def _sent_messages(send_mock):
    """Decode the JSON ``text_data`` payloads passed to consumer.send.

    consumer.send_error / send_message call ``self.send(text_data=json.dumps(...))``.
    Returns the list of decoded dicts.
    """
    messages = []
    for call in send_mock.await_args_list:
        text = call.kwargs.get("text_data")
        if text is None and call.args:
            text = call.args[0]
        if text is None:
            continue
        try:
            messages.append(json.loads(text))
        except (TypeError, ValueError):
            continue
    return messages


class TestStartApiImportBranching:
    """Crypto brokers skip the modal; Tinkoff brokers keep the existing flow."""

    async def test_crypto_broker_skips_modal_and_processes_matches(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="OKX", country="Crypto"
        )
        await database_sync_to_async(_make_okx_token)(user, broker, is_active=True)
        account = await database_sync_to_async(Accounts.objects.create)(
            broker=broker, name="OKX account", native_id="okx-main"
        )

        consumer = _make_consumer()
        consumer.user = user
        consumer.send = AsyncMock()

        process_spy = AsyncMock(return_value=None)
        # Patch the bound method on this instance so we can assert the call
        # without running the real import machinery.
        consumer.process_account_matches = process_spy

        await consumer.start_api_import(broker_id=broker.id)

        # The modal must NOT be shown.
        messages = _sent_messages(consumer.send)
        assert all(m.get("type") != "account_matching_required" for m in messages)

        # process_account_matches must be called once with one self-mapped pair
        # preserving the existing native_id.
        process_spy.assert_awaited_once()
        call_args, call_kwargs = process_spy.call_args
        broker_id_arg, pairs_arg = call_args
        assert broker_id_arg == broker.id
        assert pairs_arg == [
            {"tinkoff_account_id": "okx-main", "db_account_id": account.id}
        ]

    async def test_crypto_broker_without_native_id_falls_back_to_id(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Bybit", country="Crypto"
        )
        await database_sync_to_async(_make_bybit_token)(user, broker, is_active=True)
        # Account with no native_id -> synthesized id should fall back to str(id).
        account = await database_sync_to_async(Accounts.objects.create)(
            broker=broker, name="Bybit account"
        )

        consumer = _make_consumer()
        consumer.user = user
        consumer.send = AsyncMock()
        process_spy = AsyncMock(return_value=None)
        consumer.process_account_matches = process_spy

        await consumer.start_api_import(broker_id=broker.id)

        process_spy.assert_awaited_once()
        _, pairs_arg = process_spy.call_args.args
        assert pairs_arg == [
            {"tinkoff_account_id": str(account.id), "db_account_id": account.id}
        ]

    async def test_crypto_broker_with_no_accounts_sends_error(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="OKX", country="Crypto"
        )
        await database_sync_to_async(_make_okx_token)(user, broker, is_active=True)
        # No Accounts rows for this broker.

        consumer = _make_consumer()
        consumer.user = user
        consumer.send = AsyncMock()
        process_spy = AsyncMock(return_value=None)
        consumer.process_account_matches = process_spy

        await consumer.start_api_import(broker_id=broker.id)

        # No import / processing attempted.
        process_spy.assert_not_awaited()

        # An error message was emitted and no modal was shown.
        messages = _sent_messages(consumer.send)
        assert any(m.get("type", "").endswith("error") for m in messages), messages
        assert all(m.get("type") != "account_matching_required" for m in messages)

    async def test_tinkoff_broker_runs_existing_match_flow(self, user):
        broker = await database_sync_to_async(Brokers.objects.create)(
            investor=user, name="Tinkoff", country="RU"
        )
        await database_sync_to_async(_make_tinkoff_token)(user, broker, is_active=True)
        await database_sync_to_async(Accounts.objects.create)(
            broker=broker, name="Tinkoff account"
        )

        consumer = _make_consumer()
        consumer.user = user
        consumer.send = AsyncMock()
        process_spy = AsyncMock(return_value=None)
        consumer.process_account_matches = process_spy

        fake_result = ({"a": 1}, [{"x": 2}], [{"y": 3}])
        with patch(
            "transactions.consumers.match_tinkoff_broker_account",
            new=AsyncMock(return_value=fake_result),
        ) as match_mock:
            await consumer.start_api_import(broker_id=broker.id)

        # Existing flow: matcher called, modal message sent, no direct import.
        match_mock.assert_awaited_once_with(broker, user)
        process_spy.assert_not_awaited()

        messages = _sent_messages(consumer.send)
        modal_payloads = [m for m in messages if m.get("type") == "account_matching_required"]
        assert len(modal_payloads) == 1
        assert modal_payloads[0]["data"]["broker_id"] == broker.id
