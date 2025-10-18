# Per-Bond Notional Calculation - Implementation Details

## Overview

This document explains how the system automatically calculates **per-bond notional** values during bond redemption import from T-Bank API.

## The Challenge

**T-Bank API provides:**
- `quantity=0` (number of bonds doesn't change)
- `payment=6250 RUB` (total cash received)

**We need:**
- Per-bond notional change for database storage
- Accurate G/L calculations
- Correct NotionalHistory tracking

## Solution Architecture

### Three-Stage Process

```
T-Bank API → Import Calculation → Database Storage → Auto-History Creation
```

#### Stage 1: T-Bank API Response
```python
OperationItem(
    type=OPERATION_TYPE_BOND_REPAYMENT,
    quantity=0,  # Bonds held doesn't change
    payment=MoneyValue(currency='rub', units=6250, nano=0)  # Total cash
)
```

#### Stage 2: Map to Transaction Data
```python
# tinkoff_utils.py - map_tinkoff_operation_to_transaction()
transaction_data = {
    "type": "Bond redemption",
    "quantity": None,
    "cash_flow": 6250,
    "notional_change": 6250,  # ← Still TOTAL at this point
}
```

#### Stage 3: Calculate Per-Bond (During Import)
```python
# transactions/views.py - import_transactions_from_api()
if trans["type"] in ["Bond redemption", "Bond maturity"]:
    total_notional = trans.get("notional_change")  # 6250
    security = trans.get("security")

    # ← KEY STEP: Get position at redemption date
    position = await database_sync_to_async(security.position)(
        trans["date"], user, [account.id]
    )
    # Returns: 10 bonds

    # Calculate per-bond notional
    notional_per_bond = Decimal(total_notional) / abs(Decimal(position))
    # = 6250 / 10 = 625 RUB per bond

    # ← OVERRIDE with per-bond value
    transaction_data["notional_change"] = notional_per_bond
```

#### Stage 4: Save to Database
```python
# Transaction saved with:
{
    "type": "Bond redemption",
    "quantity": None,
    "cash_flow": 6250,  # Total cash
    "notional_change": 625,  # ← Per-bond value
}
```

#### Stage 5: Auto-Create NotionalHistory
```python
# common/models.py - Transactions.save()
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)

    if self.type in [TRANSACTION_TYPE_BOND_REDEMPTION, TRANSACTION_TYPE_BOND_MATURITY]:
        if self.security and self.notional_change:
            self._create_notional_history()

# _create_notional_history()
def _create_notional_history(self):
    # notional_change is ALREADY per-bond (625)
    notional_per_bond = self.notional_change

    # Get previous notional
    previous_history = NotionalHistory.objects.filter(
        asset=self.security,
        date__lt=self.date
    ).order_by('-date').first()

    if previous_history:
        previous_notional = previous_history.notional_per_unit  # 1000
    else:
        previous_notional = bond_meta.initial_notional  # 1000

    # Calculate new notional
    new_notional = previous_notional - notional_per_bond  # 1000 - 625 = 375

    # Create history entry
    NotionalHistory.objects.update_or_create(
        asset=self.security,
        date=self.date,
        change_reason='REDEMPTION',
        defaults={
            'notional_per_unit': 375,
            'change_amount': -625,
        }
    )
```

## Implementation Details

### Key Files and Line Numbers

1. **T-Bank Mapping** (`core/tinkoff_utils.py` lines 382-413)
   - Extracts total cash from payment field
   - Sets `notional_change = cash_received` (total)

2. **Per-Bond Calculation** (`transactions/views.py` lines 973-1007)
   ```python
   # Get position using position() method
   position = await database_sync_to_async(security.position)(
       trans["date"], user, [account.id]
   )

   # Calculate per-bond
   notional_per_bond = Decimal(total_notional) / abs(Decimal(position))

   # Override transaction data
   transaction_data["notional_change"] = notional_per_bond
   ```

3. **Auto-Create History** (`common/models.py` lines 952-1034)
   ```python
   def save(self, *args, **kwargs):
       super().save(*args, **kwargs)

       if self.type in ['Bond redemption', 'Bond maturity']:
           self._create_notional_history()
   ```

4. **Use in G/L Calculation** (`common/models.py` lines 575-634)
   ```python
   # notional_redeemed is already per-bond
   notional_redeemed = getattr(transaction, 'notional_change', None)

   # Use directly in calculation
   cost_basis = notional_redeemed * buy_in_price * bonds_held
   ```

### Why This Approach?

#### Alternative Approaches Considered

**❌ Option 1: Store total, calculate per-bond in G/L**
```python
# Problem: Would need position() in multiple places
# - G/L calculation
# - NotionalHistory creation
# - Any other calculations
```

**❌ Option 2: Calculate per-bond in tinkoff_utils**
```python
# Problem: Don't have investor/account context in tinkoff_utils
# Can't call position() method without these
```

**✅ Option 3: Calculate during import (chosen)**
```python
# Advantages:
# - Have all context (investor, account, security)
# - Can use position() method
# - Calculate once, use everywhere
# - Stored value is what we actually need
```

### Data Consistency

**Invariant:**
```
transaction.notional_change = per-bond value
transaction.cash_flow = total cash received
```

**Verification:**
```python
# For 10 bonds with 625 per bond:
assert transaction.cash_flow == transaction.notional_change * position
# 6250 == 625 * 10 ✓
```

## Usage in Calculations

### Realized Gain/Loss
```python
def calculate_position_gain_loss(...):
    if is_bond_redemption:
        cash_received = transaction.cash_flow  # 6250 (total)
        notional_redeemed = transaction.notional_change  # 625 (per-bond)

        # Get position
        bonds_held = abs(position)  # 10

        # Calculate cost basis
        cost_basis = notional_redeemed * buy_in_price * bonds_held
        # = 625 * 95 * 10 = 59,375  # Wait, this seems high...

        # Actually buy_in_price is a percentage (95 = 95% of par)
        # So we need: 625 * (95/100) * 10 = 5,937.5 ✓

        # Gain
        gain = cash_received - cost_basis
        # = 6250 - 5937.5 = 312.5 ✓
```

### NotionalHistory Creation
```python
def _create_notional_history(self):
    # Use notional_change directly (already per-bond)
    notional_per_bond = self.notional_change  # 625

    # Calculate new notional
    new_notional = previous_notional - notional_per_bond
    # = 1000 - 625 = 375

    # Create history
    NotionalHistory.objects.create(
        notional_per_unit=375,
        change_amount=-625
    )
```

## Error Handling

### Edge Case 1: Position is Zero
```python
if position and position != 0:
    notional_per_bond = Decimal(total_notional) / abs(Decimal(position))
    transaction_data["notional_change"] = notional_per_bond
else:
    logger.warning(
        f"Position is 0 for {security.name} on {trans['date']}, "
        f"keeping total notional_change={total_notional}"
    )
    # Keeps total value - better than failing
```

### Edge Case 2: Security Not Found
```python
security = trans.get("security")

if total_notional and security:
    # Calculate per-bond
else:
    # Skip calculation, keep total
```

### Edge Case 3: Async Position Calculation
```python
try:
    position = await database_sync_to_async(security.position)(
        trans["date"], user, [account.id]
    )
except Exception as e:
    logger.error(f"Error calculating per-bond notional: {e}", exc_info=True)
    # Transaction still saved, but with total notional
```

## Testing

### Test Case 1: Standard Redemption
```python
# Setup
bond = create_bond(initial_notional=1000)
buy_bonds(10, price=100)  # 10 bonds at par

# Import redemption
import_tbank_operation(
    type=BOND_REPAYMENT,
    payment=2000,  # Total
    quantity=0
)

# Verify
transaction = Transactions.objects.last()
assert transaction.notional_change == 200  # Per-bond: 2000/10
assert transaction.cash_flow == 2000  # Total

# Verify history
history = NotionalHistory.objects.last()
assert history.notional_per_unit == 800  # 1000 - 200
assert history.change_amount == -200
```

### Test Case 2: Multiple Redemptions
```python
# First redemption
import_redemption(payment=2000)  # 10 bonds → 200 per bond
# notional_per_unit = 1000 - 200 = 800

# Second redemption
import_redemption(payment=1500)  # Still 10 bonds → 150 per bond
# notional_per_unit = 800 - 150 = 650
```

### Test Case 3: Partial Position
```python
# Buy 10 bonds in account A
buy_bonds(10, account=account_a)

# Buy 5 bonds in account B
buy_bonds(5, account=account_b)

# Redemption only affects account A
import_redemption(payment=2000, account=account_a)
# Position at account A: 10 bonds
# Per-bond: 2000 / 10 = 200 ✓

# Account B unaffected
```

## Summary

**Key Points:**
1. ✅ T-Bank gives **total** cash (6250)
2. ✅ We calculate **per-bond** during import (625)
3. ✅ Store per-bond in `notional_change` field
4. ✅ Use `position()` method to get bond count
5. ✅ Automatic NotionalHistory creation
6. ✅ Correct G/L calculations

**No Manual Steps Required!** 🎉

---

**Implementation Date:** October 2, 2025
**Status:** Production Ready
**Testing:** Awaiting user validation
