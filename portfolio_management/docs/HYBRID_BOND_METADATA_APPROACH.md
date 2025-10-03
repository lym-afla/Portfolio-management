# Hybrid Bond Metadata Approach: MICEX + T-Bank Enhancement

**Date:** October 3, 2025
**Scope:** Enhanced bond metadata accuracy using both MICEX and T-Bank API
**Strategy:** Best of both worlds

## Overview

When creating a bond security from MICEX, the system now automatically enhances the metadata by also fetching from T-Bank API. This hybrid approach combines:

1. **MICEX Data** - Comprehensive Russian market data (initial notional, dates, coupon rate)
2. **T-Bank Data** - Accurate flags (floating coupon, amortization, trading status)

## Why Hybrid Approach?

### MICEX Strengths ✅
- ✅ Complete historical data
- ✅ Works for matured bonds
- ✅ Accurate initial notional values
- ✅ Official coupon rates and frequencies

### MICEX Weaknesses ❌
- ❌ TYPENAME field unreliable for bond type
- ❌ Current face value may be outdated
- ❌ No floating coupon flag
- ❌ Amortization detection by comparison only

### T-Bank Strengths ✅
- ✅ Accurate `floating_coupon_flag`
- ✅ Accurate `amortization_flag`
- ✅ Real-time trading data
- ✅ Complete instrument details

### T-Bank Weaknesses ❌
- ❌ May not have matured bonds
- ❌ Limited historical data
- ❌ Requires instrument_uid (not always available during MICEX creation)

## Solution: Sequential Enhancement

```
1. Fetch from MICEX (primary)
   ↓
2. Create asset with MICEX metadata
   ↓
3. Enhance with T-Bank data (if available)
   ↓
4. Final accurate bond metadata
```

## Implementation

### Step 1: MICEX Fetch

```python
# Fetch from MICEX
security_data = await fetch_security_from_micex_targeted(isin, BOND)

# Create BondMetadata from MICEX
bond_data = {
    "initial_notional": Decimal("1000"),  # From INITIALFACEVALUE
    "issue_date": date(2021, 4, 22),      # From ISSUEDATE
    "maturity_date": date(2026, 4, 16),   # From MATDATE
    "coupon_rate": Decimal("9.15"),       # From COUPONPERCENT
    "coupon_frequency": 4,                # From COUPONFREQUENCY
    "is_amortizing": True,                # Detected: 375 < 1000
    "bond_type": "FIXED"                  # Default (COUPONPERCENT > 0)
}
```

### Step 2: T-Bank Enhancement

```python
# After MICEX creation, enhance with T-Bank
await _enhance_bond_metadata_from_tbank(asset, isin, user)

# Fetches from T-Bank using:
response = client.instruments.bond_by(
    id_type=2,              # class_code + id lookup
    id=isin,                # Use ISIN
    class_code='TQCB'       # Corporate bonds board
)
```

### Step 3: Metadata Update

```python
bond_instrument = response.instrument

# Update with authoritative T-Bank flags
if bond_instrument.floating_coupon_flag:
    bond_meta.bond_type = "FLOATING"  # Override MICEX "FIXED"

if bond_instrument.amortization_flag:
    bond_meta.is_amortizing = True  # Confirm MICEX detection

bond_meta.save()
```

## API Parameters Explained

### `bond_by()` Parameters

```python
client.instruments.bond_by(
    id_type=2,              # Lookup method
    id=isin,                # Identifier
    class_code='TQCB'       # Trading board
)
```

**`id_type` Values:**
- `1` = FIGI
- `2` = class_code + id (we use this)
- `3` = UID
- `4` = ticker

**`class_code` Values:**
- `'TQCB'` = Corporate bonds (most common)
- `'TQOB'` = OTC bonds
- `'TQIR'` = IIS bonds
- `'EQOB'` = Other bonds

**Why `id_type=2`?**
- Allows searching by ISIN + board
- More reliable than UID (which we don't have during MICEX creation)
- Works for all actively traded bonds

**Why `class_code='TQCB'`?**
- Most corporate bonds trade on TQCB
- Covers majority of T-Bank bond transactions
- If not found, gracefully keeps MICEX data

## Data Flow Example

### Example: Европлан 001Р-02

```
MICEX Fetch:
├─ ISIN: RU000A103133
├─ INITIALFACEVALUE: 1000
├─ FACEVALUE: 375
├─ COUPONPERCENT: 9.15
├─ COUPONFREQUENCY: 4
└─ Detection: is_amortizing=True (375<1000), bond_type="FIXED"

T-Bank Enhancement:
└─ bond_by(id_type=2, id="RU000A103133", class_code="TQCB")
   ├─ floating_coupon_flag: False → Keep "FIXED" ✓
   ├─ amortization_flag: True → Confirm is_amortizing ✓
   └─ initial_nominal: 1000 RUB → Matches MICEX ✓

Final Metadata:
{
    initial_notional: 1000,
    is_amortizing: True,      ← Confirmed by both sources
    bond_type: "FIXED",       ← Confirmed not floating
    coupon_rate: 9.15,
    coupon_frequency: 4,
    issue_date: 2021-04-22,
    maturity_date: 2026-04-16
}
```

### Example: Floating Rate Bond

```
MICEX Fetch:
├─ COUPONPERCENT: 8.5
└─ Detection: bond_type="FIXED" (default)

T-Bank Enhancement:
└─ floating_coupon_flag: True
   └─ Update: bond_type="FLOATING" ✓ (corrected!)

Final Metadata:
{
    bond_type: "FLOATING",    ← Corrected by T-Bank
    ...
}
```

## Error Handling

### Bond Not Found in TQCB

```python
# T-Bank returns 50002 error
logger.info(
    f"Bond {isin} not found in T-Bank TQCB board, "
    f"keeping MICEX metadata"
)
# Continues with MICEX-only data
```

### T-Bank API Unavailable

```python
# Network error, token expired, etc.
logger.error(f"Error enhancing bond metadata: {e}")
# Continues with MICEX-only data
```

### MICEX Has More Data

If MICEX has data that T-Bank doesn't:
```python
# Only update if T-Bank has the field
if hasattr(bond_instrument, 'floating_coupon_flag'):
    # Update
else:
    # Keep MICEX value
```

## Benefits

### Accuracy 🎯
- ✅ Correct floating rate detection
- ✅ Authoritative amortization flag
- ✅ Best data from both sources

### Robustness 🛡️
- ✅ Works even if T-Bank unavailable
- ✅ Works for matured bonds (MICEX only)
- ✅ Works for new bonds (both sources)

### Performance ⚡
- ✅ Single additional API call per bond
- ✅ Async/non-blocking
- ✅ Cached in database

## Workflow Integration

### During Import from T-Bank

```
Transaction detected for new bond
↓
_find_or_create_security()
↓
create_security_from_micex()
├─ Fetch MICEX data ✓
├─ Create asset ✓
├─ Create BondMetadata ✓
└─ _enhance_bond_metadata_from_tbank() ✓ (NEW!)
   └─ Update floating_coupon_flag ✓
   └─ Update amortization_flag ✓
↓
Complete bond with accurate metadata ✓
```

### Success Criteria

✅ **Must have from MICEX:**
- initial_notional
- issue_date
- maturity_date
- coupon_rate
- coupon_frequency

✅ **Enhanced by T-Bank:**
- bond_type (FLOATING vs FIXED)
- is_amortizing (authoritative flag)

## Testing

### Test Case 1: Regular Fixed Rate Bond

```python
# MICEX: COUPONPERCENT=9.15, not amortizing
# T-Bank: floating_coupon_flag=False, amortization_flag=False

assert bond_meta.bond_type == "FIXED"
assert bond_meta.is_amortizing == False
```

### Test Case 2: Floating Rate Bond

```python
# MICEX: COUPONPERCENT=8.5 (can't detect floating)
# T-Bank: floating_coupon_flag=True

assert bond_meta.bond_type == "FLOATING"  # Corrected!
```

### Test Case 3: Amortizing Bond

```python
# MICEX: FACEVALUE=375, INITIALFACEVALUE=1000
# T-Bank: amortization_flag=True

assert bond_meta.is_amortizing == True  # Confirmed by both
assert bond_meta.initial_notional == Decimal("1000")
```

### Test Case 4: T-Bank Unavailable

```python
# MICEX: Success
# T-Bank: Network error

# Result: Uses MICEX data only
assert bond_meta.initial_notional == Decimal("1000")
assert bond_meta.bond_type == "FIXED"  # Default
```

## Comparison with Alternative Approaches

### Alternative 1: MICEX Only
❌ No floating rate detection
❌ Amortization by comparison only
✅ Works for matured bonds

### Alternative 2: T-Bank Only
✅ Accurate flags
❌ Missing matured bonds
❌ No historical data

### Alternative 3: Our Hybrid Approach
✅ Accurate flags from T-Bank
✅ Complete data from MICEX
✅ Works for all bonds
✅ Graceful degradation

## Related Documentation

- [MICEX Targeted API Upgrade](MICEX_TARGETED_API_UPGRADE.md)
- [T-Bank API Integration Upgrade](TBANK_API_INTEGRATION_UPGRADE.md)
- [Bond Amortization Guide](BOND_AMORTIZATION_GUIDE.md)

---

**Status:** ✅ Production Ready
**Testing:** Comprehensive
**Fallback:** Graceful (MICEX-only if T-Bank fails)
