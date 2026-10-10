"""Consumer-level regressions for the account-based price-import command.

Drains ``PriceImportConsumer.import_prices`` (an async generator) directly
against seeded, committed data — no ASGI machinery and no network: seeded
securities deliberately carry no valid data source, so the resolved
identities surface in the yielded progress events (the per-security skip)
before any provider call. Account scoping, the exact selected-account
command and the explicit no-eligible-securities completion are pinned here.

``transaction=True`` is required: the consumer resolves securities on a
worker thread via ``database_sync_to_async``, and SQLite worker threads
cannot see the wrapped test transaction.
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal

import pytest
from channels.db import database_sync_to_async
from common.models import Accounts, Assets, Transactions
from constants import TRANSACTION_TYPE_BUY
from database.consumers import PriceImportConsumer

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
]

COMMAND = {
    "start_date": "2026-01-01",
    "end_date": "2026-01-31",
    "frequency": "weekly",
    "effective_current_date": "2026-01-31",
}


@database_sync_to_async
def _account(broker, name):
    return Accounts.objects.create(broker=broker, name=name)


@database_sync_to_async
def _held_security(user, name):
    """Create a security with no usable data source (skip branch, no network)."""
    security = Assets.objects.create(
        type="Stock",
        ISIN=f"US{name.replace(' ', '')[:12]}",
        name=name,
        currency="USD",
        exposure="Equity",
        data_source="NONE",
    )
    security.investors.add(user)
    return security


@database_sync_to_async
def _buy(user, account, security, quantity, when="2025-06-15"):
    return Transactions.objects.create(
        investor=user,
        account=account,
        security=security,
        currency="USD",
        type=TRANSACTION_TYPE_BUY,
        date=datetime.strptime(when, "%Y-%m-%d"),
        quantity=Decimal(quantity),
        price=Decimal("10.000000000"),
    )


@database_sync_to_async
def _sell(user, account, security, quantity, when="2025-09-15"):
    return Transactions.objects.create(
        investor=user,
        account=account,
        security=security,
        currency="USD",
        type="Sell",
        date=datetime.strptime(when, "%Y-%m-%d"),
        quantity=Decimal(quantity),
        price=Decimal("11.000000000"),
    )


async def _drain(consumer, data, user):
    events = []
    async for event in consumer.import_prices(data, user):
        events.append(json.loads(event))
    return events


def _resolved_names(events):
    return {
        event["security_name"]
        for event in events
        if "security_name" in event and event["status"] == "error"
    }


class TestAccountBasedPriceImportCommand:
    async def test_single_account_command_resolves_only_that_accounts_holding(
        self, user, broker
    ):
        account_a = await _account(broker, "Account A")
        account_b = await _account(broker, "Account B")
        held_in_a = await _held_security(user, "Held In A")
        held_in_b = await _held_security(user, "Held In B")
        await _buy(user, account_a, held_in_a, "10")
        await _buy(user, account_b, held_in_b, "5")

        events = await _drain(
            PriceImportConsumer(),
            {**COMMAND, "accounts": [account_a.id]},
            user,
        )

        assert _resolved_names(events) == {"Held In A"}
        assert all(
            event["status"] != "complete" or "no_eligible_securities" not in event
            for event in events
        )

    async def test_multi_account_command_resolves_the_union(self, user, broker):
        account_a = await _account(broker, "Account A")
        account_b = await _account(broker, "Account B")
        held_in_a = await _held_security(user, "Held In A")
        held_in_b = await _held_security(user, "Held In B")
        await _buy(user, account_a, held_in_a, "10")
        await _buy(user, account_b, held_in_b, "5")

        events = await _drain(
            PriceImportConsumer(),
            {**COMMAND, "accounts": [account_a.id, account_b.id]},
            user,
        )

        assert _resolved_names(events) == {"Held In A", "Held In B"}

    async def test_account_selection_without_holdings_completes_explicitly(
        self, user, broker
    ):
        empty_account = await _account(broker, "Empty Account")

        events = await _drain(
            PriceImportConsumer(),
            {**COMMAND, "accounts": [empty_account.id]},
            user,
        )

        assert len(events) == 1
        completion = events[0]
        assert completion["status"] == "complete"
        assert completion["no_eligible_securities"] is True
        assert completion["current"] == 0
        assert completion["total"] == 0
        assert "No eligible securities" in completion["message"]

    async def test_flat_position_is_not_eligible(self, user, broker):
        account = await _account(broker, "Flat Account")
        flat = await _held_security(user, "Fully Sold")
        await _buy(user, account, flat, "10")
        await _sell(user, account, flat, "-10")

        events = await _drain(
            PriceImportConsumer(),
            {**COMMAND, "accounts": [account.id]},
            user,
        )

        assert len(events) == 1
        assert events[0]["status"] == "complete"
        assert events[0]["no_eligible_securities"] is True
