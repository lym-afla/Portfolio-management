# Bond Pricing: Percentage Basis Approach

## Overview

This document describes the consistent approach to handling bond pricing and gain/loss calculations where **all prices remain in percentage terms** (basis) throughout the system, and notional values are applied only in the final gain/loss calculations.

## Core Principle

**Keep prices as percentages, apply notional at calculation time.**

### Price Storage & Retrieval
- **Database (Prices table)**: Store as percentage of par (e.g., 98.5 = 98.5%)
- **Transactions.price**: Store as percentage of par (e.g., 100 = 100%)
- **`price_at_date()`**: Returns percentage of par
- **`calculate_buy_in_price()`**: Returns percentage of par

### Gain/Loss Calculations
Apply notional only when calculating the actual monetary gain/loss amounts.

## Formulas

### 1. Unrealized Gain/Loss

**For bonds:**
```
Unrealized G/L = notional_at_date × (price_at_date% - buy_in_price%) × position / 100
```

**For other assets:**
```
Unrealized G/L = (current_price - buy_in_price) × position
```

**Example:**
- Position: 50 bonds
- Notional at date: 1000 RUB
- Current price: 100% (stored as 100)
- Buy-in price: 98.5% (stored as 98.5)

```
Unrealized G/L = 1000 × (100 - 98.5) × 50 / 100
              = 1000 × 1.5 × 50 / 100
              = 750 RUB
```

### 2. Realized Gain/Loss - Two Components

#### A. From Actual Sale
```
Sale G/L = notional_at_sell_date × (sale_price% - buy_in_price%) × quantity_sold / 100
```

**Example:**
- Sold: 10 bonds
- Notional at sale: 1000 RUB
- Sale price: 102% (stored as 102)
- Buy-in price: 98.5% (stored as 98.5)

```
Sale G/L = 1000 × (102 - 98.5) × 10 / 100
        = 1000 × 3.5 × 10 / 100
        = 350 RUB
```

#### B. From Redemption (Partial or Full)
```
Redemption G/L = notional_redeemed × quantity × (100 - buy_in_price%) / 100
```

**Example:**
- Redemption: 5 bonds
- Notional redeemed: 200 RUB per bond
- Buy-in price: 98.5% (stored as 98.5)

```
Redemption G/L = 200 × 5 × (100 - 98.5) / 100
               = 200 × 5 × 1.5 / 100
               = 15 RUB
```

**Note:** Redemptions always occur at par (100% of notional), so the gain is based on the difference between 100 and the buy-in price percentage.

### 3. Market Value
```
Market Value = position × price% × notional / 100
```

**Example:**
- Position: 50 bonds
- Price: 100% (stored as 100)
- Notional: 1000 RUB

```
Market Value = 50 × 100 × 1000 / 100
            = 50,000 RUB
```

## Implementation Details

### 1. `calculate_buy_in_price()` Method
**Location:** `common/models.py`, lines 541-555

**Changes:**
- Uses `transaction.price` directly (not `transaction.get_price()`)
- Returns percentage of par for bonds
- Returns actual price for other assets

```python
# Use price as-is (percentage for bonds, actual for others)
current_price = transaction.price * fx_rate
weight_current = transaction.quantity
```

### 2. `price_at_date()` Method
**Location:** `common/models.py`, lines 310-343

**No changes needed:**
- Already returns `transaction.price` when falling back to transactions
- Returns percentage from Prices table for bonds
- Consistently returns percentage of par

### 3. `calculate_value_at_date()` Method
**Location:** `common/models.py`, lines 345-388

**Changes:**
- For bonds: `value = position × price% × notional / 100`
- For others: `value = position × price`

```python
if self.is_bond:
    effective_notional = self.get_effective_notional(date, investor, account_ids, currency)
    value = position * price * effective_notional / Decimal(100)
else:
    value = position * price
```

### 4. `unrealized_gain_loss()` Method
**Location:** `common/models.py`, lines 826-898

**Changes:**
- For bonds: Apply notional in the calculation
- Formula: `notional × (current_price% - buy_in_price%) × position / 100`

```python
if self.is_bond:
    notional_lcl = self.get_effective_notional(date, investor, account_ids, None)
    notional_target = self.get_effective_notional(date, investor, account_ids, currency)

    price_appreciation = (
        notional_lcl * (current_price_in_lcl_cur - buy_in_price_in_lcl_cur)
        * current_position * fx_rate_eop / Decimal(100)
    )
    unrealized_gain_loss = (
        notional_target * (current_price_in_target_cur - buy_in_price_in_target_cur)
        * current_position / Decimal(100)
    )
```

### 5. `realized_gain_loss()` Method
**Location:** `common/models.py`, lines 606-760

**Changes:**

#### For Sales (lines 716-748):
```python
if self.is_bond:
    notional_at_sell = self.get_effective_notional(
        transaction.date, investor, account_ids, transaction.currency
    )

    # Prices are in percentage terms
    price_appreciation_lcl = (
        notional_at_sell * (transaction.price - buy_in_price_lcl_currency)
        * (-transaction.quantity) / Decimal(100)
    )
    price_appreciation = price_appreciation_lcl * fx_rate_exit

    notional_at_sell_target = self.get_effective_notional(
        transaction.date, investor, account_ids, currency
    )
    gl_target_currency = (
        notional_at_sell_target * (transaction.price * fx_rate_exit - buy_in_price_target_currency)
        * (-transaction.quantity) / Decimal(100)
    )
```

#### For Redemptions (lines 651-677):
```python
# Redemption G/L = notional_redeemed × quantity × (100 - buy_in_price%)
quantity_redeemed = abs(transaction.quantity) if transaction.quantity else Decimal(1)

# Price appreciation in local currency (100 = 100% of par = redemption at par)
price_appreciation_lcl = (
    notional_redeemed * quantity_redeemed * (Decimal(100) - buy_in_price_lcl_currency) / Decimal(100)
)
price_appreciation = price_appreciation_lcl * fx_rate_exit

# Total G/L in target currency
gl_target_currency = (
    notional_redeemed * quantity_redeemed * (Decimal(100) - buy_in_price_target_currency) / Decimal(100)
)
```

## Benefits of This Approach

1. **Consistency**: All prices are in the same unit (percentage) throughout the system
2. **Clarity**: Separation between price (percentage) and notional (currency amount)
3. **Accuracy**: Notional changes over time are properly accounted for in calculations
4. **Standard Practice**: Bond markets quote prices as percentages of par
5. **Simplicity**: Price comparison doesn't require conversion

## Example Workflow

### Bond Purchase
1. **Transaction created**: price = 98.5 (98.5% of par)
2. **Stored in DB**: 98.5
3. **Buy-in price**: 98.5

### Price Update
1. **Market price**: 100 (100% of par)
2. **Stored in Prices**: 100
3. **`price_at_date()` returns**: 100

### Unrealized G/L Calculation
1. **Current price**: 100 (from `price_at_date()`)
2. **Buy-in price**: 98.5 (from `calculate_buy_in_price()`)
3. **Notional**: 1000 RUB (from bond metadata)
4. **Position**: 50 bonds
5. **Calculation**: 1000 × (100 - 98.5) × 50 / 100 = **750 RUB** ✓

### Bond Sale
1. **Sale price**: 102 (102% of par)
2. **Buy-in price**: 98.5
3. **Notional at sale**: 1000 RUB
4. **Quantity sold**: 10 bonds
5. **Calculation**: 1000 × (102 - 98.5) × 10 / 100 = **350 RUB** ✓

### Bond Redemption
1. **Notional redeemed**: 200 RUB per bond
2. **Buy-in price**: 98.5
3. **Quantity**: 5 bonds
4. **Calculation**: 200 × 5 × (100 - 98.5) / 100 = **15 RUB** ✓

## Testing Checklist

- [ ] Verify buy-in price is in percentage terms (e.g., 98.5, not 985)
- [ ] Verify current price is in percentage terms (e.g., 100, not 1000)
- [ ] Check unrealized G/L calculation with sample bonds
- [ ] Test realized G/L from bond sale
- [ ] Test realized G/L from bond redemption
- [ ] Verify market value calculation
- [ ] Test with amortizing bonds (changing notional)
- [ ] Verify FX conversions work correctly

## Migration Notes

**No database migration needed** - this is purely a calculation change.

However, ensure:
1. Existing bond prices in Prices table are stored as percentages
2. Existing transactions have prices as percentages
3. BondMetadata records have `initial_notional` set correctly

## Summary

| Component | Storage Format | Calculation Format |
|-----------|---------------|-------------------|
| Prices table | Percentage | Percentage |
| Transactions.price | Percentage | Percentage |
| `price_at_date()` | - | Returns Percentage |
| `calculate_buy_in_price()` | - | Returns Percentage |
| Unrealized G/L | - | Percentage × Notional |
| Realized G/L | - | Percentage × Notional |
| Market Value | - | Percentage × Notional |

---

**Status:** ✅ Complete
**Date:** October 4, 2025
**Impact:** High - establishes consistent bond pricing methodology
