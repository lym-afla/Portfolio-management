# Decimal Precision Standards

## Overview

This document defines the decimal precision standards for financial calculations in the portfolio management system, ensuring consistency across data storage, calculations, and display while maintaining alignment with external API requirements.

---

## Precision Requirements by Data Type

### Monetary Values

#### Database Storage Precision
- **Transaction amounts**: 9 decimal places (`decimal_places=9`)
- **FX rates**: 9 decimal places (`decimal_places=9`)
- **Security prices**: 9 decimal places (`decimal_places=9`)
- **Commission**: 9 decimal places (`decimal_places=9`)
- **Quantities**: 9 decimal places (`decimal_places=9`)

#### Calculation Precision
- **Internal calculations**: Keep at least 9 decimal places
- **Intermediate results**: Maintain full precision, do not round prematurely
- **Aggregated values**: Keep 9+ decimal places during aggregation

#### Display Precision
- **Persisted aggregates** (AnnualPerformance.*): 2 decimal places
- **UI output**: Per `CustomUser.digits` setting or default 2 decimal places
- **FX rate display**: Special formatting for readability (see examples)

### Special Cases

#### FX Rate Display Formatting
```javascript
// For rates < 1, display as inverted for better readability
if (rateNum < 1 && rateNum > 0) {
    const inverted = 1 / rateNum
    return `1:${inverted.toFixed(4)}`
}
// Otherwise, display the rate rounded to 4 decimals
return rateNum.toFixed(4)
```

**Examples:**
- Rate `0.016853` → Display as `1:59.3350` (EUR/RUB)
- Rate `59.335000` → Display as `59.3350` (RUB/EUR)

---

## Implementation Standards

### Use Decimal, Never Float

```python
# ✅ Correct - Use Decimal for all financial calculations
from decimal import Decimal, ROUND_HALF_UP

price = Decimal('150.25')
quantity = Decimal('100')
value = price * quantity  # Result: Decimal('15025.00')

# ❌ Wrong - Never use float for financial calculations
price = 150.25  # float
quantity = 100  # float
value = price * quantity  # Imprecise float result
```

### Dynamic Precision Detection

When working with database models, dynamically retrieve precision to avoid hardcoding:

```python
# Get decimal_places from the model field dynamically
exchange_rate_field = FXTransaction._meta.get_field('exchange_rate')
decimal_places = exchange_rate_field.decimal_places

# Round exchange_rate to match database precision
data_copy["exchange_rate"] = round(Decimal(str(data_copy["exchange_rate"])), decimal_places)
```

### Rounding Standards

#### Rounding Mode
- **Default**: `ROUND_HALF_UP`
- **Financial calculations**: Always use `ROUND_HALF_UP`
- **Display formatting**: Follow user preferences

#### When to Round
- **Storage**: Round to database field precision before saving
- **Display**: Round only for final output, not for intermediate calculations
- **Aggregates**: Round after complete aggregation, not during

---

## External API Integration

### T-Bank API Compatibility

T-Bank API uses **nano** fields representing 10^-9:
```python
MoneyValue(currency='rub', units=197941, nano=560000000)
# Actual value: 197941.560000000
```

**Implementation Requirements:**
- Use 9 decimal places to preserve full nano precision
- Convert nano fields to Decimal: `Decimal(units) + Decimal(nano) / Decimal(1000000000)`
- Do not lose precision during conversion

### Yahoo Finance Integration

Yahoo Finance may return varying precision:
- **Stock prices**: Usually 2-4 decimal places
- **FX rates**: Variable precision, often 4-6 decimal places
- **Implementation**: Store received values at full precision, let database handle rounding

---

## Database Schema Precision

### Current Precision Standards

| Model | Field | Max Digits | Decimal Places | Example |
|-------|-------|------------|----------------|---------|
| Transactions | quantity | 20 | 9 | `100.123456789` |
| Transactions | price | 20 | 9 | `150.250000000` |
| Transactions | commission | 20 | 9 | `9.950000000` |
| FXTransaction | from_amount | 20 | 9 | `1000.000000000` |
| FXTransaction | to_amount | 20 | 9 | `920.500000000` |
| FXTransaction | exchange_rate | 20 | 9 | `0.920500000` |
| FXTransaction | commission | 20 | 9 | `5.000000000` |
| AnnualPerformance | *aggregates* | 20 | 2 | `1234567.89` |

### Migration Guidelines

When changing precision:
1. **Backwards-compatible**: Only increase precision, never decrease
2. **Backup first**: Always backup database before precision migrations
3. **Test thoroughly**: Verify calculations remain accurate
4. **Rollback plan**: Have migration rollback SQL ready

**Example Migration (0066_increase_decimal_precision_to_9.py):**
```python
migrations.AlterField(
    'transactions',
    'quantity',
    models.DecimalField(decimal_places=9, max_digits=20)
)
```

---

## Calculation Examples

### Bond Calculations

```python
from decimal import Decimal, ROUND_HALF_UP

# Bond with high precision price
price_per_bond = Decimal('98.765432109')  # 9 decimal places
quantity = Decimal('10')
notional_per_bond = Decimal('1000.000000000')

# Calculate total value
total_value = price_per_bond * quantity / Decimal('100') * notional_per_bond
# Result: Decimal('9876.54321090')

# Round for display (2 decimal places)
display_value = total_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
# Result: Decimal('9876.54')
```

### FX Rate Calculations

```python
# High-precision FX rate
rate = Decimal('0.016853015691797202')  # From API
amount = Decimal('1000.00')

# Convert with full precision
converted_amount = amount * rate
# Result: Decimal('16.853015692')

# Round to database precision (9 decimal places)
db_amount = converted_amount.quantize(Decimal('0.000000001'), rounding=ROUND_HALF_UP)
# Result: Decimal('16.853016000')
```

### Portfolio Performance

```python
# High-precision IRR calculation
cash_flows = [
    Decimal('-10000.000000000'),  # Initial investment
    Decimal('500.250000000'),     # Dividend
    Decimal('10500.750000000'),   # Sale proceeds
]

# Calculate with full precision
irr = calculate_irr(cash_flows)  # Returns high-precision Decimal

# Final display rounding (2 decimal places for percentages)
display_irr = irr.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
# Result: Decimal('0.0525') = 5.25%
```

---

## Testing Requirements

### Unit Tests for Precision

```python
def test_decimal_precision_preservation():
    """Test that API precision is preserved through database storage"""
    # High-precision input
    rate = Decimal('0.016853015691797202')

    # Save to database
    fx = FXTransaction.objects.create(
        from_amount=Decimal('1000.000000000'),
        to_amount=Decimal('16.853016000'),  # Rounded to 9 decimals
        exchange_rate=rate.quantize(Decimal('0.000000001'))  # 9 decimals
    )

    # Retrieve and verify
    retrieved = FXTransaction.objects.get(id=fx.id)
    assert retrieved.exchange_rate == Decimal('0.016853016')

def test_display_formatting():
    """Test FX rate display formatting"""
    # Small rate (< 1)
    assert format_exchange_rate('0.016853') == '1:59.3350'

    # Large rate (> 1)
    assert format_exchange_rate('59.335000') == '59.3350'
```

### Regression Tests

When changing precision logic:
1. Create test fixtures with known expected results
2. Test boundary conditions (very small/large numbers)
3. Verify no precision loss in calculation chains
4. Test display formatting matches expectations

---

## Common Pitfalls & Solutions

### Pitfall 1: Float Conversion
```python
# ❌ Wrong - Converts to float, loses precision
result = float(Decimal('0.016853015691797202')) * 1000

# ✅ Correct - Keep all operations in Decimal
result = Decimal('0.016853015691797202') * Decimal('1000')
```

### Pitfall 2: Premature Rounding
```python
# ❌ Wrong - Rounds too early
intermediate = some_calculation().quantize(Decimal('0.01'))
final_result = intermediate * other_value

# ✅ Correct - Round only at the end
intermediate = some_calculation()  # Keep full precision
final_result = (intermediate * other_value).quantize(Decimal('0.01'))
```

### Pitfall 3: String Conversion Issues
```python
# ❌ Wrong - May create float accidentally
value = Decimal(str(some_float))

# ✅ Correct - Direct string to Decimal
value = Decimal('123.456789012')
```

---

## Performance Considerations

### Decimal Performance
- Decimal operations are slower than float but necessary for financial accuracy
- Cache frequently used calculated values
- Consider bulk calculations for large datasets
- Use appropriate precision (not excessive) for each use case

### Database Performance
- Indexes on decimal fields work normally
- Queries with decimal comparisons are efficient
- Consider materialized views for complex aggregations

---

## Monitoring & Validation

### Data Quality Checks
```python
# Check for suspicious precision loss
def validate_transaction_precision():
    suspicious = Transactions.objects.filter(
        Q(price__regex=r'^\d+\.\d{0,2}$') |  # Too few decimals
        Q(commission__regex=r'^\d+\.0+$')     # Whole numbers only
    )
    return suspicious.count()
```

### Precision Monitoring
- Monitor API responses for changing precision
- Alert on precision that might indicate data quality issues
- Regular validation of stored vs. calculated values

---

## References

- **Python Decimal Documentation**: https://docs.python.org/3/library/decimal.html
- **Django DecimalField**: https://docs.djangoproject.com/en/stable/ref/models/fields/#decimalfield
- **IEEE 754 Floating Point**: For understanding float precision issues

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-03 | Initial 9-digit precision standard for T-Bank API compatibility |
| 1.1 | 2025-10-03 | Added dynamic precision detection patterns |
| 1.2 | 2025-10-03 | Added FX rate display formatting standards |
