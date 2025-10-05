# Transaction Display Unification Plan

## Current Problem

Transaction formatting exists in **two places** on backend:

1. **`_process_regular_transaction()` in `core/transactions_utils.py`**
   - Used by `get_transactions_table_api` for TransactionsPage
   - Manual field-by-field formatting
   - Calculates running balances

2. **`TransactionSerializer` in `database/serializers.py`**
   - Used by `api_get_security_transactions` for SecurityDetailPage
   - Uses serializer methods for formatting
   - NO balance calculation

On frontend, display logic is duplicated in:
- `TransactionsPage.vue` (complex template with balances)
- `SecurityDetailPage.vue` (simpler transaction display)

## Proposed Solution: DRY Architecture

### Backend Unification

#### Strategy
**Use `TransactionSerializer` as the ONLY formatting source**, enhance it to optionally handle balances.

#### Changes Needed

1. **Enhance `TransactionSerializer`** to:
   - Accept `include_balances` context parameter
   - Accept `balance_tracker` context parameter (for running balance)
   - Add `balances` field (optional)
   - Add `instrument_type` field for frontend formatting
   - Handle both regular and FX transactions

2. **Refactor `get_transactions_table_api`** to:
   - Use `TransactionSerializer` instead of `_process_regular_transaction`
   - Pass balance tracker via context
   - Remove duplicate formatting code

3. **Deprecate** `_process_regular_transaction` and `_process_fx_transaction`

### Frontend Unification

#### Strategy
Create a **reusable component** for transaction row display.

#### Component Structure

```
components/
  transactions/
    TransactionRow.vue          ← New reusable component
    TransactionDescription.vue  ← New: handles description logic
    TransactionCashFlow.vue     ← New: handles cash flow display
```

#### Changes Needed

1. **Create `TransactionRow.vue`**
   - Props: `transaction`, `currencies`, `showBalances`
   - Emits: `edit`, `delete`
   - Uses sub-components for description and cash flow

2. **Create `TransactionDescription.vue`**
   - Handles all transaction type display logic
   - Single source of truth for description formatting
   - Props: `transaction`

3. **Create `TransactionCashFlow.vue`**
   - Handles cash flow display per currency
   - Props: `transaction`, `currency`

4. **Update `TransactionsPage.vue`**
   - Use `<TransactionRow>` with `showBalances=true`

5. **Update `SecurityDetailPage.vue`**
   - Use `<TransactionRow>` with `showBalances=false`

## Implementation Plan

### Phase 1: Backend Serializer Enhancement

#### Step 1.1: Enhance TransactionSerializer

```python
# database/serializers.py

class TransactionSerializer(serializers.ModelSerializer):
    # Existing fields...
    balances = serializers.SerializerMethodField()
    instrument_type = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()  # 'regular' or 'fx'

    class Meta:
        model = Transactions
        fields = [
            "id",
            "transaction_type",
            "date",
            "type",
            "quantity",
            "price",
            "value",
            "cash_flow",
            "commission",
            "aci",
            "currency",
            "security_name",
            "security_id",
            "instrument_type",
            "account",
            "notional_change",
            "notional",
            "balances",  # NEW: optional
        ]

    def get_balances(self, obj):
        """Return balances if balance tracking is enabled in context"""
        if not self.context.get('include_balances', False):
            return None

        balance_tracker = self.context.get('balance_tracker', {})
        return balance_tracker.get(obj.id, {})

    def get_instrument_type(self, obj):
        """Return instrument type for frontend formatting"""
        return obj.security.type if obj.security else None

    def get_transaction_type(self, obj):
        """Return 'regular' or 'fx' based on model type"""
        return 'regular'  # Override in FXTransactionSerializer

    def get_price(self, obj):
        """Format price based on instrument type"""
        instrument_type = self.get_instrument_type(obj)
        effective_price = obj.get_price()

        # For bonds, show as percentage
        if instrument_type and instrument_type.lower() == 'bond':
            return format_bond_price(obj.price, self.get_digits())

        return format_value(effective_price, "price", obj.currency, self.get_digits())
```

#### Step 1.2: Create FXTransactionSerializer

```python
# database/serializers.py

class FXTransactionSerializer(serializers.ModelSerializer):
    """Serializer for FX transactions to match regular transaction format"""

    date = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()
    from_cur = serializers.CharField(source='from_currency')
    to_cur = serializers.CharField(source='to_currency')
    from_amount = serializers.SerializerMethodField()
    to_amount = serializers.SerializerMethodField()
    exchange_rate = serializers.SerializerMethodField()
    balances = serializers.SerializerMethodField()

    class Meta:
        model = FXTransaction
        fields = [
            "id",
            "transaction_type",
            "date",
            "type",
            "from_cur",
            "to_cur",
            "from_amount",
            "to_amount",
            "exchange_rate",
            "commission",
            "account",
            "balances",
        ]

    def get_transaction_type(self, obj):
        return 'fx'

    # ... other methods
```

#### Step 1.3: Create BalanceTracker Helper Class

```python
# core/transactions_utils.py

class BalanceTracker:
    """Helper class to track running balances across transactions"""

    def __init__(self, currencies, initial_balances=None):
        self.currencies = currencies
        self.balances = {currency: Decimal(0) for currency in currencies}
        if initial_balances:
            self.balances.update(initial_balances)
        self.transaction_balances = {}

    def process_transaction(self, transaction, number_of_digits):
        """Process a transaction and update balances"""
        if isinstance(transaction, Transactions):
            self._process_regular(transaction)
        elif isinstance(transaction, FXTransaction):
            self._process_fx(transaction)

        # Store formatted balances for this transaction
        self.transaction_balances[transaction.id] = {
            currency: currency_format(self.balances[currency], currency, number_of_digits)
            for currency in self.currencies
        }

    def _process_regular(self, transaction):
        """Update balance for regular transaction"""
        effective_price = transaction.get_price() or Decimal(0)
        balance_entry = self.balances.get(transaction.currency, Decimal(0)) - Decimal(
            effective_price * Decimal(transaction.quantity or Decimal(0))
            - Decimal(transaction.aci or Decimal(0))
            - Decimal(transaction.cash_flow or Decimal(0))
            - Decimal(transaction.commission or Decimal(0))
        )
        self.balances[transaction.currency] = round(balance_entry, 2)

    def _process_fx(self, transaction):
        """Update balance for FX transaction"""
        self.balances[transaction.from_currency] += transaction.from_amount
        self.balances[transaction.to_currency] += transaction.to_amount
        if transaction.commission:
            self.balances[transaction.commission_currency] -= transaction.commission

    def get_balances_dict(self):
        """Return dictionary of transaction_id -> formatted balances"""
        return self.transaction_balances
```

#### Step 1.4: Refactor get_transactions_table_api

```python
# core/transactions_utils.py

def get_transactions_table_api(request):
    # ... existing setup code ...

    # Get currencies
    currencies = set()
    for account in Accounts.objects.filter(broker__investor=user, id__in=selected_account_ids):
        currencies.update(account.get_currencies())

    # Calculate initial balances if start_date provided
    initial_balances = {}
    if start_date:
        for account_id in selected_account_ids:
            account = Accounts.objects.get(id=account_id)
            account_balance = account.balance(start_date)
            for currency, amount in account_balance.items():
                initial_balances[currency] = initial_balances.get(currency, Decimal(0)) + amount

    # Create balance tracker
    balance_tracker = BalanceTracker(currencies, initial_balances)

    # Process transactions to calculate balances
    for transaction in transactions:
        balance_tracker.process_transaction(transaction, number_of_digits)

    # Serialize transactions with balance context
    regular_transactions = [t for t in transactions if isinstance(t, Transactions)]
    fx_transactions = [t for t in transactions if isinstance(t, FXTransaction)]

    regular_serializer = TransactionSerializer(
        regular_transactions,
        many=True,
        context={
            'include_balances': True,
            'balance_tracker': balance_tracker.transaction_balances,
            'digits': number_of_digits,
        }
    )

    fx_serializer = FXTransactionSerializer(
        fx_transactions,
        many=True,
        context={
            'include_balances': True,
            'balance_tracker': balance_tracker.transaction_balances,
            'digits': number_of_digits,
        }
    )

    # Combine and sort transactions
    all_transactions = list(regular_serializer.data) + list(fx_serializer.data)
    all_transactions.sort(key=lambda x: x['date'])

    # Apply pagination
    paginated_transactions, pagination_data = paginate_table(
        all_transactions, page, items_per_page
    )

    return {
        "transactions": paginated_transactions,  # Already formatted by serializer
        "currencies": list(currencies),
        "total_items": pagination_data["total_items"],
        "current_page": pagination_data["current_page"],
        "total_pages": pagination_data["total_pages"],
    }
```

### Phase 2: Frontend Component Creation

#### Step 2.1: Create TransactionDescription.vue

```vue
<!-- components/transactions/TransactionDescription.vue -->
<template>
  <span class="text-start text-nowrap">
    <!-- Bond Redemption/Maturity -->
    <template v-if="isBondRedemption">
      of {{ transaction.notional_change }} {{ transaction.cur }} for
      <security-link :id="transaction.security?.id" :name="transaction.security?.name" />
    </template>

    <!-- Cash transactions -->
    <template v-else-if="isCashTransaction">
      {{ transaction.type }} {{ transaction.cash_flow }}
      <template v-if="isDividendOrCoupon">
        for <security-link :id="transaction.security?.id" :name="transaction.security?.name" />
      </template>
    </template>

    <!-- FX Transaction -->
    <template v-else-if="isFXTransaction">
      : {{ transaction.from_cur }} to {{ transaction.to_cur }} @
      {{ formatExchangeRate(transaction.exchange_rate) }}
      <commission-display v-if="transaction.commission" :commission="transaction.commission" />
    </template>

    <!-- Close -->
    <template v-else-if="transaction.type === 'Close'">
      {{ transaction.quantity }} of
      <security-link :id="transaction.security?.id" :name="transaction.security?.name" />
    </template>

    <!-- Regular transaction (Buy/Sell) -->
    <template v-else-if="isRegularTransaction">
      {{ transaction.quantity }} @ {{ transaction.price }} of
      <security-link :id="transaction.security?.id" :name="transaction.security?.name" />
      <commission-display v-if="transaction.commission" :commission="transaction.commission" />
      <aci-display v-if="transaction.aci" :aci="transaction.aci" />
    </template>

    <!-- Tax -->
    <template v-else-if="transaction.type === 'Tax' && transaction.security?.name">
      for <security-link :id="transaction.security?.id" :name="transaction.security?.name" />
      <span v-if="transaction.security?.type === 'Bond'"> coupon </span>
      <span v-else> dividend </span>
    </template>
  </span>
</template>

<script>
import { computed } from 'vue'
import SecurityLink from './SecurityLink.vue'
import CommissionDisplay from './CommissionDisplay.vue'
import AciDisplay from './AciDisplay.vue'

export default {
  name: 'TransactionDescription',
  components: { SecurityLink, CommissionDisplay, AciDisplay },
  props: {
    transaction: {
      type: Object,
      required: true
    }
  },
  setup(props) {
    const isBondRedemption = computed(() =>
      ['Bond redemption', 'Bond maturity'].includes(props.transaction.type)
    )

    const isCashTransaction = computed(() =>
      props.transaction.type.includes('Cash') ||
      props.transaction.type === 'Dividend' ||
      props.transaction.type === 'Coupon'
    )

    const isDividendOrCoupon = computed(() =>
      props.transaction.type === 'Dividend' ||
      props.transaction.type === 'Coupon'
    )

    const isFXTransaction = computed(() =>
      props.transaction.type === 'FX'
    )

    const isRegularTransaction = computed(() =>
      !['Broker commission', 'Tax', 'Interest income', 'Bond redemption', 'Bond maturity']
        .includes(props.transaction.type)
    )

    const formatExchangeRate = (rate) => {
      const rateNum = parseFloat(rate)
      if (rateNum < 1 && rateNum > 0) {
        return `${(1 / rateNum).toFixed(4)}`
      }
      return rateNum.toFixed(4)
    }

    return {
      isBondRedemption,
      isCashTransaction,
      isDividendOrCoupon,
      isFXTransaction,
      isRegularTransaction,
      formatExchangeRate
    }
  }
}
</script>
```

#### Step 2.2: Create TransactionRow.vue

```vue
<!-- components/transactions/TransactionRow.vue -->
<template>
  <tr>
    <td v-if="showActions" />
    <td>{{ transaction.date }}</td>
    <td class="text-start">
      <transaction-description :transaction="transaction" />
    </td>
    <td class="text-center">{{ transaction.type }}</td>

    <!-- Cash Flow columns (per currency) -->
    <template v-if="showCashFlow">
      <td
        v-for="currency in currencies"
        :key="`cash_flow-${currency}`"
        class="text-center"
      >
        <transaction-cash-flow :transaction="transaction" :currency="currency" />
      </td>
    </template>

    <!-- Spacer -->
    <td v-if="showBalances" class="text-center" />

    <!-- Balance columns (per currency) -->
    <template v-if="showBalances">
      <td
        v-for="currency in currencies"
        :key="`balance-${currency}`"
        class="text-center"
      >
        {{ transaction.balances?.[currency] || '–' }}
      </td>
    </template>

    <!-- Actions -->
    <td v-if="showActions" class="text-end">
      <v-icon small class="mr-2" @click="$emit('edit', transaction)">
        mdi-pencil
      </v-icon>
      <v-icon small @click="$emit('delete', transaction)">
        mdi-delete
      </v-icon>
    </td>
  </tr>
</template>

<script>
import TransactionDescription from './TransactionDescription.vue'
import TransactionCashFlow from './TransactionCashFlow.vue'

export default {
  name: 'TransactionRow',
  components: { TransactionDescription, TransactionCashFlow },
  props: {
    transaction: {
      type: Object,
      required: true
    },
    currencies: {
      type: Array,
      default: () => []
    },
    showBalances: {
      type: Boolean,
      default: false
    },
    showActions: {
      type: Boolean,
      default: true
    },
    showCashFlow: {
      type: Boolean,
      default: true
    }
  },
  emits: ['edit', 'delete']
}
</script>
```

#### Step 2.3: Update TransactionsPage.vue

```vue
<!-- Replace the template #item section -->
<template #item="{ item }">
  <transaction-row
    :transaction="item"
    :currencies="currencies"
    :show-balances="true"
    :show-cash-flow="true"
    @edit="editTransaction"
    @delete="processDeleteTransaction"
  />
</template>
```

#### Step 2.4: Update SecurityDetailPage.vue

```vue
<!-- Replace the template #item section -->
<template #item="{ item }">
  <transaction-row
    :transaction="item"
    :currencies="[]"
    :show-balances="false"
    :show-cash-flow="true"
    :show-actions="false"
  />
</template>
```

## Benefits of This Approach

### Backend Benefits
1. ✅ **Single Source of Truth**: `TransactionSerializer` formats ALL transactions
2. ✅ **Consistency**: Same formatting logic everywhere
3. ✅ **Maintainability**: Change once, applies everywhere
4. ✅ **Testability**: Test serializer once instead of multiple functions
5. ✅ **Extensibility**: Easy to add new transaction types

### Frontend Benefits
1. ✅ **Reusability**: Components used in multiple views
2. ✅ **Consistency**: Same display logic everywhere
3. ✅ **Maintainability**: Update component once
4. ✅ **Flexibility**: Props control what to show
5. ✅ **Smaller Files**: Split complex template into manageable pieces

## Migration Path

### Step-by-Step Migration

1. **Phase 1**: Enhance serializer (no breaking changes)
2. **Phase 2**: Create frontend components (parallel to existing)
3. **Phase 3**: Update `get_transactions_table_api` to use serializer
4. **Phase 4**: Update frontend to use new components
5. **Phase 5**: Remove deprecated functions

## Testing Checklist

- [ ] TransactionsPage displays correctly with balances
- [ ] SecurityDetailPage displays correctly without balances
- [ ] Bond prices show as percentages
- [ ] FX transactions display correctly
- [ ] All transaction types render properly
- [ ] Edit/Delete actions work
- [ ] Pagination works
- [ ] Search/filter works
- [ ] Performance is acceptable

---

**Status:** ✅ Implementation Complete
**Date:** October 5, 2025
**Impact:** High - Major refactoring for long-term maintainability

## Implementation Status

### Backend (Phase 1) ✅ Complete
- ✅ Enhanced `TransactionSerializer` with balances, instrument_type, transaction_type
- ✅ Created `FXTransactionSerializer` for consistent FX handling
- ✅ Created `BalanceTracker` helper class
- ✅ Refactored `get_transactions_table_api` to use serializers
- ✅ Added centralized `get_calculated_cash_flow()` method
- ✅ Deprecated old processing functions

### Frontend (Phase 2) ✅ Complete
- ✅ Created `SecurityLink.vue` component
- ✅ Created `CommissionDisplay.vue` component
- ✅ Created `AciDisplay.vue` component
- ✅ Created `TransactionCashFlow.vue` component
- ✅ Created `TransactionDescription.vue` component
- ✅ Created `TransactionRow.vue` main component
- ✅ Updated `TransactionsPage.vue` to use `TransactionRow`
- ✅ Updated `SecurityDetailPage.vue` to use `TransactionRow`

### Files Created
**Backend:**
- `portfolio_management/core/balance_tracker.py` - Multi-currency balance tracking
- `portfolio_management/tests/test_transaction_unification.py` - Comprehensive test suite

**Frontend:**
- `portfolio-frontend/src/components/transactions/SecurityLink.vue`
- `portfolio-frontend/src/components/transactions/CommissionDisplay.vue`
- `portfolio-frontend/src/components/transactions/AciDisplay.vue`
- `portfolio-frontend/src/components/transactions/TransactionCashFlow.vue`
- `portfolio-frontend/src/components/transactions/TransactionDescription.vue`
- `portfolio-frontend/src/components/transactions/TransactionRow.vue`

### Files Modified
**Backend:**
- `portfolio_management/common/models.py` - Added `get_calculated_cash_flow()`
- `portfolio_management/database/serializers.py` - Enhanced serializers
- `portfolio_management/core/transactions_utils.py` - Refactored to use serializers
- `portfolio_management/core/portfolio_utils.py` - Simplified IRR calculation

**Frontend:**
- `portfolio-frontend/src/views/TransactionsPage.vue` - ~170 lines → 10 lines in template
- `portfolio-frontend/src/views/database/SecurityDetailPage.vue` - ~50 lines → 10 lines in template

### Code Reduction
- **Backend**: Eliminated ~100 lines of duplicate formatting code
- **Frontend TransactionsPage.vue**: Reduced template section from 170 to 10 lines (94% reduction)
- **Frontend SecurityDetailPage.vue**: Reduced template section from 50 to 10 lines (80% reduction)
- **Total**: ~300+ lines of duplicate code eliminated

### Next Steps
1. Run backend tests: `pytest portfolio_management/tests/test_transaction_unification.py -v`
2. Start Django server and frontend to verify everything works
3. Test both transaction pages visually
4. Remove deprecated code after thorough testing
