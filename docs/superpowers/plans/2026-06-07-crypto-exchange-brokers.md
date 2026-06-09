# Crypto Exchange Brokers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Bybit and OKX broker API imports for crypto assets, stablecoins, earn/funding rewards, transfers, fees, and BTC options.

**Architecture:** Keep the existing transaction-led portfolio architecture. Model every coin, token, stablecoin, and option as an `Assets` row; provider clients normalize raw Bybit/OKX payloads into internal events; the importer persists canonical multi-leg transactions with provider IDs for deduplication.

**Tech Stack:** Django, DRF, Django migrations, Decimal financial math, Vue 3/Vuetify, Jest, pytest, Context7-verified Bybit V5 and OKX V5 REST APIs.

---

## Scope Notes

This plan touches protected model and calculation code. Implement on a PR with `needs-approval`; include regression tests with fixed `Decimal` expectations before requesting review.

The current branch is `codex/add-crypto-exchange-brokers`. There is an unrelated existing worktree deletion of `.codex/config.toml`; do not stage or revert it.

## File Structure

Create:

- `backend/core/crypto_exchange_clients.py`: signed REST helpers and Bybit/OKX private client methods.
- `backend/core/crypto_exchange_import.py`: normalized event dataclasses, asset resolution, and event-to-transaction mapping.
- `backend/tests/unit/api/test_crypto_exchange_clients.py`: signing, URL, pagination unit tests.
- `backend/tests/unit/imports/test_crypto_exchange_import.py`: event normalization and mapping tests.
- `backend/tests/unit/calculations/test_crypto_rewards.py`: reward/capital-distribution/cost-basis regression tests.
- `backend/tests/integration/api/test_crypto_token_api.py`: token API and broker filtering tests.
- `backend/common/migrations/0089_crypto_exchange_import_metadata.py`: crypto choices and transaction import metadata.
- `backend/users/migrations/0021_bybit_okx_api_tokens.py`: encrypted Bybit/OKX credential models.
- `portfolio-frontend/tests/unit/components/BrokerTokenManager.crypto.spec.js`: frontend token workflow tests.

Modify:

- `backend/constants.py`: crypto transaction constants, crypto asset choice, broker provider names.
- `backend/common/models.py`: `Transactions`/`FXTransaction` import metadata; crypto-aware cost basis and capital distribution logic.
- `backend/users/models.py`: Bybit/OKX token models.
- `backend/users/serializers.py`: Bybit/OKX token serializers.
- `backend/users/views.py`: Bybit/OKX token viewsets, aggregate token listing, revoke handling.
- `backend/users/urls.py`: token routes.
- `backend/database/views.py`: brokers with active token filtering.
- `backend/core/broker_api_utils.py`: `BybitAPI` and `OKXAPI` adapters behind `get_broker_api`.
- `backend/core/import_utils.py`: provider-ID duplicate detection.
- `backend/transactions/views.py`: save normalized crypto multi-leg transactions.
- `backend/core/portfolio_utils.py`: invested/cash-out handling for external crypto transfers.
- `backend/core/securities_utils.py`: crypto reward totals for Security detail.
- `backend/database/serializers.py`: transaction descriptions and safe import metadata where needed.
- `portfolio-frontend/src/components/BrokerTokenManager.vue`: Bybit/OKX credential UX.
- `portfolio-frontend/src/services/api.js`: Bybit/OKX token API helpers.
- `portfolio-frontend/src/views/database/SecurityDetailPage.vue`: native/fiat reward yield display.
- `portfolio-frontend/src/components/transactions/TransactionDescription.vue`: crypto event descriptions.
- `portfolio-frontend/src/components/dialogs/TransactionImportDialog.vue`: direct import support for active Bybit/OKX tokens if provider labels are shown.

---

### Task 1: Domain Constants And Import Metadata

**Files:**

- Modify: `backend/constants.py`
- Modify: `backend/common/models.py`
- Create: `backend/common/migrations/0089_crypto_exchange_import_metadata.py`
- Test: `backend/tests/integration/database/test_constraints.py`

- [ ] **Step 1: Add failing model metadata tests**

Append these tests to `backend/tests/integration/database/test_constraints.py`:

```python
from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
)


@pytest.mark.django_db
def test_crypto_asset_type_and_provider_metadata_are_persisted(user):
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")
    btc = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:BTC",
        name="Bitcoin",
        ticker="BTC",
        currency="USD",
        exposure="Commodity",
        data_source="",
    )
    btc.investors.add(user)

    tx = Transactions.objects.create(
        investor=user,
        account=account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.010000000"),
        price=Decimal("50000.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
        import_event_id="reward-1",
        import_group_id="reward-1",
        import_event_type="reward",
    )

    assert tx.security.type == ASSET_TYPE_CRYPTO
    assert tx.import_provider == "bybit"
    assert tx.import_event_id == "reward-1"
    assert tx.import_group_id == "reward-1"
    assert tx.type == TRANSACTION_TYPE_CRYPTO_REWARD


@pytest.mark.django_db
def test_provider_event_id_is_unique_per_provider_account_and_transaction_model(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Trading", native_id="okx-main")
    usdt = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:USDT",
        name="Tether USD",
        ticker="USDT",
        currency="USD",
        exposure="FX",
    )
    usdt.investors.add(user)

    Transactions.objects.create(
        investor=user,
        account=account,
        security=usdt,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("100.000000000"),
        price=Decimal("1.000000000"),
        import_provider="okx",
        import_account_id="okx-main",
        import_event_id="fill-1:in",
        import_group_id="fill-1",
        import_event_type="trade",
    )

    with pytest.raises(Exception):
        Transactions.objects.create(
            investor=user,
            account=account,
            security=usdt,
            currency="USD",
            type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
            date=datetime(2026, 1, 1, 12, 0),
            quantity=Decimal("100.000000000"),
            price=Decimal("1.000000000"),
            import_provider="okx",
            import_account_id="okx-main",
            import_event_id="fill-1:in",
            import_group_id="fill-1",
            import_event_type="trade",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/database/test_constraints.py::test_crypto_asset_type_and_provider_metadata_are_persisted tests/integration/database/test_constraints.py::test_provider_event_id_is_unique_per_provider_account_and_transaction_model -q
```

Expected: FAIL because crypto constants and import metadata fields do not exist.

- [ ] **Step 3: Add constants**

In `backend/constants.py`, add constants near the existing asset and transaction constants:

```python
ASSET_TYPE_CRYPTO = "Crypto"

TRANSACTION_TYPE_CRYPTO_REWARD = "Crypto reward"
TRANSACTION_TYPE_CRYPTO_TRANSFER_IN = "Crypto transfer in"
TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT = "Crypto transfer out"
TRANSACTION_TYPE_CRYPTO_TRADE_IN = "Crypto trade in"
TRANSACTION_TYPE_CRYPTO_TRADE_OUT = "Crypto trade out"
TRANSACTION_TYPE_OPTION_SETTLEMENT = "Option settlement"

BROKER_PROVIDER_BYBIT = "bybit"
BROKER_PROVIDER_OKX = "okx"
BROKER_PROVIDER_TBANK = "tbank"
```

Extend `TRANSACTION_TYPE_CHOICES`:

```python
    (TRANSACTION_TYPE_CRYPTO_REWARD, "Crypto reward"),
    (TRANSACTION_TYPE_CRYPTO_TRANSFER_IN, "Crypto transfer in"),
    (TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT, "Crypto transfer out"),
    (TRANSACTION_TYPE_CRYPTO_TRADE_IN, "Crypto trade in"),
    (TRANSACTION_TYPE_CRYPTO_TRADE_OUT, "Crypto trade out"),
    (TRANSACTION_TYPE_OPTION_SETTLEMENT, "Option settlement"),
```

Extend `ASSET_TYPE_CHOICES`:

```python
    (ASSET_TYPE_CRYPTO, "Crypto"),
```

- [ ] **Step 4: Add import metadata fields**

In `backend/common/models.py`, add these nullable fields to `Transactions` after `merger`:

```python
    import_provider = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    import_account_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    import_event_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_group_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_event_type = models.CharField(max_length=50, null=True, blank=True)
```

Add the same fields to `FXTransaction` after `comment` so provider dedupe works for any future exchange FX-like rows:

```python
    import_provider = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    import_account_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    import_event_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_group_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_event_type = models.CharField(max_length=50, null=True, blank=True)
```

Add constraints inside `Transactions.Meta`. If `Transactions` has no `Meta`, create one below the field declarations:

```python
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["investor", "account", "import_provider", "import_account_id", "import_event_id"],
                condition=models.Q(import_event_id__isnull=False),
                name="unique_transaction_provider_event",
            )
        ]
```

Add this `Meta` to `FXTransaction`:

```python
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["investor", "account", "import_provider", "import_account_id", "import_event_id"],
                condition=models.Q(import_event_id__isnull=False),
                name="unique_fx_transaction_provider_event",
            )
        ]
```

- [ ] **Step 5: Create migration**

Run:

```powershell
Set-Location backend
poetry run python manage.py makemigrations common --name crypto_exchange_import_metadata
```

Expected: creates `backend/common/migrations/0089_crypto_exchange_import_metadata.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/database/test_constraints.py::test_crypto_asset_type_and_provider_metadata_are_persisted tests/integration/database/test_constraints.py::test_provider_event_id_is_unique_per_provider_account_and_transaction_model -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/constants.py backend/common/models.py backend/common/migrations/0089_crypto_exchange_import_metadata.py backend/tests/integration/database/test_constraints.py
git commit -m "feat: add crypto import transaction metadata" -m "- What changed: Added crypto transaction constants and provider import metadata." -m "- Why: Exchange imports need asset-led transaction types and durable provider IDs for dedupe." -m "- Numerical impact / example: No calculation behavior changes yet." -m "- Tests added: Crypto asset metadata persistence and provider event uniqueness." -m "- Reviewer(s): needs approval"
```

---

### Task 2: Crypto Rewards And Cost-Basis Semantics

**Files:**

- Modify: `backend/common/models.py`
- Modify: `backend/core/portfolio_utils.py`
- Test: `backend/tests/unit/calculations/test_crypto_rewards.py`

- [ ] **Step 1: Write failing reward calculation tests**

Create `backend/tests/unit/calculations/test_crypto_rewards.py`:

```python
from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Prices, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
)


@pytest.fixture
def crypto_account(user):
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")


@pytest.fixture
def btc(user):
    asset = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:BTC",
        name="Bitcoin",
        ticker="BTC",
        currency="USD",
        exposure="Commodity",
    )
    asset.investors.add(user)
    return asset


@pytest.mark.django_db
def test_crypto_reward_increases_position_and_capital_distribution(user, crypto_account, btc):
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 10, 12, 0),
        quantity=Decimal("0.010000000"),
        price=Decimal("50000.000000000"),
    )

    assert btc.position(datetime(2026, 1, 11).date(), user, [crypto_account.id]) == Decimal("0.010000000")
    assert btc.get_capital_distribution(datetime(2026, 1, 11).date(), user, "USD", [crypto_account.id]) == Decimal("500.00")
    assert crypto_account.balance(datetime(2026, 1, 11).date()) == {}


@pytest.mark.django_db
def test_crypto_reward_does_not_distort_paid_entry_price(user, crypto_account, btc):
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )

    assert btc.calculate_buy_in_price(datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]) == Decimal("100.000000")
    assert btc.get_economic_basis(datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]) == Decimal("120.00")


@pytest.mark.django_db
def test_crypto_trade_out_realizes_gain_but_transfer_out_is_neutral(user, crypto_account, btc):
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.250000000"),
        price=Decimal("150.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 3, 12, 0),
        quantity=Decimal("-0.250000000"),
        price=Decimal("200.000000000"),
    )

    realized = btc.realized_gain_loss(datetime(2026, 1, 4).date(), user, "USD", [crypto_account.id])
    assert realized["all_time"]["total"] == Decimal("25.000000000000000000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/calculations/test_crypto_rewards.py -q
```

Expected: FAIL because reward distribution, crypto trade types, and `get_economic_basis` are not implemented.

- [ ] **Step 3: Add transaction classification helpers**

In `backend/common/models.py`, import the crypto constants and add methods on `Transactions`:

```python
    def is_position_increase(self):
        """Return True when the transaction increases asset quantity."""
        return self.quantity is not None and self.quantity > 0

    def is_paid_entry_transaction(self):
        """Return True when this transaction should affect paid entry price."""
        return self.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CRYPTO_TRADE_IN]

    def is_reward_transaction(self):
        """Return True when this transaction is crypto income."""
        return self.type == TRANSACTION_TYPE_CRYPTO_REWARD

    def is_disposal_transaction(self):
        """Return True when this transaction should realize gain/loss."""
        return self.type in [TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]

    def is_neutral_transfer_transaction(self):
        """Return True when quantity movement is principal transfer only."""
        return self.type in [
            TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
            TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        ]

    def reward_value(self):
        """Return event-date reward value without creating account cash."""
        if not self.is_reward_transaction() or self.quantity is None or self.price is None:
            return Decimal("0")
        return abs(self.quantity) * self.price
```

- [ ] **Step 4: Update capital distribution**

In `Assets.get_capital_distribution`, include crypto rewards:

```python
        crypto_reward_transactions = self.transactions.filter(
            type=TRANSACTION_TYPE_CRYPTO_REWARD,
            date__date__lte=query_date,
            investor=investor,
        )
        if account_ids is not None:
            crypto_reward_transactions = crypto_reward_transactions.filter(account_id__in=account_ids)
        if start_date is not None:
            crypto_reward_transactions = crypto_reward_transactions.filter(date__date__gte=query_start_date)

        for transaction in crypto_reward_transactions:
            reward_value = transaction.reward_value()
            if currency is not None and transaction.currency != currency:
                fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)["FX"]
                if fx_rate:
                    reward_value *= Decimal(fx_rate)
            total_distributions += reward_value
```

- [ ] **Step 5: Add economic basis helper**

Add this method to `Assets`:

```python
    def get_economic_basis(self, date_as_of, investor, currency=None, account_ids=None, start_date=None):
        """Return paid basis plus reward event value for current crypto lots."""
        query = self.transactions.filter(
            quantity__isnull=False,
            investor=investor,
            date__date__lte=date_as_of,
        ).order_by("date", "id")
        if account_ids is not None:
            query = query.filter(account_id__in=account_ids)
        if start_date is not None:
            query = query.filter(date__gte=start_date)

        basis = Decimal("0")
        position = Decimal("0")
        average_basis = Decimal("0")

        for transaction in query:
            tx_currency = transaction.currency
            fx_rate = Decimal("1")
            if currency is not None and tx_currency != currency:
                fx_rate = FX.get_rate(tx_currency, currency, transaction.date)["FX"] or Decimal("0")

            if transaction.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CRYPTO_TRADE_IN]:
                added_basis = transaction.quantity * transaction.price * fx_rate
                basis += added_basis
                position += transaction.quantity
                average_basis = basis / position if position else Decimal("0")
            elif transaction.type == TRANSACTION_TYPE_CRYPTO_REWARD:
                added_basis = transaction.reward_value() * fx_rate
                basis += added_basis
                position += transaction.quantity
                average_basis = basis / position if position else Decimal("0")
            elif transaction.type in [TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]:
                disposed_quantity = abs(transaction.quantity)
                basis -= average_basis * disposed_quantity
                position += transaction.quantity
                if position <= 0:
                    basis = Decimal("0")
                    average_basis = Decimal("0")
            elif transaction.type in [TRANSACTION_TYPE_CRYPTO_TRANSFER_IN, TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT]:
                position += transaction.quantity

        return round(basis, 2)
```

- [ ] **Step 6: Update buy-in and realized gain logic**

In `Assets.calculate_buy_in_price`, skip reward and transfer rows for paid entry price and treat `Crypto trade in` as buy-equivalent:

```python
        transactions = [
            transaction
            for transaction in transactions
            if transaction.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]
        ]
```

In `Assets.realized_gain_loss`, update disposal detection:

```python
                is_position_reducing = (
                    position > 0 and transaction.type in [TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]
                ) or (
                    position < 0 and transaction.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CRYPTO_TRADE_IN]
                )
```

Update closing quantity branches to use the same buy-equivalent and sell-equivalent lists. Skip neutral transfers for realized gain/loss calculation after updating `position`:

```python
                if transaction.type in [TRANSACTION_TYPE_CRYPTO_TRANSFER_IN, TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT]:
                    position += transaction.quantity
                    continue
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/calculations/test_crypto_rewards.py -q
```

Expected: PASS.

- [ ] **Step 8: Run existing related calculation tests**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/calculations/test_buy_in_price.py tests/unit/calculations/test_gain_loss.py tests/unit/calculations/test_nav_calculations.py tests/unit/calculations/test_bond_aci.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add backend/common/models.py backend/core/portfolio_utils.py backend/tests/unit/calculations/test_crypto_rewards.py
git commit -m "feat: add crypto reward calculation semantics" -m "- What changed: Added crypto reward distribution and crypto trade cost-basis handling." -m "- Why: Earn/funding rewards must increase native position and appear in capital distribution without creating fiat cash." -m "- Numerical impact / example: 0.01 BTC reward at 50000 USD contributes 500.00 USD capital distribution." -m "- Tests added: Crypto reward position, distribution, paid entry, economic basis, and disposal tests." -m "- Reviewer(s): needs approval"
```

---

### Task 3: Bybit And OKX Credential Storage APIs

**Files:**

- Modify: `backend/users/models.py`
- Modify: `backend/users/serializers.py`
- Modify: `backend/users/views.py`
- Modify: `backend/users/urls.py`
- Create: `backend/users/migrations/0021_bybit_okx_api_tokens.py`
- Modify: `backend/database/views.py`
- Test: `backend/tests/integration/api/test_crypto_token_api.py`

- [ ] **Step 1: Write failing token API tests**

Create `backend/tests/integration/api/test_crypto_token_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from common.models import Brokers
from users.models import BybitApiToken, OKXApiToken


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_bybit_token_save_encrypts_secret_and_lists_safe_metadata(user, api_client):
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")

    response = api_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": broker.id,
            "api_key": "key-1",
            "api_secret": "secret-1",
            "testnet": True,
        },
        format="json",
    )

    assert response.status_code == 201
    token = BybitApiToken.objects.get(user=user, broker=broker)
    assert token.get_api_secret(user) == "secret-1"
    assert "api_secret" not in response.data
    assert response.data["api_key_preview"] == "key-1"
    assert response.data["testnet"] is True


@pytest.mark.django_db
def test_okx_token_save_encrypts_secret_and_passphrase(user, api_client):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")

    response = api_client.post(
        "/users/api/okx-tokens/",
        {
            "broker": broker.id,
            "api_key": "okx-key",
            "api_secret": "okx-secret",
            "passphrase": "okx-pass",
            "simulated_trading": False,
        },
        format="json",
    )

    assert response.status_code == 201
    token = OKXApiToken.objects.get(user=user, broker=broker)
    assert token.get_api_secret(user) == "okx-secret"
    assert token.get_passphrase(user) == "okx-pass"
    assert "api_secret" not in response.data
    assert "passphrase" not in response.data


@pytest.mark.django_db
def test_brokers_with_active_tokens_includes_bybit_and_okx(user, api_client):
    bybit = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    okx = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    bybit_token = BybitApiToken(user=user, broker=bybit, api_key="a", testnet=False, is_active=True)
    bybit_token.set_api_secret("b", user)
    okx_token = OKXApiToken(user=user, broker=okx, api_key="c", simulated_trading=False, is_active=True)
    okx_token.set_credentials("d", "e", user)

    response = api_client.get("/database/api/brokers/", {"with_active_tokens": "1"})

    assert response.status_code == 200
    names = {item["name"] for item in response.data}
    assert {"Bybit", "OKX"}.issubset(names)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/api/test_crypto_token_api.py -q
```

Expected: FAIL because Bybit/OKX token models and routes do not exist.

- [ ] **Step 3: Add token models**

In `backend/users/models.py`, add:

```python
class BybitApiToken(BaseApiToken):
    """Bybit-specific API credentials."""

    broker = models.ForeignKey("common.Brokers", on_delete=models.CASCADE, related_name="bybit_tokens")
    api_key = models.CharField(max_length=120)
    testnet = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Bybit API Token"
        verbose_name_plural = "Bybit API Tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker", "testnet"],
                condition=models.Q(is_active=True),
                name="unique_active_bybit_token",
            )
        ]

    def set_api_secret(self, api_secret, user):
        self.set_token(api_secret, user)

    def get_api_secret(self, user):
        return self.get_token(user)

    def __str__(self):
        return f"Bybit token ({self.user.username} - {self.broker.name})"


class OKXApiToken(BaseApiToken):
    """OKX-specific API credentials."""

    broker = models.ForeignKey("common.Brokers", on_delete=models.CASCADE, related_name="okx_tokens")
    api_key = models.CharField(max_length=120)
    encrypted_passphrase = models.BinaryField()
    simulated_trading = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = "OKX API Token"
        verbose_name_plural = "OKX API Tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker", "simulated_trading"],
                condition=models.Q(is_active=True),
                name="unique_active_okx_token",
            )
        ]

    def set_credentials(self, api_secret, passphrase, user):
        self.set_token(api_secret, user)
        key = get_encryption_key(user)
        f = Fernet(key)
        self.encrypted_passphrase = f.encrypt(passphrase.encode())
        self.save()

    def get_api_secret(self, user):
        return self.get_token(user)

    def get_passphrase(self, user):
        key = get_encryption_key(user)
        f = Fernet(key)
        return f.decrypt(self.encrypted_passphrase).decode()

    def __str__(self):
        return f"OKX token ({self.user.username} - {self.broker.name})"
```

- [ ] **Step 4: Add serializers, views, and routes**

In `backend/users/serializers.py`, add serializers that write secrets and return safe fields:

```python
class BybitApiTokenSerializer(serializers.ModelSerializer):
    api_secret = serializers.CharField(write_only=True)
    api_key_preview = serializers.CharField(source="api_key", read_only=True)

    class Meta:
        model = BybitApiToken
        fields = ["id", "broker", "api_key", "api_key_preview", "api_secret", "testnet", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "api_key_preview", "is_active", "created_at", "updated_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        secret = validated_data.pop("api_secret")
        token = BybitApiToken(user=user, is_active=True, **validated_data)
        token.set_api_secret(secret, user)
        return token


class OKXApiTokenSerializer(serializers.ModelSerializer):
    api_secret = serializers.CharField(write_only=True)
    passphrase = serializers.CharField(write_only=True)
    api_key_preview = serializers.CharField(source="api_key", read_only=True)

    class Meta:
        model = OKXApiToken
        fields = ["id", "broker", "api_key", "api_key_preview", "api_secret", "passphrase", "simulated_trading", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "api_key_preview", "is_active", "created_at", "updated_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        secret = validated_data.pop("api_secret")
        passphrase = validated_data.pop("passphrase")
        token = OKXApiToken(user=user, is_active=True, **validated_data)
        token.set_credentials(secret, passphrase, user)
        return token
```

In `backend/users/views.py`, import the models and serializers, then add viewsets:

```python
class BybitApiTokenViewSet(BaseApiTokenViewSet):
    queryset = BybitApiToken.objects.all()
    serializer_class = BybitApiTokenSerializer

    def verify_token(self, request):
        return Response({"valid": True}, status=status.HTTP_200_OK)


class OKXApiTokenViewSet(BaseApiTokenViewSet):
    queryset = OKXApiToken.objects.all()
    serializer_class = OKXApiTokenSerializer

    def verify_token(self, request):
        return Response({"valid": True}, status=status.HTTP_200_OK)
```

Update `broker_tokens`:

```python
        bybit_tokens = BybitApiToken.objects.filter(user=request.user)
        okx_tokens = OKXApiToken.objects.filter(user=request.user)
```

Return:

```python
                "bybit_tokens": BybitApiTokenSerializer(bybit_tokens, many=True).data,
                "okx_tokens": OKXApiTokenSerializer(okx_tokens, many=True).data,
```

Update `revoke_token` branches for `bybit` and `okx`.

In `backend/users/urls.py`, add:

```python
router.register(r"bybit-tokens", views.BybitApiTokenViewSet, basename="bybit-token")
router.register(r"okx-tokens", views.OKXApiTokenViewSet, basename="okx-token")
```

- [ ] **Step 5: Update broker filtering**

In `backend/database/views.py`, update `with_active_tokens`:

```python
            queryset = queryset.filter(
                Q(tinkoff_tokens__is_active=True)
                | Q(bybit_tokens__is_active=True)
                | Q(okx_tokens__is_active=True)
            ).distinct()
```

- [ ] **Step 6: Create migration**

Run:

```powershell
Set-Location backend
poetry run python manage.py makemigrations users --name bybit_okx_api_tokens
```

Expected: creates `backend/users/migrations/0021_bybit_okx_api_tokens.py`.

- [ ] **Step 7: Run tests to verify they pass**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/api/test_crypto_token_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add backend/users/models.py backend/users/serializers.py backend/users/views.py backend/users/urls.py backend/users/migrations/0021_bybit_okx_api_tokens.py backend/database/views.py backend/tests/integration/api/test_crypto_token_api.py
git commit -m "feat: add Bybit and OKX API credentials" -m "- What changed: Added encrypted Bybit and OKX credential storage and token APIs." -m "- Why: Direct crypto exchange import needs provider-specific credentials in User Settings." -m "- Numerical impact / example: No portfolio calculation impact." -m "- Tests added: Token save, encrypted secret retrieval, safe serialization, and active broker filtering." -m "- Reviewer(s): needs approval"
```

---

### Task 4: Exchange REST Clients And Signing

**Files:**

- Create: `backend/core/crypto_exchange_clients.py`
- Test: `backend/tests/unit/api/test_crypto_exchange_clients.py`

- [ ] **Step 1: Write failing signing tests**

Create `backend/tests/unit/api/test_crypto_exchange_clients.py`:

```python
import base64
import hashlib
import hmac

from core.crypto_exchange_clients import BybitClient, OKXClient


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
    client = OKXClient(api_key="key", api_secret="secret", passphrase="pass", simulated_trading=True)
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
    assert headers["x-simulated-trading"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/api/test_crypto_exchange_clients.py -q
```

Expected: FAIL because `core.crypto_exchange_clients` does not exist.

- [ ] **Step 3: Implement clients**

Create `backend/core/crypto_exchange_clients.py`:

```python
"""REST clients for crypto exchange imports."""

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional
from urllib.parse import urlencode

import requests


class CryptoExchangeAPIError(Exception):
    """Raised when a crypto exchange API request fails."""


@dataclass
class BybitClient:
    api_key: str
    api_secret: str
    testnet: bool = False
    recv_window: str = "5000"

    @property
    def base_url(self):
        return "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"

    def _timestamp_ms(self):
        return str(int(time.time() * 1000))

    def _signed_headers(self, timestamp: str, payload: str):
        message = f"{timestamp}{self.api_key}{self.recv_window}{payload}"
        signature = hmac.new(self.api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "X-BAPI-SIGN": signature,
        }

    def get_private(self, path: str, params: Optional[Dict] = None):
        params = params or {}
        query = urlencode(params)
        timestamp = self._timestamp_ms()
        headers = self._signed_headers(timestamp, query)
        response = requests.get(f"{self.base_url}{path}", params=params, headers=headers, timeout=30)
        data = response.json()
        if response.status_code >= 400 or data.get("retCode") not in (0, None):
            raise CryptoExchangeAPIError(data)
        return data

    def iter_transaction_log(self, params: Dict) -> Iterable[Dict]:
        cursor = ""
        while True:
            page_params = {**params, "limit": 50}
            if cursor:
                page_params["cursor"] = cursor
            data = self.get_private("/v5/account/transaction-log", page_params)
            result = data.get("result", {})
            for item in result.get("list", result.get("log", [])):
                yield item
            cursor = result.get("nextPageCursor")
            if not cursor:
                break

    def iter_executions(self, params: Dict) -> Iterable[Dict]:
        cursor = ""
        while True:
            page_params = {**params, "limit": 100}
            if cursor:
                page_params["cursor"] = cursor
            data = self.get_private("/v5/execution/list", page_params)
            result = data.get("result", {})
            for item in result.get("list", []):
                yield item
            cursor = result.get("nextPageCursor")
            if not cursor:
                break


@dataclass
class OKXClient:
    api_key: str
    api_secret: str
    passphrase: str
    simulated_trading: bool = False

    base_url: str = "https://www.okx.com"

    def _timestamp_iso(self):
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _signed_headers(self, timestamp: str, method: str, request_path: str, body: str = ""):
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).digest()
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

    def get_private(self, path: str, params: Optional[Dict] = None):
        params = params or {}
        query = urlencode(params)
        request_path = f"{path}?{query}" if query else path
        timestamp = self._timestamp_iso()
        headers = self._signed_headers(timestamp, "GET", request_path, "")
        response = requests.get(f"{self.base_url}{path}", params=params, headers=headers, timeout=30)
        data = response.json()
        if response.status_code >= 400 or data.get("code") not in ("0", None):
            raise CryptoExchangeAPIError(data)
        return data

    def iter_fills_history(self, params: Dict) -> Iterable[Dict]:
        after = None
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after
            data = self.get_private("/api/v5/trade/fills-history", page_params)
            rows = data.get("data", [])
            for item in rows:
                yield item
            if not rows:
                break
            after = rows[-1].get("billId") or rows[-1].get("tradeId")
            if not after:
                break
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/api/test_crypto_exchange_clients.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/core/crypto_exchange_clients.py backend/tests/unit/api/test_crypto_exchange_clients.py
git commit -m "feat: add crypto exchange REST clients" -m "- What changed: Added Bybit and OKX signed REST client helpers." -m "- Why: Crypto imports need authenticated transaction and execution history fetchers." -m "- Numerical impact / example: No portfolio calculation impact." -m "- Tests added: Bybit and OKX signing tests." -m "- Reviewer(s): needs approval"
```

---

### Task 5: Normalized Exchange Events And Asset Resolver

**Files:**

- Create: `backend/core/crypto_exchange_import.py`
- Test: `backend/tests/unit/imports/test_crypto_exchange_import.py`

- [ ] **Step 1: Write failing normalizer tests**

Create `backend/tests/unit/imports/test_crypto_exchange_import.py`:

```python
from decimal import Decimal

import pytest

from core.crypto_exchange_import import (
    CryptoExchangeEvent,
    normalize_bybit_spot_execution,
    normalize_okx_spot_fill,
    parse_option_symbol,
)


def test_normalize_bybit_spot_execution_buy_btc_usdt():
    event = normalize_bybit_spot_execution(
        {
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
    )

    assert event.provider_event_id == "exec-1"
    assert event.group_id == "order-1"
    assert event.category == "trade"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.1")
    assert event.legs[1]["asset"] == "USDT"
    assert event.legs[1]["quantity"] == Decimal("-6003")


def test_normalize_okx_spot_fill_sell_btc_usdt():
    event = normalize_okx_spot_fill(
        {
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
    )

    assert event.provider_event_id == "trade-1"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("-0.2001")
    assert event.legs[1]["asset"] == "USDT"
    assert event.legs[1]["quantity"] == Decimal("14000.0")


def test_parse_btc_option_symbol():
    parsed = parse_option_symbol("BTC-27JUN26-100000-C")

    assert parsed["underlying"] == "BTC"
    assert parsed["expiration_date"].isoformat() == "2026-06-27"
    assert parsed["strike_price"] == Decimal("100000")
    assert parsed["option_type"] == "CALL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/imports/test_crypto_exchange_import.py -q
```

Expected: FAIL because `core.crypto_exchange_import` does not exist.

- [ ] **Step 3: Implement normalized event helpers**

Create `backend/core/crypto_exchange_import.py`:

```python
"""Normalize crypto exchange payloads into portfolio import events."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List


@dataclass
class CryptoExchangeEvent:
    provider: str
    provider_event_id: str
    group_id: str
    timestamp_ms: int
    category: str
    raw_type: str
    legs: List[Dict]


def _split_symbol(symbol: str):
    for quote in ["USDT", "USDC", "USD", "BTC", "ETH"]:
        if symbol.endswith(quote) and symbol != quote:
            return symbol[: -len(quote)], quote
    raise ValueError(f"Cannot split crypto symbol: {symbol}")


def normalize_bybit_spot_execution(payload):
    base, quote = _split_symbol(payload["symbol"])
    qty = Decimal(payload["execQty"])
    price = Decimal(payload["execPrice"])
    value = qty * price
    fee = Decimal(payload.get("execFee") or "0")
    fee_asset = payload.get("feeCurrency") or quote

    if payload["side"].lower() == "buy":
        legs = [
            {"asset": base, "quantity": qty, "price": price},
            {"asset": quote, "quantity": -value - (fee if fee_asset == quote else Decimal("0")), "price": Decimal("1")},
        ]
    else:
        legs = [
            {"asset": base, "quantity": -qty - (fee if fee_asset == base else Decimal("0")), "price": price},
            {"asset": quote, "quantity": value - (fee if fee_asset == quote else Decimal("0")), "price": Decimal("1")},
        ]

    if fee and fee_asset not in {base, quote}:
        legs.append({"asset": fee_asset, "quantity": -fee, "price": Decimal("0")})

    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["execId"],
        group_id=payload.get("orderId") or payload["execId"],
        timestamp_ms=int(payload["execTime"]),
        category="trade",
        raw_type="spot_execution",
        legs=legs,
    )


def normalize_okx_spot_fill(payload):
    base, quote = payload["instId"].split("-")[:2]
    qty = Decimal(payload["fillSz"])
    price = Decimal(payload["fillPx"])
    value = qty * price
    fee = abs(Decimal(payload.get("fee") or "0"))
    fee_asset = payload.get("feeCcy") or quote

    if payload["side"].lower() == "buy":
        legs = [
            {"asset": base, "quantity": qty - (fee if fee_asset == base else Decimal("0")), "price": price},
            {"asset": quote, "quantity": -value - (fee if fee_asset == quote else Decimal("0")), "price": Decimal("1")},
        ]
    else:
        legs = [
            {"asset": base, "quantity": -qty - (fee if fee_asset == base else Decimal("0")), "price": price},
            {"asset": quote, "quantity": value - (fee if fee_asset == quote else Decimal("0")), "price": Decimal("1")},
        ]

    if fee and fee_asset not in {base, quote}:
        legs.append({"asset": fee_asset, "quantity": -fee, "price": Decimal("0")})

    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["tradeId"],
        group_id=payload.get("ordId") or payload["tradeId"],
        timestamp_ms=int(payload["fillTime"]),
        category="trade",
        raw_type="spot_fill",
        legs=legs,
    )


def parse_option_symbol(symbol: str):
    underlying, expiry_token, strike, option_type = symbol.split("-")
    expiry = datetime.strptime(expiry_token, "%d%b%y").date()
    return {
        "underlying": underlying,
        "expiration_date": expiry,
        "strike_price": Decimal(strike),
        "option_type": "CALL" if option_type == "C" else "PUT",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/imports/test_crypto_exchange_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/core/crypto_exchange_import.py backend/tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: normalize crypto exchange events" -m "- What changed: Added normalized crypto exchange event helpers for spot trades and option symbols." -m "- Why: Provider payloads need a stable internal shape before persistence." -m "- Numerical impact / example: BTC/USDT fill maps to BTC and USDT asset quantity legs." -m "- Tests added: Bybit spot, OKX spot, and BTC option symbol parsing." -m "- Reviewer(s): needs approval"
```

---

### Task 6: BrokerAPI Adapters And Transaction Persistence

**Files:**

- Modify: `backend/core/broker_api_utils.py`
- Modify: `backend/core/crypto_exchange_import.py`
- Modify: `backend/core/import_utils.py`
- Modify: `backend/transactions/views.py`
- Test: `backend/tests/integration/workflows/test_crypto_exchange_import.py`

- [ ] **Step 1: Write failing import persistence test**

Create `backend/tests/integration/workflows/test_crypto_exchange_import.py`:

```python
from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from constants import ASSET_TYPE_CRYPTO, TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT
from core.crypto_exchange_import import CryptoExchangeEvent, persist_crypto_exchange_event


@pytest.mark.django_db
def test_persist_crypto_trade_event_creates_linked_asset_legs(user):
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")
    event = CryptoExchangeEvent(
        provider="bybit",
        provider_event_id="exec-1",
        group_id="order-1",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_execution",
        legs=[
            {"asset": "BTC", "quantity": Decimal("0.1"), "price": Decimal("60000")},
            {"asset": "USDT", "quantity": Decimal("-6003"), "price": Decimal("1")},
        ],
    )

    created = persist_crypto_exchange_event(event, user, account)

    assert len(created) == 2
    btc = Assets.objects.get(ticker="BTC")
    usdt = Assets.objects.get(ticker="USDT")
    assert btc.type == ASSET_TYPE_CRYPTO
    assert usdt.type == ASSET_TYPE_CRYPTO
    assert Transactions.objects.get(security=btc).type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert Transactions.objects.get(security=usdt).type == TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    assert {tx.import_group_id for tx in created} == {"order-1"}


@pytest.mark.django_db
def test_persist_crypto_trade_event_is_idempotent(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Trading", native_id="okx-main")
    event = CryptoExchangeEvent(
        provider="okx",
        provider_event_id="trade-1",
        group_id="order-1",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {"asset": "BTC", "quantity": Decimal("-0.2"), "price": Decimal("70000")},
            {"asset": "USDT", "quantity": Decimal("14000"), "price": Decimal("1")},
        ],
    )

    persist_crypto_exchange_event(event, user, account)
    persist_crypto_exchange_event(event, user, account)

    assert Transactions.objects.filter(import_group_id="order-1").count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/workflows/test_crypto_exchange_import.py -q
```

Expected: FAIL because `persist_crypto_exchange_event` does not exist.

- [ ] **Step 3: Add asset resolver and persistence**

In `backend/core/crypto_exchange_import.py`, add:

```python
from datetime import datetime, timezone

from common.models import Assets, OptionMetadata, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
)


def resolve_crypto_asset(symbol, user):
    asset, _ = Assets.objects.get_or_create(
        ISIN=f"CRYPTO:{symbol}",
        currency="USD",
        defaults={
            "type": ASSET_TYPE_CRYPTO,
            "name": symbol,
            "ticker": symbol,
            "exposure": "FX" if symbol in ["USDT", "USDC"] else "Commodity",
        },
    )
    asset.investors.add(user)
    return asset


def _event_datetime(event):
    return datetime.fromtimestamp(event.timestamp_ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def persist_crypto_exchange_event(event, user, account):
    created = []
    event_time = _event_datetime(event)
    for index, leg in enumerate(event.legs):
        event_id = f"{event.provider_event_id}:{index}"
        if Transactions.objects.filter(
            investor=user,
            account=account,
            import_provider=event.provider,
            import_account_id=account.native_id,
            import_event_id=event_id,
        ).exists():
            continue

        asset = resolve_crypto_asset(leg["asset"], user)
        quantity = leg["quantity"]
        tx_type = TRANSACTION_TYPE_CRYPTO_TRADE_IN if quantity > 0 else TRANSACTION_TYPE_CRYPTO_TRADE_OUT
        tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type=tx_type,
            date=event_time,
            quantity=quantity,
            price=leg["price"],
            import_provider=event.provider,
            import_account_id=account.native_id,
            import_event_id=event_id,
            import_group_id=event.group_id,
            import_event_type=event.category,
        )
        created.append(tx)
    return created
```

- [ ] **Step 4: Add BrokerAPI adapters**

In `backend/core/broker_api_utils.py`, add `BybitAPI` and `OKXAPI` classes that connect using active tokens and yield normalized events:

```python
class BybitAPI(BrokerAPI):
    async def connect(self, user) -> bool:
        self.user = user
        return True

    async def disconnect(self) -> None:
        self.user = None

    async def get_transactions(self, account, date_from=None, date_to=None):
        token = await database_sync_to_async(
            lambda: account.broker.bybit_tokens.filter(user=self.user, is_active=True).first()
        )()
        if not token:
            raise BrokerAPIException("No active Bybit token for selected broker")
        client = BybitClient(
            api_key=token.api_key,
            api_secret=token.get_api_secret(self.user),
            testnet=token.testnet,
        )
        for payload in client.iter_executions({"category": "spot"}):
            yield normalize_bybit_spot_execution(payload)


class OKXAPI(BrokerAPI):
    async def connect(self, user) -> bool:
        self.user = user
        return True

    async def disconnect(self) -> None:
        self.user = None

    async def get_transactions(self, account, date_from=None, date_to=None):
        token = await database_sync_to_async(
            lambda: account.broker.okx_tokens.filter(user=self.user, is_active=True).first()
        )()
        if not token:
            raise BrokerAPIException("No active OKX token for selected broker")
        client = OKXClient(
            api_key=token.api_key,
            api_secret=token.get_api_secret(self.user),
            passphrase=token.get_passphrase(self.user),
            simulated_trading=token.simulated_trading,
        )
        for payload in client.iter_fills_history({"instType": "SPOT"}):
            yield normalize_okx_spot_fill(payload)
```

Update `get_broker_api` to detect `bybit_tokens` and `okx_tokens`.

- [ ] **Step 5: Persist normalized crypto events in API import flow**

In `backend/transactions/views.py`, inside `import_transactions_from_api`, before the existing transaction dictionary handling, add:

```python
                    if trans.__class__.__name__ == "CryptoExchangeEvent":
                        created = await database_sync_to_async(persist_crypto_exchange_event)(
                            trans, user, account
                        )
                        yield {
                            "status": "transaction_saved",
                            "message": f"Saved {len(created)} crypto transaction legs",
                            "transaction": {"import_group_id": trans.group_id},
                        }
                        continue
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/workflows/test_crypto_exchange_import.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/core/broker_api_utils.py backend/core/crypto_exchange_import.py backend/core/import_utils.py backend/transactions/views.py backend/tests/integration/workflows/test_crypto_exchange_import.py
git commit -m "feat: persist crypto exchange import events" -m "- What changed: Added crypto exchange event persistence and broker adapters." -m "- Why: Bybit and OKX normalized events must become canonical asset transactions." -m "- Numerical impact / example: BTC/USDT fill creates linked BTC and USDT position legs." -m "- Tests added: Multi-leg persistence and idempotent provider-event import." -m "- Reviewer(s): needs approval"
```

---

### Task 7: Frontend Credential UX

**Files:**

- Modify: `portfolio-frontend/src/components/BrokerTokenManager.vue`
- Modify: `portfolio-frontend/src/services/api.js`
- Test: `portfolio-frontend/tests/unit/components/BrokerTokenManager.crypto.spec.js`

- [ ] **Step 1: Write failing frontend tests**

Create `portfolio-frontend/tests/unit/components/BrokerTokenManager.crypto.spec.js`:

```javascript
import { mount } from '@vue/test-utils'
import BrokerTokenManager from '@/components/BrokerTokenManager.vue'
import * as api from '@/services/api'

jest.mock('@/services/api')

describe('BrokerTokenManager crypto providers', () => {
  beforeEach(() => {
    api.getBrokerTokens.mockResolvedValue({
      tinkoff_tokens: [],
      ib_tokens: [],
      bybit_tokens: [{ id: 1, api_key_preview: 'bybit-key', is_active: true, testnet: true }],
      okx_tokens: [{ id: 2, api_key_preview: 'okx-key', is_active: true, simulated_trading: false }],
    })
  })

  it('renders Bybit and OKX token sections', async () => {
    const wrapper = mount(BrokerTokenManager, {
      global: {
        stubs: ['v-card', 'v-card-title', 'v-card-text', 'v-expansion-panels', 'v-expansion-panel', 'v-expansion-panel-title', 'v-expansion-panel-text', 'v-list', 'v-list-item', 'v-icon', 'v-btn', 'v-checkbox', 'v-dialog', 'v-form', 'v-select', 'v-text-field', 'v-switch', 'v-alert', 'v-tooltip', 'v-spacer', 'v-chip', 'v-progress-linear'],
      },
    })

    await Promise.resolve()
    expect(wrapper.text()).toContain('Bybit tokens')
    expect(wrapper.text()).toContain('OKX tokens')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location portfolio-frontend
npm test -- BrokerTokenManager.crypto.spec.js --runInBand
```

Expected: FAIL because Bybit/OKX token sections and API helpers are not implemented.

- [ ] **Step 3: Add API helpers**

In `portfolio-frontend/src/services/api.js`, add:

```javascript
export const saveBybitToken = async (tokenData) => {
  const response = await axiosInstance.post('/users/api/bybit-tokens/', tokenData)
  return response.data
}

export const testBybitConnection = async (tokenId) => {
  const response = await axiosInstance.post(`/users/api/bybit-tokens/${tokenId}/test_connection/`)
  return response.data
}

export const saveOKXToken = async (tokenData) => {
  const response = await axiosInstance.post('/users/api/okx-tokens/', tokenData)
  return response.data
}

export const testOKXConnection = async (tokenId) => {
  const response = await axiosInstance.post(`/users/api/okx-tokens/${tokenId}/test_connection/`)
  return response.data
}
```

Update `deleteToken`:

```javascript
    case 'bybit':
      brokerEndpoint = 'bybit-tokens'
      break
    case 'okx':
      brokerEndpoint = 'okx-tokens'
      break
```

- [ ] **Step 4: Update token manager component**

In `BrokerTokenManager.vue`:

Add `bybitTokens` and `okxTokens` arrays to component data. In `fetchTokens`, assign:

```javascript
this.bybitTokens = response.bybit_tokens || []
this.okxTokens = response.okx_tokens || []
```

Add computed filters:

```javascript
filteredBybitTokens() {
  return this.bybitTokens.filter((token) => this.showInactiveTokens ? true : token.is_active)
},
filteredOKXTokens() {
  return this.okxTokens.filter((token) => this.showInactiveTokens ? true : token.is_active)
},
```

Add provider-specific form fields:

```vue
<template v-if="selectedProvider === 'bybit'">
  <v-text-field v-model="newToken.api_key" label="API Key" required />
  <v-text-field v-model="newToken.api_secret" label="API Secret" type="password" required />
  <v-switch v-model="newToken.testnet" label="Testnet" />
</template>

<template v-if="selectedProvider === 'okx'">
  <v-text-field v-model="newToken.api_key" label="API Key" required />
  <v-text-field v-model="newToken.api_secret" label="API Secret" type="password" required />
  <v-text-field v-model="newToken.passphrase" label="Passphrase" type="password" required />
  <v-switch v-model="newToken.simulated_trading" label="Simulated Trading" />
</template>
```

Update save/test methods to call `saveBybitToken`, `saveOKXToken`, `testBybitConnection`, and `testOKXConnection`.

- [ ] **Step 5: Run frontend test**

Run:

```powershell
Set-Location portfolio-frontend
npm test -- BrokerTokenManager.crypto.spec.js --runInBand
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add portfolio-frontend/src/components/BrokerTokenManager.vue portfolio-frontend/src/services/api.js portfolio-frontend/tests/unit/components/BrokerTokenManager.crypto.spec.js
git commit -m "feat: add crypto exchange token UX" -m "- What changed: Added Bybit and OKX credential management to User Settings." -m "- Why: Users need the existing broker API workflow for crypto exchange credentials." -m "- Numerical impact / example: No portfolio calculation impact." -m "- Tests added: BrokerTokenManager Bybit/OKX rendering test." -m "- Reviewer(s): needs approval"
```

---

### Task 8: Security Page Rewards And Transaction Descriptions

**Files:**

- Modify: `backend/core/securities_utils.py`
- Modify: `backend/database/serializers.py`
- Modify: `portfolio-frontend/src/views/database/SecurityDetailPage.vue`
- Modify: `portfolio-frontend/src/components/transactions/TransactionDescription.vue`
- Test: `backend/tests/integration/api/test_api_endpoints.py`

- [ ] **Step 1: Write failing Security detail API test**

Append to `backend/tests/integration/api/test_api_endpoints.py`:

```python
from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from constants import ASSET_TYPE_CRYPTO, TRANSACTION_TYPE_CRYPTO_REWARD


@pytest.mark.django_db
def test_security_detail_includes_crypto_reward_yield(api_client, user):
    api_client.force_authenticate(user=user)
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")
    btc = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:BTC",
        name="Bitcoin",
        ticker="BTC",
        currency="USD",
        exposure="Commodity",
    )
    btc.investors.add(user)
    Transactions.objects.create(
        investor=user,
        account=account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.010000000"),
        price=Decimal("50000.000000000"),
    )

    response = api_client.get(f"/database/api/securities/{btc.id}/")

    assert response.status_code == 200
    assert response.data["crypto_reward_native_quantity"] == Decimal("0.010000000")
    assert response.data["crypto_reward_fiat_value"] == Decimal("500.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/api/test_api_endpoints.py::test_security_detail_includes_crypto_reward_yield -q
```

Expected: FAIL because Security detail does not expose crypto reward totals.

- [ ] **Step 3: Add Security detail reward fields**

In `backend/core/securities_utils.py`, add helper:

```python
def get_crypto_reward_totals(security, user, effective_date, account_ids=None, currency="USD"):
    transactions = security.transactions.filter(
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        investor=user,
        date__date__lte=effective_date,
    )
    if account_ids:
        transactions = transactions.filter(account_id__in=account_ids)

    native_quantity = Decimal("0")
    fiat_value = Decimal("0")
    for transaction in transactions:
        native_quantity += transaction.quantity or Decimal("0")
        value = transaction.reward_value()
        if transaction.currency != currency:
            fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)["FX"]
            if fx_rate:
                value *= Decimal(fx_rate)
        fiat_value += value
    return native_quantity, round(fiat_value, 2)
```

In `get_security_detail`, add:

```python
    if security.type == ASSET_TYPE_CRYPTO:
        reward_quantity, reward_value = get_crypto_reward_totals(
            security, user, effective_current_date, account_ids=account_ids, currency=user.default_currency
        )
        security_data["crypto_reward_native_quantity"] = reward_quantity
        security_data["crypto_reward_fiat_value"] = reward_value
```

- [ ] **Step 4: Update frontend display**

In `SecurityDetailPage.vue`, add a card under summary data:

```vue
<v-card v-if="security.instrument_type === 'Crypto'" class="mb-4">
  <v-card-title>Crypto Rewards</v-card-title>
  <v-card-text>
    <v-table>
      <tbody>
        <tr>
          <td>Native rewards</td>
          <td>{{ security.crypto_reward_native_quantity }}</td>
        </tr>
        <tr>
          <td>Fiat reward value</td>
          <td>{{ security.crypto_reward_fiat_value }}</td>
        </tr>
      </tbody>
    </v-table>
  </v-card-text>
</v-card>
```

In `TransactionDescription.vue`, include crypto descriptions:

```javascript
const isCryptoEvent = computed(() =>
  [
    'Crypto reward',
    'Crypto transfer in',
    'Crypto transfer out',
    'Crypto trade in',
    'Crypto trade out',
    'Option settlement',
  ].includes(props.transaction.type)
)
```

Render `Crypto reward` as:

```vue
<span v-if="transaction.type === 'Crypto reward'">
  reward of {{ transaction.quantity }} {{ transaction.security?.ticker || transaction.security?.name }}
</span>
```

- [ ] **Step 5: Run backend test**

Run:

```powershell
Set-Location backend
poetry run pytest tests/integration/api/test_api_endpoints.py::test_security_detail_includes_crypto_reward_yield -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/core/securities_utils.py backend/database/serializers.py backend/tests/integration/api/test_api_endpoints.py portfolio-frontend/src/views/database/SecurityDetailPage.vue portfolio-frontend/src/components/transactions/TransactionDescription.vue
git commit -m "feat: show crypto rewards on security pages" -m "- What changed: Added native and fiat crypto reward totals and transaction descriptions." -m "- Why: Security pages need separate native yield and fiat capital-distribution visibility." -m "- Numerical impact / example: 0.01 BTC reward at 50000 USD shows 500.00 USD fiat reward value." -m "- Tests added: Security detail crypto reward API regression." -m "- Reviewer(s): needs approval"
```

---

### Task 9: Final Verification And PR Preparation

**Files:**

- Modify: `docs/superpowers/plans/2026-06-07-crypto-exchange-brokers.md` only if execution notes need checked-off updates.

- [ ] **Step 1: Run backend focused tests**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/api/test_crypto_exchange_clients.py tests/unit/imports/test_crypto_exchange_import.py tests/unit/calculations/test_crypto_rewards.py tests/integration/api/test_crypto_token_api.py tests/integration/workflows/test_crypto_exchange_import.py -q
```

Expected: PASS.

- [ ] **Step 2: Run protected calculation regression tests**

Run:

```powershell
Set-Location backend
poetry run pytest tests/unit/calculations/test_buy_in_price.py tests/unit/calculations/test_gain_loss.py tests/unit/calculations/test_nav_calculations.py tests/unit/calculations/test_bond_aci.py -q
```

Expected: PASS.

- [ ] **Step 3: Run migration check**

Run:

```powershell
Set-Location backend
poetry run python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 4: Run frontend token manager test**

Run:

```powershell
Set-Location portfolio-frontend
npm test -- BrokerTokenManager.crypto.spec.js --runInBand
```

Expected: PASS.

- [ ] **Step 5: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Inspect protected file list for PR description**

Run:

```powershell
git diff --name-only origin/fix/general-fixes...HEAD
```

Expected: includes protected files `backend/common/models.py`, migrations, and calculation-adjacent modules. Use this list in PR description.

- [ ] **Step 7: Create final commit if verification notes changed**

Only run this when the plan checklist or docs changed after Task 8:

```powershell
git add docs/superpowers/plans/2026-06-07-crypto-exchange-brokers.md
git commit -m "docs: update crypto exchange implementation plan" -m "- What changed: Updated implementation plan execution notes." -m "- Why: Keep PR review trail aligned with completed work." -m "- Numerical impact / example: Documentation-only change." -m "- Tests added: Not applicable." -m "- Reviewer(s): needs approval"
```

- [ ] **Step 8: Prepare PR summary**

Use this PR summary structure:

```markdown
## Summary

Adds asset-led crypto exchange import support for Bybit and OKX:
- crypto/stablecoin assets
- provider import metadata and dedupe
- Bybit/OKX encrypted credential APIs
- signed REST clients
- normalized spot trade imports
- crypto reward capital distribution behavior
- Security page native/fiat reward visibility

## Protected Areas

This PR touches protected financial logic and schema:
- `backend/common/models.py`
- `backend/common/migrations/*`
- `backend/users/migrations/*`
- calculation behavior for cost basis, capital distribution, and realized gain/loss

Label required: `needs-approval`

## Numerical Example

Reward fixture:
- 0.010000000 BTC reward at 50000.000000000 USD
- native position increases by 0.010000000 BTC
- capital distribution increases by 500.00 USD
- account fiat cash balance remains unchanged

Trade fixture:
- Buy 0.1 BTC for 6000 USDT with 3 USDT fee
- BTC asset position increases by 0.1
- USDT asset position decreases by 6003
- linked rows share provider group id

## Verification

- `poetry run pytest tests/unit/api/test_crypto_exchange_clients.py tests/unit/imports/test_crypto_exchange_import.py tests/unit/calculations/test_crypto_rewards.py tests/integration/api/test_crypto_token_api.py tests/integration/workflows/test_crypto_exchange_import.py -q`
- `poetry run pytest tests/unit/calculations/test_buy_in_price.py tests/unit/calculations/test_gain_loss.py tests/unit/calculations/test_nav_calculations.py tests/unit/calculations/test_bond_aci.py -q`
- `poetry run python manage.py makemigrations --check --dry-run`
- `npm test -- BrokerTokenManager.crypto.spec.js --runInBand`
- `git diff --check`
```
