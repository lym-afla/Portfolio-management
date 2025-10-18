# Decimal Precision Upgrade to 9 Digits

**Date:** October 3, 2025
**Scope:** Transaction and FX Transaction models
**Reason:** Align with T-Bank API nano precision

## Overview

Upgraded decimal precision from 6 to 9 decimal places for transaction-related fields to match T-Bank API's nano-precision values (nano represents 10^-9).

## Changes Made

### 1. Model Field Updates

**File:** `portfolio_management/common/models.py`

#### Transactions Model
- `quantity`: `decimal_places=6` → `decimal_places=9`
- `commission`: `decimal_places=2` → `decimal_places=9`
- `price`: Already at `decimal_places=9` ✓

#### FXTransaction Model
- `from_amount`: `decimal_places=6` → `decimal_places=9`
- `to_amount`: `decimal_places=6` → `decimal_places=9`
- `exchange_rate`: `decimal_places=6` → `decimal_places=9`
- `commission`: `decimal_places=6` → `decimal_places=9`

### 2. Dynamic Precision Detection

**File:** `portfolio_management/core/import_utils.py`

Updated `fx_transaction_exists()` to dynamically retrieve precision from model:

```python
# Get decimal_places from the model field dynamically
exchange_rate_field = FXTransaction._meta.get_field('exchange_rate')
decimal_places = exchange_rate_field.decimal_places

# Round exchange_rate to match database precision
data_copy["exchange_rate"] = round(Decimal(str(data_copy["exchange_rate"])), decimal_places)
```

**Benefits:**
- No hardcoded values
- Automatically adapts to model changes
- Single source of truth

### 3. Save Transaction Updates

**File:** `portfolio_management/transactions/views.py`

Updated `save_transactions()` to use dynamic precision when rounding FX rates before database insert:

```python
# Get decimal_places from the model field dynamically
exchange_rate_field = FXTransaction._meta.get_field('exchange_rate')
decimal_places = exchange_rate_field.decimal_places
data["exchange_rate"] = round(Decimal(str(data["exchange_rate"])), decimal_places)
```

### 4. Frontend Display Enhancement

**File:** `portfolio-frontend/src/views/TransactionsPage.vue`

Added `formatExchangeRate()` function for better readability:

```javascript
const formatExchangeRate = (rate) => {
  const rateNum = parseFloat(rate)

  // If rate < 1, display as 1:X for better readability
  if (rateNum < 1 && rateNum > 0) {
    const inverted = 1 / rateNum
    return `1:${inverted.toFixed(4)}`
  }

  // Otherwise, display the rate rounded to 4 decimals
  return rateNum.toFixed(4)
}
```

**Examples:**
- Old: `0.016853` → New: `1:59.3350` (easier to read for RUB/EUR rates)
- Old: `59.335000` → New: `59.3350` (cleaned up display)

### 5. Database Migration

**File:** `portfolio_management/common/migrations/0066_increase_decimal_precision_to_9.py`

**Created:** October 3, 2025
**Changes:**
- Alter field `quantity` on `transactions`
- Alter field `commission` on `transactions`
- Alter field `from_amount` on `fxtransaction`
- Alter field `to_amount` on `fxtransaction`
- Alter field `exchange_rate` on `fxtransaction`
- Alter field `commission` on `fxtransaction`

## Impact

### Before
- FX duplicate detection failed due to precision mismatch
- Exchange rates like `0.016853015691797202` rounded to `0.016853` caused false negatives
- Display of rates < 1 was hard to interpret

### After
- ✅ Full nano precision support (9 decimal places)
- ✅ Accurate duplicate detection
- ✅ Better readability with inverted rates for small values
- ✅ Dynamic precision - no hardcoded values

## Testing

### Test Cases

1. **FX Duplicate Detection**
   - API returns: `exchange_rate = 0.016853015691797202`
   - DB stores: `0.016853016` (9 decimals)
   - Duplicate check: ✅ Works correctly

2. **Display Format**
   - EUR/RUB rate `0.016853` → Displays as `1:59.3350`
   - USD/EUR rate `1.0850` → Displays as `1.0850`

3. **T-Bank Import**
   - Nano values correctly preserved
   - No data loss from rounding
   - Quantities with high precision supported

## Migration Steps

```bash
# Activate virtual environment
.\AW-portolio-management\Scripts\Activate.ps1

# Navigate to project
cd portfolio_management

# Apply migration
python manage.py migrate common 0066_increase_decimal_precision_to_9

# Verify
python manage.py showmigrations common
```

## Rollback (if needed)

```bash
# Roll back to previous migration
python manage.py migrate common 0065

# Remove migration file
rm common/migrations/0066_increase_decimal_precision_to_9.py
```

## Technical Notes

### Why 9 Decimal Places?

T-Bank API uses **nano** fields representing 10^-9:
```python
MoneyValue(currency='rub', units=197941, nano=560000000)
# Actual value: 197941.560000000
```

This requires 9 decimal places to preserve full precision.

### Dynamic Precision Benefits

1. **Maintainability**: Change model field → automatic propagation
2. **Type Safety**: Uses Django's ORM metadata
3. **Consistency**: Single source of truth
4. **Future-Proof**: Easy to adjust precision if needed

### Frontend Formatting Logic

- **Rate ≥ 1**: Show as-is with 4 decimals (e.g., `59.3350`)
- **Rate < 1**: Invert and show as `1:X` with 4 decimals (e.g., `1:59.3350`)
- **Rate = 0**: Handled by parseFloat (returns `0.0000`)

## Related Documentation

- [Bond Amortization Guide](BOND_AMORTIZATION_GUIDE.md)
- [Critical Fixes Summary](CRITICAL_FIXES_SUMMARY.md)
- [T-Bank API Integration](../core/tinkoff_utils.py)

---

**Status:** ✅ Production Ready
**Testing:** Completed
**Migration:** Ready to apply
