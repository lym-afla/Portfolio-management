# Bond Amortization Domain Knowledge

## Overview

This document captures the domain knowledge and architectural patterns for bond amortization support in the portfolio management system. It covers the business logic, data models, and calculation methods required for accurate bond portfolio management.

---

## Bond Types & Characteristics

### Bullet Bonds (Non-Amortizing)
- **Description**: Traditional bonds that pay full principal at maturity
- **Cash Flow Pattern**: Regular coupon payments + lump sum principal at maturity
- **Notional Tracking**: Notional remains constant throughout bond life
- **Examples**: Government bonds, corporate bonds

### Amortizing Bonds
- **Description**: Bonds that return principal gradually over time
- **Cash Flow Pattern**: Regular coupon payments + scheduled principal repayments
- **Notional Tracking**: Notional decreases with each principal repayment
- **Examples**: Mortgage-backed securities, structured bonds, some corporate bonds

### Key Distinction
**Bullet Bonds**: Position value = `quantity × current_price × notional`
**Amortizing Bonds**: Position value = `quantity × current_price × current_notional_per_unit`

---

## Data Model Architecture

### Core Models

#### BondMetadata Model
```python
class BondMetadata(models.Model):
    asset = models.OneToOneField(Assets, on_delete=models.CASCADE)
    initial_notional = models.DecimalField(max_digits=20, decimal_places=9)
    issue_date = models.DateField()
    maturity_date = models.DateField()
    coupon_rate = models.DecimalField(max_digits=10, decimal_places=6)
    coupon_frequency = models.IntegerField()  # 1=annual, 2=semi-annual, 4=quarterly
    is_amortizing = models.BooleanField(default=False)
    bond_type = models.CharField(max_length=20, choices=BOND_TYPE_CHOICES)
    credit_rating = models.CharField(max_length=10, blank=True)
```

#### NotionalHistory Model
```python
class NotionalHistory(models.Model):
    asset = models.ForeignKey(Assets, on_delete=models.CASCADE)
    date = models.DateField()
    notional_per_unit = models.DecimalField(max_digits=20, decimal_places=9)
    change_amount = models.DecimalField(max_digits=20, decimal_places=9)
    change_reason = models.CharField(max_length=20, choices=CHANGE_REASON_CHOICES)
    comment = models.TextField(blank=True)
```

### New Transaction Types

#### Bond Redemption
- **Type**: `Bond redemption`
- **Use Case**: Partial principal repayment
- **Key Fields**:
  - `quantity`: Number of bonds affected (negative for redemption)
  - `cash_flow`: Cash received from redemption
  - `notional_change`: Principal amount redeemed per bond
  - `price`: Redemption price (typically par = 100)

#### Bond Maturity
- **Type**: `Bond maturity`
- **Use Case**: Final principal repayment at bond end
- **Key Fields**: Same as Bond Redemption
- **Distinction**: Closes out position entirely

---

## Calculation Patterns

### Position Calculations

#### Standard (Bullet) Bonds
```python
def position_value(self, date, investor, account_ids=None):
    quantity = self.position(date, investor, account_ids)
    price = self.price_at_date(date)
    return quantity * price.price if price else Decimal(0)
```

#### Amortizing Bonds
```python
def position_value(self, date, investor, account_ids=None):
    quantity = self.position(date, investor, account_ids)
    if self.is_bond and self.bond_metadata.is_amortizing:
        # Get current notional from history
        current_notional = self.get_current_notional(date, investor, account_ids)
        price = self.price_at_date(date)
        return quantity * (price.price / Decimal('100')) * current_notional
    else:
        # Standard calculation for non-amortizing
        price = self.price_at_date(date)
        return quantity * price.price if price else Decimal(0)
```

### Current Notional Calculation
```python
def get_current_notional(self, date, investor, account_ids=None):
    if not self.is_bond or not self.bond_metadata.is_amortizing:
        return self.bond_metadata.initial_notional

    # Get most recent notional history entry
    latest_history = NotionalHistory.objects.filter(
        asset=self,
        date__lte=date,
        change_reason__in=['INITIAL', 'REDEMPTION', 'MATURITY']
    ).order_by('-date').first()

    if latest_history:
        return latest_history.notional_per_unit
    else:
        return self.bond_metadata.initial_notional
```

### Realized Gain/Loss Calculations

#### Regular Sales
```python
# Standard G/L: (Sell Price - Buy Price) × Quantity
gain_loss = (sell_price - buy_in_price) * quantity_sold
```

#### Bond Redemptions
```python
# Redemption G/L: (Redemption Price - Buy Price) × Quantity
gain_loss = (redemption_price - buy_in_price) * quantity

# Note: Typically zero if redeemed at par and bought at par
# Can be gain/loss if bought at premium/discount
```

#### Buy-in Price for Amortizing Bonds
```python
def calculate_buy_in_price(self, date, investor, account_ids=None):
    transactions = self.get_transactions_up_to(date, investor, account_ids)

    if not self.bond_metadata.is_amortizing:
        # Standard calculation
        total_cost = sum(txn.quantity * txn.price for txn in buys)
        total_quantity = sum(txn.quantity for txn in buys)
        return total_cost / total_quantity if total_quantity else Decimal(0)

    # Amortizing bonds: weighted by notional at each transaction date
    weighted_cost = Decimal(0)
    total_notional = Decimal(0)

    for txn in buys:
        # Get notional at transaction date
        notional_at_date = self.get_current_notional(txn.date, investor, account_ids)

        # Weight by notional × quantity
        weight = notional_at_date * txn.quantity
        weighted_cost += txn.price * weight
        total_notional += weight

    return weighted_cost / total_notional if total_notional else Decimal(0)
```

### IRR Cash Flow Treatment

#### Cash Flow Classification
```python
def _calculate_cash_flow(self, transaction, investor):
    if transaction.type == 'Buy':
        return -transaction.total_cash_flow()  # Outflow
    elif transaction.type == 'Sell':
        return transaction.total_cash_flow()   # Inflow
    elif transaction.type == 'Coupon':
        return transaction.cash_flow                    # Inflow
    elif transaction.type in ['Bond redemption', 'Bond maturity']:
        return transaction.cash_flow                    # Inflow (return of capital)
    elif transaction.type in ['Cash In', 'Cash Out']:
        return -transaction.cash_flow                   # Outflow
```

#### Key Principle
- **Redemptions** are treated as **return of capital**, not gains
- **True returns** come from coupons (separate transactions)
- **IRR calculation** reflects this by including redemption cash flows positively

---

## T-Bank API Integration

### Special Handling: Quantity=0 Issue

T-Bank API returns bond redemption operations with **`quantity=0`**:

```python
# T-Bank API response for amortizing bond redemption
OperationItem(
    type=OperationType.OPERATION_TYPE_BOND_REPAYMENT,
    payment=MoneyValue(currency='rub', units=6250, nano=0),
    quantity=0,  # ← Key issue: bonds don't change in quantity
)
```

### Why Quantity is Zero

For amortizing bonds:
- **Number of bonds held** doesn't change during redemption
- **Face value per bond** decreases instead
- **Cash received** represents notional that was redeemed

### Implementation Solution
```python
# In map_tinkoff_operation_to_transaction()
if operation.type in [
    OperationType.OPERATION_TYPE_BOND_REPAYMENT,
    OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL,
]:
    # T-Bank API returns quantity=0 for bond redemptions
    # The actual redemption info is in the payment field

    if operation.payment:
        cash_received = quotation_to_decimal(operation.payment)
        transaction_data["cash_flow"] = cash_received
        transaction_data["notional_change"] = cash_received

    # Set quantity to None (bonds held doesn't change)
    transaction_data["quantity"] = None
    transaction_data["price"] = None
```

### Per-Bond Notional Calculation

Since T-Bank provides total cash received, we need to calculate per-bond notional:

```python
# During import process
total_notional = 6250  # From T-Bank
position = security.position(date, user, [account.id])  # 10 bonds
notional_per_bond = 6250 / 10 = 625 RUB per bond
```

---

## Workflow Examples

### Complete Amortizing Bond Lifecycle

#### 1. Bond Purchase
```python
# Buy 10 amortizing bonds at par
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Buy',
    date='2024-01-01',
    quantity=Decimal('10'),
    price=Decimal('100'),  # At par
    currency='USD'
)

# Initialize notional history
NotionalHistory.objects.create(
    asset=bond,
    date='2024-01-01',
    notional_per_unit=Decimal('1000.00'),  # Initial notional
    change_amount=Decimal('1000.00'),
    change_reason='INITIAL'
)
```

#### 2. Coupon Payment
```python
# Semi-annual coupon payment
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Coupon',
    date='2024-07-01',
    cash_flow=Decimal('250.00'),  # $1000 * 10 * 5% / 2
    currency='USD'
)
```

#### 3. Partial Redemption
```python
# First principal repayment
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Bond redemption',
    date='2024-07-01',
    quantity=Decimal('-10'),     # All bonds partially redeemed
    cash_flow=Decimal('500.00'), # $50 per bond * 10 bonds
    notional_change=Decimal('50.00'),  # $50 per bond redeemed
    price=Decimal('100'),        # Redemption at par
    currency='USD'
)

# Update notional history
NotionalHistory.objects.create(
    asset=bond,
    date='2024-07-01',
    notional_per_unit=Decimal('950.00'),  # Reduced from $1000 to $950
    change_amount=Decimal('-50.00'),
    change_reason='REDEMPTION'
)
```

#### 4. Final Maturity
```python
# Bond maturity - remaining principal
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Bond maturity',
    date='2030-01-01',
    quantity=Decimal('-10'),     # Close out position
    cash_flow=Decimal('9500.00'), # $950 remaining * 10 bonds
    notional_change=Decimal('950.00'),  # Final $950 per bond
    price=Decimal('100'),
    currency='USD'
)
```

### IRR Calculation Example

```python
# Calculate IRR for the amortizing bond position
irr_result = IRR(
    user_id=user.id,
    date='2025-12-31',
    currency='USD',
    asset_id=bond.id,
    account_ids=[account.id]
)

# Expected cash flows:
# 2024-01-01: -$10,000 (initial purchase)
# 2024-07-01: +$250 (coupon)
# 2024-07-01: +$500 (partial redemption - return of capital)
# 2025-01-01: +$237.50 (coupon on $950 notional)
# 2025-01-01: +$500 (partial redemption)
# ... and so on
```

---

## Migration & Data Management

### Migration Strategy

#### Step 1: Schema Migration
```bash
python manage.py migrate common 0064_add_bond_support_and_derivatives
```

#### Step 2: Backfill Bond Metadata
```python
# Create metadata for existing bonds
bonds = Assets.objects.filter(type='Bond')

for bond in bonds:
    BondMetadata.objects.get_or_create(
        asset=bond,
        defaults={
            'initial_notional': Decimal('1000.00'),
            'is_amortizing': False,  # Default to bullet bonds
            'maturity_date': None,   # Set if known
            'coupon_rate': Decimal('0'),
            'coupon_frequency': 2,
            'bond_type': 'FIXED'
        }
    )
```

#### Step 3: Convert Historical Redemptions
```python
# Find bond redemptions recorded as "Sell"
redemptions = Transactions.objects.filter(
    security__type='Bond',
    type='Sell',
    # Add business logic to identify actual redemptions
)

for txn in redemptions:
    txn.type = 'Bond redemption'
    txn.notional_change = calculate_per_bond_notional(txn)
    txn.save()
```

### Data Validation Rules

#### Consistency Checks
```python
def validate_bond_data(bond):
    """Validate bond metadata and transaction consistency"""
    errors = []

    # Check metadata exists
    if not hasattr(bond, 'bondmetadata'):
        errors.append("Missing BondMetadata")
        return errors

    # Check amortizing bonds have notional history
    if bond.bond_metadata.is_amortizing:
        history_count = NotionalHistory.objects.filter(asset=bond).count()
        if history_count == 0:
            errors.append("Amortizing bond missing NotionalHistory")

    # Check transaction types
    redemptions = Transactions.objects.filter(
        security=bond,
        type__in=['Bond redemption', 'Bond maturity']
    )

    for redemption in redemptions:
        if redemption.notional_change is None:
            errors.append(f"Redemption {redemption.id} missing notional_change")

    return errors
```

---

## Testing Requirements

### Unit Tests

#### Bond Metadata Operations
```python
def test_bond_metadata_creation():
    bond = Assets.objects.create(name="Test Bond", type="Bond")
    metadata = BondMetadata.objects.create(
        asset=bond,
        initial_notional=Decimal('1000'),
        is_amortizing=True
    )
    assert metadata.asset == bond
    assert metadata.is_amortizing == True
```

#### Notional Tracking
```python
def test_notional_history_tracking():
    # Create bond with initial notional
    # Add redemption transaction
    # Verify notional history is updated correctly
    pass
```

#### IRR with Amortization
```python
def test_irr_amortizing_bond():
    # Create amortizing bond position
    # Add buy, coupon, and redemption transactions
    # Calculate IRR
    # Verify result is reasonable
    pass
```

### Integration Tests

#### T-Bank API Import
```python
def test_tbank_amortizing_bond_import():
    # Mock T-Bank response with quantity=0
    # Import transaction
    # Verify correct transaction type and notional_change
    pass
```

#### Performance Calculations
```python
def test_performance_with_amortizing_bonds():
    # Create portfolio with amortizing bonds
    # Calculate portfolio performance
    # Verify position values and returns are correct
    pass
```

---

## Common Issues & Solutions

### Issue 1: Notional Calculation Inconsistency
**Problem**: Per-bond notional doesn't match historical transactions
**Solution**: Use `position()` method to get bond count at redemption date

### Issue 2: IRR Changes Unexpectedly
**Problem**: IRR values change after implementing amortization
**Explanation**: Expected! Redemptions now correctly treated as return of capital
**Solution**: Review calculations manually to verify they're now correct

### Issue 3: Position Value Wrong
**Problem**: Position value doesn't account for reduced notional
**Solution**: Implement notional-aware position calculation for amortizing bonds

### Issue 4: Missing NotionalHistory
**Problem**: Automatic NotionalHistory creation fails
**Solution**: Manual calculation based on position and redemption amount

---

## Future Enhancements

### Short Term
1. **Admin Interface**: Bond metadata management UI
2. **Bulk Import Tool**: Historical bond data import
3. **Validation Rules**: Automated data consistency checks
4. **Reports**: Fixed income portfolio analytics

### Medium Term
1. **Automated Scheduling**: Generate amortization schedules
2. **Yield Calculations**: YTM, YTC, BEY calculations
3. **Duration Metrics**: Modified duration, convexity
4. **Credit Analysis**: Rating tracking and alerts

### Long Term
1. **Complex Instruments**: CMOs, ABS, structured products
2. **Scenario Analysis**: Interest rate stress testing
3. **Optimization**: Portfolio construction for fixed income
4. **Risk Metrics**: VaR, concentration limits for bonds

---

## References

- **Investopedia - Amortizing Bonds**: https://www.investopedia.com/terms/a/amortizingbond.asp
- **Fixed Income Mathematics**: Standard bond calculation formulas
- **T-Bank API Documentation**: Operation types and data structures

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-02 | Initial bond amortization support implementation |
| 1.1 | 2025-10-02 | T-Bank API integration with quantity=0 handling |
| 1.2 | 2025-10-02 | Automatic NotionalHistory creation |
