# Bond Amortization Support Guide

## Overview

This guide explains the new comprehensive bond tracking capabilities added to the portfolio management system, including support for amortizing bonds, partial redemptions, and accurate IRR calculations.

## Table of Contents

1. [Key Features](#key-features)
2. [New Transaction Types](#new-transaction-types)
3. [Bond Metadata](#bond-metadata)
4. [Notional Tracking](#notional-tracking)
5. [How It Works](#how-it-works)
6. [Migration Guide](#migration-guide)
7. [Usage Examples](#usage-examples)
8. [Future: Derivatives Support](#future-derivatives-support)

## Key Features

### 1. **Amortizing Bond Support**
- Track bonds with declining notional/principal values
- Separate tracking of principal redemptions vs. interest payments
- Accurate position and valuation calculations

### 2. **Correct IRR Calculations**
- Principal redemptions are treated as return of capital, not gains
- Proper cash flow categorization for IRR
- Accurate performance metrics for fixed income portfolios

### 3. **Partial Redemption Tracking**
- Record each partial redemption event
- Historical notional values at any point in time
- Distinction between partial redemptions and full maturity

### 4. **Extensible Framework**
- Foundation for options and futures (derivatives)
- Instrument-specific metadata architecture
- Scalable to other complex financial instruments

## New Transaction Types

### Bond Redemption
**Type:** `Bond redemption`
**Constant:** `TRANSACTION_TYPE_BOND_REDEMPTION`

Used for partial bond repayments where some of the principal is returned to the investor.

**Fields:**
- `quantity`: Negative value representing bonds redeemed
- `cash_flow`: Positive value representing cash received
- `notional_change`: The notional amount per bond that was redeemed
- `price`: Redemption price (typically par value = 100)

### Bond Maturity
**Type:** `Bond maturity`
**Constant:** `TRANSACTION_TYPE_BOND_MATURITY`

Used when a bond fully matures and all remaining principal is returned.

**Fields:** Same as Bond Redemption

## Bond Metadata

### BondMetadata Model

Store bond-specific information:

```python
from common.models import Assets, BondMetadata

# For a bond asset
bond = Assets.objects.get(ISIN="US912828...")

# Create or update bond metadata
bond_meta, created = BondMetadata.objects.get_or_create(
    asset=bond,
    defaults={
        'initial_notional': Decimal('1000.00'),  # $1000 par value
        'issue_date': date(2020, 1, 1),
        'maturity_date': date(2030, 1, 1),
        'coupon_rate': Decimal('5.25'),  # 5.25% annual
        'coupon_frequency': 2,  # Semi-annual payments
        'is_amortizing': True,
        'bond_type': 'FIXED',
        'credit_rating': 'AAA'
    }
)
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `initial_notional` | Decimal | Initial par/face value per bond |
| `issue_date` | Date | Bond issue date |
| `maturity_date` | Date | Bond maturity date |
| `coupon_rate` | Decimal | Annual coupon rate (e.g., 5.25 for 5.25%) |
| `coupon_frequency` | Integer | Payments per year (1=annual, 2=semi-annual, 4=quarterly) |
| `is_amortizing` | Boolean | Whether principal amortizes |
| `bond_type` | Choice | FIXED, FLOATING, ZERO_COUPON, INFLATION_LINKED, CONVERTIBLE |
| `credit_rating` | String | Credit rating (AAA, BB+, etc.) |

## Notional Tracking

### NotionalHistory Model

Track how notional values change over time:

```python
from common.models import NotionalHistory

# Record a partial redemption
NotionalHistory.objects.create(
    asset=bond,
    date=date(2025, 6, 1),
    notional_per_unit=Decimal('800.00'),  # Reduced from $1000 to $800
    change_amount=Decimal('-200.00'),  # $200 redeemed
    change_reason='REDEMPTION',
    comment='First scheduled amortization payment'
)
```

### Change Reasons

- `INITIAL`: Initial bond issuance
- `REDEMPTION`: Partial redemption/amortization
- `MATURITY`: Full maturity
- `ADJUSTMENT`: Manual adjustment

## How It Works

### 1. Buy a Bond

```python
# Standard bond purchase
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Buy',
    date=date(2024, 1, 1),
    quantity=Decimal('10'),  # 10 bonds
    price=Decimal('100'),  # At par
    currency='USD'
)
```

### 2. Receive Coupons

```python
# Coupon payment (unchanged)
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Coupon',
    date=date(2024, 6, 1),
    cash_flow=Decimal('262.50'),  # $1000 * 10 bonds * 5.25% / 2
    currency='USD'
)
```

### 3. Partial Redemption

```python
# Partial bond redemption
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Bond redemption',
    date=date(2025, 1, 1),
    quantity=Decimal('-10'),  # All 10 bonds partially redeemed
    cash_flow=Decimal('2000.00'),  # $200 per bond * 10 bonds
    notional_change=Decimal('200.00'),  # $200 per bond redeemed
    price=Decimal('100'),  # Redemption at par
    currency='USD'
)

# Update notional history
NotionalHistory.objects.create(
    asset=bond,
    date=date(2025, 1, 1),
    notional_per_unit=Decimal('800.00'),  # Now $800 per bond
    change_amount=Decimal('-200.00'),
    change_reason='REDEMPTION'
)
```

### 4. Final Maturity

```python
# Bond maturity - return of remaining principal
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Bond maturity',
    date=date(2030, 1, 1),
    quantity=Decimal('-10'),  # Close out position
    cash_flow=Decimal('8000.00'),  # $800 remaining * 10 bonds
    notional_change=Decimal('800.00'),  # Final $800 per bond
    price=Decimal('100'),
    currency='USD'
)
```

### Key Calculation Updates

#### Position Calculation
- For non-amortizing bonds: Standard quantity-based
- For amortizing bonds: Quantity * current notional per unit

#### Buy-in Price
- Accounts for notional changes when calculating weighted average
- Uses effective notional at each transaction date

#### Realized Gain/Loss
- **Regular sales**: Gain = (Sell Price - Buy Price) × Quantity
- **Redemptions**: Gain = (Redemption Price - Buy Price) × Quantity
  - Typically zero if redeemed at par and bought at par
  - Can be gain/loss if bought at premium/discount

#### IRR Calculation
- **Buys**: Cash outflow (negative)
- **Coupons**: Cash inflow (positive)
- **Redemptions**: Cash inflow (positive) - treated as return of capital
- **Sales**: Net cash flow based on transaction

## Migration Guide

### Step 1: Run Migration

```bash
cd portfolio_management
python manage.py migrate common 0064
```

### Step 2: Add Bond Metadata for Existing Bonds

```python
from common.models import Assets, BondMetadata

# Identify your bonds
bonds = Assets.objects.filter(type='Bond')

for bond in bonds:
    # Create metadata for each bond
    BondMetadata.objects.get_or_create(
        asset=bond,
        defaults={
            'initial_notional': Decimal('1000.00'),  # Adjust as needed
            'is_amortizing': False,  # Set True if amortizing
            # ... other fields
        }
    )
```

### Step 3: Update Existing Redemption Transactions

If you have historical bond redemptions recorded as "Sell" transactions:

```python
from common.models import Transactions

# Find redemption transactions (you may need custom logic)
redemptions = Transactions.objects.filter(
    security__type='Bond',
    type='Sell',
    # Add your criteria for identifying redemptions
)

for txn in redemptions:
    # Update to new transaction type
    txn.type = 'Bond redemption'
    # Add notional change if known
    txn.notional_change = Decimal('100.00')  # Or actual value
    txn.save()
```

## Usage Examples

### Example 1: Simple Bullet Bond (Non-Amortizing)

```python
# Create bond
bond = Assets.objects.create(
    name='US Treasury 5% 2030',
    type='Bond',
    ISIN='US912828ABC1',
    currency='USD'
)

# Add metadata
BondMetadata.objects.create(
    asset=bond,
    initial_notional=Decimal('1000.00'),
    maturity_date=date(2030, 1, 15),
    coupon_rate=Decimal('5.00'),
    coupon_frequency=2,
    is_amortizing=False,  # Bullet bond
    bond_type='FIXED'
)

# Buy 100 bonds
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Buy',
    date=date(2024, 1, 15),
    quantity=Decimal('100'),
    price=Decimal('98.50'),  # Below par
    currency='USD'
)

# Receive semi-annual coupon
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Coupon',
    date=date(2024, 7, 15),
    cash_flow=Decimal('2500.00'),  # $1000 * 100 * 5% / 2
    currency='USD'
)

# At maturity
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type='Bond maturity',
    date=date(2030, 1, 15),
    quantity=Decimal('-100'),
    cash_flow=Decimal('100000.00'),  # $1000 * 100
    price=Decimal('100'),  # Par value
    currency='USD'
)
```

### Example 2: Amortizing Bond

```python
# Create amortizing bond
amortizing_bond = Assets.objects.create(
    name='Mortgage Bond 2025-2035',
    type='Bond',
    ISIN='US123456789',
    currency='USD'
)

# Add metadata with amortization
BondMetadata.objects.create(
    asset=amortizing_bond,
    initial_notional=Decimal('1000.00'),
    maturity_date=date(2035, 12, 31),
    coupon_rate=Decimal('4.50'),
    coupon_frequency=4,  # Quarterly
    is_amortizing=True,
    bond_type='FIXED'
)

# Buy 50 bonds
Transactions.objects.create(
    investor=user,
    account=account,
    security=amortizing_bond,
    type='Buy',
    date=date(2025, 1, 1),
    quantity=Decimal('50'),
    price=Decimal('100'),
    currency='USD'
)

# Quarterly: Coupon + Partial Redemption
# Q1 2025 - Coupon
Transactions.objects.create(
    investor=user,
    account=account,
    security=amortizing_bond,
    type='Coupon',
    date=date(2025, 3, 31),
    cash_flow=Decimal('562.50'),  # $1000 * 50 * 4.5% / 4
    currency='USD'
)

# Q1 2025 - Partial Redemption
Transactions.objects.create(
    investor=user,
    account=account,
    security=amortizing_bond,
    type='Bond redemption',
    date=date(2025, 3, 31),
    quantity=Decimal('-50'),  # All bonds partially redeemed
    cash_flow=Decimal('2500.00'),  # $50 per bond * 50 bonds
    notional_change=Decimal('50.00'),
    price=Decimal('100'),
    currency='USD'
)

NotionalHistory.objects.create(
    asset=amortizing_bond,
    date=date(2025, 3, 31),
    notional_per_unit=Decimal('950.00'),  # $1000 - $50
    change_amount=Decimal('-50.00'),
    change_reason='REDEMPTION'
)

# Continue with subsequent quarters...
```

### Example 3: Calculating IRR with Redemptions

```python
from core.portfolio_utils import IRR

# Calculate IRR for amortizing bond position
irr_result = IRR(
    user_id=user.id,
    date=date(2026, 12, 31),
    currency='USD',
    asset_id=amortizing_bond.id,
    account_ids=[account.id]
)

print(f"IRR: {irr_result * 100:.2f}%")
# IRR calculation now correctly treats redemptions as return of capital
```

## Future: Derivatives Support

The framework now includes extensible metadata models for:

### Options (OptionMetadata)
- Strike price
- Expiration date
- Option type (Call/Put)
- Underlying asset reference
- Contract size

### Futures (FutureMetadata)
- Expiration date
- Underlying asset reference
- Contract size
- Tick size
- Initial margin requirements

These models are ready for implementation as you expand derivative support.

## Best Practices

1. **Always set bond metadata** for bonds in your portfolio
2. **Mark amortizing bonds** with `is_amortizing=True`
3. **Record notional changes** in NotionalHistory for accurate tracking
4. **Use correct transaction types**:
   - Use "Buy"/"Sell" for market transactions
   - Use "Bond redemption" for partial repayments
   - Use "Bond maturity" for final maturity
5. **Set notional_change** for redemption transactions
6. **Keep coupon transactions separate** from principal repayments

## Troubleshooting

### IRR Calculation Issues
- Ensure `notional_change` is set for redemption transactions
- Check that transaction types are correct
- Verify cash_flow values match actual cash received

### Position Calculation Issues
- For amortizing bonds, ensure BondMetadata has `is_amortizing=True`
- Verify NotionalHistory entries are created for each redemption
- Check that quantity and notional_change values are consistent

### Migration Issues
- If migration fails, check database connection
- Ensure all dependencies (0063) are applied
- Review any custom model changes that might conflict

## Support

For questions or issues:
1. Check the test files in `portfolio_management/tests/`
2. Review transaction examples in the database
3. Examine the model methods in `common/models.py`

## Changelog

**Version 1.0** (October 2025)
- Initial bond amortization support
- New transaction types (Bond redemption, Bond maturity)
- BondMetadata, NotionalHistory models
- Updated IRR calculations
- Foundation for derivatives (options, futures)
- T-Bank API integration for bond redemptions
