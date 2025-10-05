# Bond Price Formatting Fix

## Problem

Bond prices in the positions table were showing as currency values (e.g., "₽100") instead of percentages (e.g., "100%").

**Example:**
- **Before**: Entry Price: ₽100, Current Price: ₽98.5
- **Expected**: Entry Price: 100%, Current Price: 98.5%

## Root Cause

The issue had two components:

1. **Missing `instrument_type` in position data**: The `instrument_type` field wasn't being added to the position dictionaries, so the formatting logic couldn't distinguish bonds from other instruments.

2. **Incorrect formatting logic**: The `currency_format()` function had bond logic that used `format_percentage()`, which multiplies values by 100. But bond prices are already stored as percentages (100 = 100%), not decimals (1.0 = 100%).

## Solution

### 1. Added `instrument_type` to Position Dictionaries

**File:** `portfolio_management/core/tables_utils.py`

#### Open Positions (lines 321-327)
```python
position = {
    "id": asset.id,
    "type": asset.type,
    "instrument_type": asset.type,  # For formatting logic
    "name": asset.name,
    "currency": currency_format(None, asset.currency),
}
```

#### Closed Positions (lines 85-92)
```python
position = {
    "id": asset.id,
    "type": asset.type,
    "instrument_type": asset.type,  # For formatting logic
    "name": asset.name,
    "currency": currency_format(None, asset.currency),
    "exit_date": exit_date,
}
```

### 2. Created Dedicated Bond Price Formatter

**File:** `portfolio_management/core/formatting_utils.py`

#### Added `format_bond_price()` Function (lines 145-166)
```python
def format_bond_price(value: Union[Decimal, float, int, None], digits: int = 2) -> str:
    """
    Format a bond price as a percentage.
    Bond prices are stored as actual percentages (100 = 100%), not decimals.

    :param value: Bond price value (100 = 100%)
    :param digits: Number of digits for rounding
    :return: Formatted percentage string
    """
    if value is None:
        return "NA"

    try:
        value = Decimal(value)
        if value < 0:
            return f"({abs(value):.{digits}f}%)"
        elif value == 0:
            return "–"
        else:
            return f"{value:.{digits}f}%"
    except (TypeError, ValueError):
        return str(value)
```

### 3. Updated `format_value()` to Use Bond Formatter

**File:** `portfolio_management/core/formatting_utils.py` (lines 73-75)

Added specific check for bond prices:
```python
elif key in ["entry_price", "current_price"] and instrument_type and instrument_type.lower() == "bond":
    # Bond prices are stored as percentages (100 = 100%), format them as such
    return format_bond_price(value, digits)
```

### 4. Cleaned Up `currency_format()`

**File:** `portfolio_management/core/formatting_utils.py` (lines 82-120)

Removed the bond-specific logic from `currency_format()` since it's now handled by `format_value()`:

**Before:**
```python
if currency is None:
    symbol = ""
elif instrument_type and instrument_type.lower() == "bond":
    return format_percentage(value, digits)  # ❌ This was wrong
else:
    symbol = get_currency_symbol(...)
```

**After:**
```python
if currency is None:
    symbol = ""
else:
    symbol = get_currency_symbol(currency.upper(), locale="en_US")
```

## Key Differences

### `format_percentage()` vs `format_bond_price()`

**`format_percentage(value, digits)`:**
- Expects decimal values: `1.0` = 100%
- Multiplies by 100: `0.985 * 100 = 98.5%`
- Used for: IRR, total return %, share of portfolio

**`format_bond_price(value, digits)`:**
- Expects percentage values: `100` = 100%
- Does NOT multiply: `98.5 = 98.5%`
- Used for: Bond entry_price and current_price

## Example

### Bond with 100% of par price

**Data:**
- `entry_price`: 100 (stored as percentage)
- `current_price`: 98.5 (stored as percentage)
- `instrument_type`: "Bond"

**Formatting:**
```python
# entry_price formatting
format_value(100, "entry_price", "RUB", 2, "Bond")
# Result: "100.00%"

# current_price formatting
format_value(98.5, "current_price", "RUB", 2, "Bond")
# Result: "98.50%"

# Stock price for comparison
format_value(100, "current_price", "RUB", 2, "Stock")
# Result: "₽100.00"
```

## Testing

### Manual Test
1. Open the Open Positions or Closed Positions table
2. Find a bond position
3. Check that `entry_price` and `current_price` display as percentages (e.g., "100.00%")
4. Check that values (entry_value, current_value) still display as currency

### Expected Output

**For Bonds:**
| Field | Before | After |
|-------|--------|-------|
| Entry Price | ₽100.00 | 100.00% |
| Current Price | ₽98.50 | 98.50% |
| Entry Value | ₽100,000.00 | ₽100,000.00 |
| Current Value | ₽98,500.00 | ₽98,500.00 |

**For Stocks (unchanged):**
| Field | Format |
|-------|--------|
| Entry Price | ₽1,000.50 |
| Current Price | ₽1,050.25 |
| Entry Value | ₽100,000.00 |
| Current Value | ₽105,025.00 |

## Impact on Other Formatting

### What Changed
- ✅ Bond `entry_price` and `current_price` now format as percentages
- ✅ All other fields format unchanged

### What Stayed the Same
- ✅ Position values (entry_value, current_value) still format as currency
- ✅ Stock/Equity prices still format as currency
- ✅ Percentages (IRR, total return) still use `format_percentage()`
- ✅ Currency symbols still display correctly

## Notes

### Bond Price Storage
In the database and calculations, bond prices are stored as:
- **Percentage of par**: 100 = 100%, 98.5 = 98.5%
- **NOT decimals**: NOT 1.0 = 100%, NOT 0.985 = 98.5%

This is consistent with bond market conventions where:
- Prices are quoted as "% of par"
- 100 means the bond trades at its face value
- 98.5 means the bond trades at 98.5% of its face value

### Calculation Methods
The underlying calculation methods work in percentage terms:
- `calculate_buy_in_price()` returns percentage for bonds
- `price_at_date()` returns percentage for bonds
- `unrealized_gain_loss()` applies notional when calculating actual gains

## Future Enhancements

Potential improvements for bond display:
1. Show notional value in tooltip
2. Display yield-to-maturity alongside price
3. Add color coding for premium (>100%) vs discount (<100%) bonds

---

**Status:** ✅ Complete
**Date:** October 4, 2025
**Impact:** Medium - Improves bond price display clarity
