# Transaction Processing Patterns

## Overview

This document captures the unified transaction processing architecture and patterns that ensure consistent handling of all transaction types across the portfolio management system. It covers centralized calculations, serialization patterns, and the DRY implementation that eliminated duplicate code.

---

## Transaction Model Conventions

### Field Usage for Buy/Sell Transactions

**IMPORTANT**: For buy and sell transactions with price and quantity:

1. **cash_flow field**: Should be `None` (not set)
   - The cash flow is calculated from `price * quantity + commission`
   - Do NOT duplicate this calculation in the cash_flow field

2. **commission field**: Uses natural sign convention
   - **Negative value** = expense (most common case)
   - **Positive value** = rebate/credit
   - Example: `commission=Decimal("-5.00")` means a $5 expense

3. **Required fields for Buy/Sell**:
   - `type`: Transaction type ("Buy", "Sell", etc.)
   - `date`: Transaction date
   - `quantity`: Number of units (positive for Buy, negative for Sell)
   - `price`: Price per unit
   - `commission`: Commission amount with natural sign
   - `account`: Account reference (not `broker`)
   - `investor`: User reference
   - `security`: Asset reference

### Correct Transaction Creation Example

```python
# BUY transaction
buy_tx = Transactions.objects.create(
    investor=user,
    account=account,  # Note: account, not broker
    security=asset,
    currency="USD",
    type="Buy",
    date=date(2023, 1, 15),
    quantity=Decimal("100"),
    price=Decimal("50.00"),
    commission=Decimal("-5.00"),  # Negative = expense
    # cash_flow is NOT set - it's calculated
)

# SELL transaction
sell_tx = Transactions.objects.create(
    investor=user,
    account=account,
    security=asset,
    currency="USD",
    type="Sell",
    date=date(2023, 3, 15),
    quantity=Decimal("-100"),  # Negative for sell
    price=Decimal("55.00"),
    commission=Decimal("-5.00"),  # Negative = expense
    # cash_flow is NOT set - it's calculated
)
```

### Special Transaction Types

**Dividend Transactions**:
- `quantity`: `None`
- `price`: `None`
- `cash_flow`: The dividend amount received (positive)
- `commission`: Usually `None`, or negative if fees apply

**Corporate Actions** (splits, etc.):
- `cash_flow`: `Decimal("0.00")` (no cash movement)
- `quantity`: Adjusted share count
- `price`: Adjusted price after split
- `commission`: `None`

### Model Relationships

**Assets Model**:
- Uses `investors` (ManyToManyField) - NOT `investor`
- Does NOT have a `brokers` field
- Has `type` field (e.g., "Stock", "Bond") - NOT `instrument_type`

**Transactions/FXTransaction Models**:
- Use `account` field (ForeignKey to Accounts)
- Do NOT use `broker` field directly
- Must have `investor` field (ForeignKey to CustomUser)

**Brokers and Accounts**:
- Brokers have a ManyToOne relationship with investors
- Accounts belong to Brokers
- Transactions reference Accounts (which link to Brokers)

**Assets.position() Method**:
```python
# Requires investor parameter
position = asset.position(date, investor)  # Correct
position = asset.position(date)  # Wrong - missing investor
```

---

## Centralized Transaction Architecture

### Core Principle: Single Source of Truth

All transaction processing now flows through centralized methods to ensure consistency across the application:

1. **Central Cash Flow Calculation** - `Transactions.get_calculated_cash_flow()`
2. **Unified Serializers** - `TransactionSerializer` and `FXTransactionSerializer`
3. **Balance Tracking** - `BalanceTracker` helper class
4. **Consistent Formatting** - Single formatting logic for all views

---

## Central Cash Flow Calculation

### Location: `common/models.py`

The `get_calculated_cash_flow()` method serves as the single source of truth for all cash flow calculations:

```python
class Transactions(models.Model):
    def get_calculated_cash_flow(self, target_currency=None):
        """
        Calculate the cash flow for this transaction with consistent logic.

        Handles all transaction types:
        - Buy/Sell: quantity × price + commission + ACI
        - Dividends/Coupons: cash_flow (as provided)
        - Bond Redemptions: cash_flow (return of capital)
        - FX Transactions: to_amount - from_amount
        """
        if self.type in ['Buy', 'Sell']:
            # Standard security transaction
            cash_flow = self.quantity * self.get_price()  # Uses get_price() for bonds

            # Add accrued interest for bonds
            if self.security.is_bond and self.aci:
                cash_flow += self.aci

            # Add commission
            if self.commission:
                cash_flow += self.commission

            # Buy transactions are negative cash flow
            if self.type == 'Buy':
                cash_flow = -cash_flow

        elif self.type in ['Dividend', 'Coupon']:
            cash_flow = self.cash_flow

        elif self.type in ['Bond redemption', 'Bond maturity']:
            cash_flow = self.cash_flow  # Return of capital

        elif self.type == 'FX':
            # FX transactions handle currency conversion separately
            cash_flow = self.to_amount - self.from_amount

        else:
            # Cash in/out, etc.
            cash_flow = self.cash_flow or 0

        # Currency conversion if needed
        if target_currency and target_currency != self.currency:
            cash_flow = self.convert_to_currency(cash_flow, target_currency)

        return cash_flow
```

### Key Features

#### 1. Bond Price Handling
```python
def get_price(self):
    """
    Get price with proper bond handling.

    Returns:
    - Bonds: Actual price (percentage of par converted to actual value)
    - Others: Nominal price as stored
    """
    if self.security.is_bond:
        # Bond prices stored as percentage of par (e.g., 98.5 = 98.5%)
        # Convert to actual price using current notional
        notional = self.security.get_current_notional(self.date, self.investor)
        return self.price * notional / 100
    else:
        return self.price
```

#### 2. ACI (Accrued Interest) Support
```python
# For bonds, include accrued interest in cash flow
if self.security.is_bond and self.aci:
    cash_flow += self.aci
```

#### 3. Currency Conversion
```python
def convert_to_currency(self, amount, target_currency):
    """Convert amount to target currency using FX rates"""
    if self.currency == target_currency:
        return amount

    fx_rate = FX.get_rate(self.currency, target_currency, self.date)
    return amount * fx_rate
```

---

## Unified Serializers

### Location: `database/serializers.py`

#### TransactionSerializer
```python
class TransactionSerializer(serializers.ModelSerializer):
    """Unified serializer for all non-FX transactions"""

    id = serializers.SerializerMethodField()  # Prefixed ID (e.g., "regular_123")
    transaction_type = serializers.CharField(default="regular")
    security = SecuritySerializer(read_only=True)
    instrument_type = serializers.CharField(source='security.type', read_only=True)
    balances = serializers.SerializerMethodField()  # Optional balance tracking

    # Formatted fields
    price = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()
    cash_flow = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()

    class Meta:
        model = Transactions
        fields = [
            'id', 'transaction_type', 'date', 'type',
            'security', 'instrument_type', 'quantity', 'price', 'value',
            'cash_flow', 'commission', 'currency', 'account', 'balances'
        ]

    def get_id(self, obj):
        return f"regular_{obj.id}"

    def get_price(self, obj):
        """Format price: bonds as percentage, others as actual price"""
        if obj.security.is_bond:
            return f"{obj.price}%"
        else:
            return currency_format(obj.price, obj.currency)

    def get_cash_flow(self, obj):
        """Use centralized cash flow calculation"""
        cash_flow = obj.get_calculated_cash_flow()
        return currency_format(cash_flow, obj.currency, absolute_value=True)

    def get_value(self, obj):
        """Calculate transaction value"""
        if obj.type in ['Buy', 'Sell']:
            value = abs(obj.quantity) * obj.get_price()
            if obj.security.is_bond and obj.aci:
                value += obj.aci
            return currency_format(value, obj.currency)
        return None

    def get_balances(self, obj):
        """Optional balance tracking per transaction"""
        if hasattr(obj, '_balances'):
            return {
                currency: currency_format(amount, currency)
                for currency, amount in obj._balances.items()
            }
        return None
```

#### FXTransactionSerializer
```python
class FXTransactionSerializer(serializers.ModelSerializer):
    """Unified serializer for FX transactions"""

    id = serializers.SerializerMethodField()  # Prefixed ID (e.g., "fx_123")
    transaction_type = serializers.CharField(default="fx")
    balances = serializers.SerializerMethodField()

    # Formatted fields
    source_amount = serializers.SerializerMethodField()
    target_amount = serializers.SerializerMethodField()
    exchange_rate = serializers.SerializerMethodField()

    class Meta:
        model = FXTransaction
        fields = [
            'id', 'transaction_type', 'date', 'type',
            'source_currency', 'target_currency',
            'source_amount', 'target_amount', 'exchange_rate',
            'commission', 'account', 'balances'
        ]

    def get_id(self, obj):
        return f"fx_{obj.id}"

    def get_source_amount(self, obj):
        return currency_format(-obj.from_amount, obj.source_currency, absolute_value=True)

    def get_target_amount(self, obj):
        return currency_format(obj.to_amount, obj.target_currency)

    def get_exchange_rate(self, obj):
        return format_exchange_rate(obj.exchange_rate)

    def get_balances(self, obj):
        if hasattr(obj, '_balances'):
            return {
                currency: currency_format(amount, currency)
                for currency, amount in obj._balances.items()
            }
        return None
```

---

## BalanceTracker Helper Class

### Location: `core/balance_tracker.py`

The `BalanceTracker` class provides unified multi-currency balance tracking:

```python
from decimal import Decimal
from common.models import currency_format

class BalanceTracker:
    """
    Unified balance tracking for transaction processing.

    Supports:
    - Multi-currency balances
    - Both regular and FX transactions
    - Per-transaction balance snapshots
    - Consistent formatting using currency_format()
    """

    def __init__(self, number_of_digits=2):
        self.balances = {}  # {currency: Decimal}
        self.per_transaction_balances = {}  # {transaction_id: {currency: Decimal}}
        self.number_of_digits = number_of_digits

    def set_initial_balances(self, initial_balances):
        """Set starting balances"""
        self.balances = {
            currency: Decimal(str(amount))
            for currency, amount in initial_balances.items()
        }

    def update(self, transaction):
        """Update balances based on transaction"""
        transaction_balances = self.balances.copy()

        if transaction.__class__.__name__ == 'Transactions':
            # Regular transaction
            cash_flow = transaction.get_calculated_cash_flow()
            currency = transaction.currency

            # Update balance
            current_balance = self.balances.get(currency, Decimal('0'))
            new_balance = current_balance + cash_flow
            self.balances[currency] = new_balance
            transaction_balances[currency] = new_balance

        elif transaction.__class__.__name__ == 'FXTransaction':
            # FX transaction
            # Subtract from source currency
            source_balance = self.balances.get(transaction.source_currency, Decimal('0'))
            new_source_balance = source_balance - transaction.from_amount
            self.balances[transaction.source_currency] = new_source_balance
            transaction_balances[transaction.source_currency] = new_source_balance

            # Add to target currency
            target_balance = self.balances.get(transaction.target_currency, Decimal('0'))
            new_target_balance = target_balance + transaction.to_amount
            self.balances[transaction.target_currency] = new_target_balance
            transaction_balances[transaction.target_currency] = new_target_balance

        # Store per-transaction snapshot
        self.per_transaction_balances[transaction.id] = transaction_balances

    def get_balances_for_transaction(self, transaction_id):
        """Get balance snapshot for specific transaction"""
        return self.per_transaction_balances.get(transaction_id, self.balances)

    def get_current_balances(self):
        """Get current balances"""
        return {
            currency: currency_format(amount, currency, self.number_of_digits)
            for currency, amount in self.balances.items()
        }
```

### Usage Example

```python
def calculate_transactions_with_balances(transactions, initial_balances):
    """Calculate transaction table with balance tracking"""

    tracker = BalanceTracker(number_of_digits=2)
    tracker.set_initial_balances(initial_balances)

    processed_transactions = []

    for transaction in transactions:
        # Update balances
        tracker.update(transaction)

        # Store balance reference on transaction
        transaction._balances = tracker.get_balances_for_transaction(transaction.id)

        # Serialize with balance information
        if transaction.__class__.__name__ == 'Transactions':
            serializer = TransactionSerializer(transaction)
        else:
            serializer = FXTransactionSerializer(transaction)

        processed_transactions.append(serializer.data)

    return processed_transactions
```

---

## Refactored Transaction Table API

### Location: `core/transactions_utils.py`

The `_calculate_transactions_table_output()` function was completely refactored to use the unified architecture:

#### Before (Duplicate Code)
```python
# ❌ OLD - Duplicate processing logic
def _process_regular_transaction(transaction):
    # Custom formatting logic - 50 lines
    # Custom balance calculation - 20 lines
    # Bond-specific handling - 15 lines
    # Currency formatting - 10 lines
    pass

def _process_fx_transaction(transaction):
    # Custom formatting logic - 40 lines
    # Custom balance calculation - 15 lines
    # Exchange rate formatting - 10 lines
    pass

# Total: ~160 lines of duplicate logic
```

#### After (DRY Implementation)
```python
# ✅ NEW - Unified processing
def _calculate_transactions_table_output(transactions, user, date, account_ids):
    # Initialize balance tracker
    tracker = BalanceTracker(number_of_digits=user.number_of_digits)
    tracker.set_initial_balances(get_initial_balances(user, date, account_ids))

    processed_transactions = []

    for transaction in transactions:
        # Update balances
        tracker.update(transaction)
        transaction._balances = tracker.get_balances_for_transaction(transaction.id)

        # Use appropriate serializer
        if transaction.__class__.__name__ == 'Transactions':
            serializer = TransactionSerializer(transaction)
        else:
            serializer = FXTransactionSerializer(transaction)

        processed_transactions.append(serializer.data)

    return {
        'transactions': processed_transactions,
        'currencies': list(tracker.balances.keys()),
        'total_items': len(transactions),
        'current_page': 1,
        'total_pages': math.ceil(len(transactions) / PAGE_SIZE)
    }

# Total: ~30 lines - eliminates ~130 lines of duplicate code
```

---

## Integration with Existing Components

### Balance Calculation Updates

#### Accounts.balance() Method
```python
# Before: Manual calculation
def balance(self, date, currency=None):
    # Manual calculation with effective_price * quantity - aci - cash_flow - commission
    # Complex logic prone to errors

# After: Centralized calculation
def balance(self, date, currency=None):
    total_balance = Decimal('0')

    for transaction in self.get_transactions_up_to(date):
        # Use centralized cash flow calculation
        cash_flow = transaction.get_calculated_cash_flow(target_currency=currency)
        total_balance += cash_flow

    return total_balance
```

### IRR Calculation Updates

#### Portfolio Utils _calculate_cash_flow()
```python
# Before: Complex conditional logic
def _calculate_cash_flow(transaction, investor):
    if transaction.type == 'Buy':
        return -transaction.quantity * transaction.price - transaction.commission
    elif transaction.type == 'Sell':
        return transaction.quantity * transaction.price - transaction.commission
    # ... 50+ lines of complex logic

# After: Centralized calculation
def _calculate_cash_flow(transaction, investor):
    # Use centralized method with sign adjustment for IRR
    cash_flow = transaction.get_calculated_cash_flow()

    # Adjust sign for IRR convention (negative = outflow, positive = inflow)
    if transaction.type in ['Buy', 'Cash Out']:
        return -abs(cash_flow)
    else:
        return abs(cash_flow)
```

---

## API Response Structure

### Main Transactions Table
```json
{
  "transactions": [
    {
      "id": "regular_123",
      "transaction_type": "regular",
      "date": "2024-01-15",
      "type": "Buy",
      "security": {
        "id": 45,
        "name": "Apple Inc.",
        "type": "Stock"
      },
      "instrument_type": "Stock",
      "quantity": "100",
      "price": "$150.25",
      "value": "$15,025.00",
      "cash_flow": "-$15,034.95",
      "commission": "-$9.95",
      "currency": "USD",
      "account": {
        "id": 1,
        "name": "Main Brokerage"
      },
      "balances": {
        "USD": "$84,965.05",
        "EUR": "€5,000.00"
      }
    },
    {
      "id": "fx_456",
      "transaction_type": "fx",
      "date": "2024-01-16",
      "type": "FX",
      "source_currency": "USD",
      "target_currency": "EUR",
      "source_amount": "-$1,000.00",
      "target_amount": "€920.50",
      "fx_rate": "0.9205",
      "account": {
        "id": 1,
        "name": "Main Brokerage"
      },
      "balances": {
        "USD": "$83,965.05",
        "EUR": "€5,920.50"
      }
    }
  ],
  "currencies": ["EUR", "USD"],
  "total_items": 145,
  "current_page": 1,
  "total_pages": 6
}
```

### Security Transactions
Uses the same `TransactionSerializer` but with `include_balances: false`:

```json
{
  "transactions": [
    {
      "id": "regular_123",
      "transaction_type": "regular",
      "date": "2024-01-15",
      "type": "Buy",
      "security": {
        "id": 45,
        "name": "Apple Inc.",
        "type": "Stock"
      },
      "instrument_type": "Stock",
      "quantity": "100",
      "price": "$150.25",
      "value": "$15,025.00",
      "cash_flow": "-$15,034.95",
      "commission": "-$9.95",
      "currency": "USD",
      "account": {
        "id": 1,
        "name": "Main Brokerage"
      }
    }
  ]
}
```

---

## Benefits of the Unified Architecture

### 1. **Consistency**
- All views (transaction table, security details, balance calculations) use the same logic
- Bond price formatting handled uniformly (percentage vs. actual price)
- ACI inclusion/exclusion consistent across all calculations

### 2. **Maintainability**
- Single place to update cash flow logic
- Changes automatically propagate to all views
- Serializers serve as the single source of truth for formatting

### 3. **Extensibility**
- Easy to add new transaction types
- BalanceTracker can be reused in new features
- Serializers can be extended with additional fields

### 4. **Bug Prevention**
- No more forgetting to update multiple places when adding ACI support
- Type-specific logic (bonds, derivatives) centralized
- Consistent rounding and formatting

---

## Migration Guide

### Step 1: Update Views to Use Centralized Methods

```python
# Old approach
def calculate_balance_old(transactions):
    balance = Decimal('0')
    for txn in transactions:
        if txn.type == 'Buy':
            balance -= txn.quantity * txn.price + txn.commission
        elif txn.type == 'Sell':
            balance += txn.quantity * txn.price - txn.commission
        # ... complex logic for each type
    return balance

# New approach
def calculate_balance_new(transactions):
    balance = Decimal('0')
    for txn in transactions:
        balance += txn.get_calculated_cash_flow()
    return balance
```

### Step 2: Replace Custom Formatting

```python
# Old approach
def format_transaction_old(transaction):
    if transaction.security.is_bond:
        price = f"{transaction.price}%"
    else:
        price = f"${transaction.price:.2f}"

    # Custom cash flow calculation
    if transaction.type == 'Buy':
        cash_flow = -transaction.quantity * transaction.price
    # ... etc

    return {
        'price': price,
        'cash_flow': f"${cash_flow:.2f}"
    }

# New approach
def format_transaction_new(transaction):
    serializer = TransactionSerializer(transaction)
    return serializer.data
```

### Step 3: Update Balance Tracking

```python
# Old approach
def track_balances_old(transactions):
    balances = {}
    for txn in transactions:
        # Manual balance calculation
        if txn.currency not in balances:
            balances[txn.currency] = Decimal('0')
        balances[txn.currency] += calculate_cash_flow_old(txn)
    return balances

# New approach
def track_balances_new(transactions):
    tracker = BalanceTracker()
    for txn in transactions:
        tracker.update(txn)
    return tracker.get_current_balances()
```

---

## Testing the Unified Architecture

### Unit Tests for Centralized Methods

```python
def test_get_calculated_cash_flow_buy():
    """Test cash flow calculation for buy transaction"""
    security = create_security(type='Stock')
    transaction = Transactions.objects.create(
        type='Buy',
        security=security,
        quantity=Decimal('100'),
        price=Decimal('150.25'),
        commission=Decimal('9.95')
    )

    expected = -(100 * 150.25 + 9.95)  # -15034.95
    actual = transaction.get_calculated_cash_flow()
    assert actual == expected

def test_get_calculated_cash_flow_bond():
    """Test cash flow calculation for bond with ACI"""
    bond = create_security(type='Bond')
    transaction = Transactions.objects.create(
        type='Buy',
        security=bond,
        quantity=Decimal('10'),
        price=Decimal('98.5'),  # 98.5% of par
        aci=Decimal('50.00'),   # Accrued interest
        commission=Decimal('10.00')
    )

    # Price should be converted using get_price()
    expected = -(10 * (98.5 * 1000 / 100) + 50 + 10)  # -(9850 + 50 + 10)
    actual = transaction.get_calculated_cash_flow()
    assert actual == expected
```

### Integration Tests for Serializers

```python
def test_transaction_serializer_bond():
    """Test that TransactionSerializer handles bonds correctly"""
    bond = create_security(type='Bond')
    transaction = Transactions.objects.create(
        type='Buy',
        security=bond,
        quantity=Decimal('10'),
        price=Decimal('98.5')
    )

    serializer = TransactionSerializer(transaction)
    data = serializer.data

    # Bond price should display as percentage
    assert data['price'] == '98.5%'
    assert data['instrument_type'] == 'Bond'
    assert data['transaction_type'] == 'regular'

def test_fx_transaction_serializer():
    """Test that FXTransactionSerializer handles FX correctly"""
    fx_transaction = FXTransaction.objects.create(
        from_amount=Decimal('1000'),
        to_amount=Decimal('920.50'),
        exchange_rate=Decimal('0.9205')
    )

    serializer = FXTransactionSerializer(fx_transaction)
    data = serializer.data

    assert data['transaction_type'] == 'fx'
    assert data['source_amount'] == '$1,000.00'
    assert data['target_amount'] == '€920.50'
    assert data['exchange_rate'] == '1:1.0865'  # Formatted for readability
```

### Regression Tests

```python
def test_balance_calculation_consistency():
    """Ensure all balance calculations give same results"""
    # Create test transactions
    transactions = create_test_transactions()

    # Calculate using old method
    old_balance = calculate_balance_old(transactions)

    # Calculate using new method
    new_balance = calculate_balance_new(transactions)

    # Results should be identical
    assert old_balance == new_balance
```

---

## Performance Considerations

### Database Query Optimization

```python
# Use select_related and prefetch_related to minimize queries
transactions = Transactions.objects.select_related(
    'security', 'account', 'investor'
).prefetch_related(
    'security__bondmetadata'
).filter(
    investor=user,
    date__lte=date
)

# Batch process transactions for large datasets
def process_transactions_batch(transactions, batch_size=1000):
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        yield process_transaction_batch(batch)
```

### Caching Strategy

```python
# Cache expensive calculations
@lru_cache(maxsize=1000)
def get_cached_cash_flow(transaction_id, target_currency=None):
    transaction = Transactions.objects.get(id=transaction_id)
    return transaction.get_calculated_cash_flow(target_currency)

# Cache balance snapshots
def cache_balances_for_user(user_id, date):
    cache_key = f"balances:{user_id}:{date}"
    cached = cache.get(cache_key)

    if cached:
        return cached

    balances = calculate_balances_for_user(user_id, date)
    cache.set(cache_key, balances, 3600)  # 1 hour

    return balances
```

---

## Common Issues & Solutions

### Issue 1: Inconsistent Bond Price Display
**Problem**: Bonds show as actual price in some views, percentage in others
**Solution**: Use `TransactionSerializer` which handles bond pricing consistently

### Issue 2: Balance Calculations Don't Match
**Problem**: Transaction table balances don't match account balance calculations
**Solution**: Both should use `get_calculated_cash_flow()` method

### Issue 3: Missing ACI in Some Views
**Problem**: Accrued interest included in some calculations but not others
**Solution**: Centralized in `get_calculated_cash_flow()` - automatically included for bonds

### Issue 4: FX Rate Formatting Inconsistency
**Problem**: Different formats for exchange rates across views
**Solution**: Use `FXTransactionSerializer` with consistent formatting

---

## Future Enhancements

### Short Term
1. **Transaction Type Interface**: Create abstract base class for transaction types
2. **Performance Optimization**: Bulk serialization for large datasets
3. **Validation Layer**: Add business logic validation to serializers
4. **Caching Layer**: Cache frequently accessed calculations

### Medium Term
1. **Advanced Balance Tracking**: Multi-period balance reconciliation
2. **Transaction Categories**: Enhanced categorization and filtering
3. **Audit Trail**: Track balance changes over time
4. **Reporting**: Built-in transaction analysis reports

### Long Term
1. **Real-time Updates**: WebSocket integration for live balance updates
2. **Machine Learning**: Anomaly detection in transaction patterns
3. **Advanced Analytics**: Portfolio performance attribution
4. **Multi-entity Support**: Support for complex entity structures

---

## References

- **Django REST Framework Serializers**: https://www.django-rest-framework.org/api-guide/serializers/
- **DRY Principle**: https://en.wikipedia.org/wiki/Don%27t_repeat_yourself
- **Financial Transaction Processing**: Standard industry patterns

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-05 | Initial transaction unification implementation |
| 1.1 | 2025-10-05 | Added BalanceTracker helper class |
| 1.2 | 2025-10-05 | Integrated with existing components (balance, IRR calculations) |
| 1.3 | 2025-10-05 | Complete documentation of patterns and migration guide |
