# Bond Redemption Semantics - Technical Note

## Understanding Amortizing Bond Redemptions

### The Challenge

T-Bank API returns bond redemption operations with **`quantity=0`**, which initially seems incorrect but is actually the proper representation of amortizing bond mechanics.

### Example from T-Bank API

```python
OperationItem(
    type=OperationType.OPERATION_TYPE_BOND_REPAYMENT,
    name='Европлан 001Р-02',
    date=datetime.datetime(2022, 11, 21, 8, 2, 5),
    payment=MoneyValue(currency='rub', units=6250, nano=0),  # Cash received
    price=MoneyValue(currency='rub', units=0, nano=0),  # Not used
    quantity=0,  # Number of bonds doesn't change!
    quantity_rest=0,
    quantity_done=0,
    ...
)
```

### Key Insight: Quantity vs. Notional

**For Amortizing Bonds:**

| Aspect | What Happens |
|--------|--------------|
| **Number of bonds** | Stays the SAME |
| **Face value per bond** | DECREASES |
| **Total position value** | DECREASES |

**Example:**
- You own 10 bonds, each with $1000 face value = $10,000 total
- Partial redemption of $200 per bond occurs
- **After redemption:**
  - You still own 10 bonds (quantity unchanged)
  - Each bond now has $800 face value
  - Total position: 10 × $800 = $8,000
  - Cash received: 10 × $200 = $2,000

### Implementation Approach

#### 1. Transaction Recording

For bond redemptions, we record:

```python
{
    "type": "Bond redemption",
    "quantity": None,  # Or 0 - bonds held doesn't change
    "cash_flow": 6250.00,  # Cash received (positive)
    "notional_change": 6250.00,  # Total notional redeemed
    "price": None,  # Not a market transaction
    "currency": "RUB"
}
```

**Why `quantity` is None/0:**
- The NUMBER of bonds you hold doesn't change
- Only the NOTIONAL (face value) per bond changes
- Setting quantity to negative would incorrectly suggest you sold bonds

#### 2. Position Calculation

For regular assets:
```python
position = sum(quantity for all transactions)
```

For amortizing bonds (future enhancement):
```python
number_of_bonds = sum(quantity for buy/sell transactions)
current_notional_per_bond = initial_notional - sum(notional_changes)
position_value = number_of_bonds * current_notional_per_bond
```

#### 3. Realized Gain/Loss

Bond redemptions are **return of capital**, not gains:

```python
# In realized_gain_loss method
if transaction.type in ['Bond redemption', 'Bond maturity']:
    # Skip from G/L calculation
    # This is return of principal, not a gain or loss
    # The return comes from coupons (tracked separately)
    continue
```

**Why skip?**
- Redemption at par = you get back what you invested (no gain/loss)
- Redemption at premium/discount = difference already reflected in price when bought
- True returns come from:
  - Coupons (tracked as "Coupon" transactions)
  - Price appreciation if bought below par (captured when bought/sold)

#### 4. IRR Calculation

```python
# In _calculate_cash_flow
if transaction.type in ["Bond redemption", "Bond maturity"]:
    return transaction.cash_flow  # Positive cash inflow
```

IRR correctly treats redemptions as cash returned to investor.

### Data Flow

#### From T-Bank API to Database

1. **T-Bank Operation:**
   ```
   OPERATION_TYPE_BOND_REPAYMENT
   quantity=0
   payment=6250 RUB
   ```

2. **map_tinkoff_operation_to_transaction:**
   ```python
   {
       "type": "Bond redemption",
       "quantity": None,
       "cash_flow": 6250,
       "notional_change": 6250,  # TOTAL cash received
       "currency": "RUB"
   }
   ```

3. **import_transactions_from_api (views.py):**
   ```python
   # First, format transaction data
   transaction_data = {
       "date": trans["date"],
       "type": trans["type"],
       "quantity": trans.get("quantity"),  # None
       "cash_flow": trans.get("cash_flow"),  # 6250
       "notional_change": trans.get("notional_change"),  # 6250 (total)
       ...
   }

   # Then, calculate PER-BOND notional for bond redemptions
   if trans["type"] in ["Bond redemption", "Bond maturity"]:
       total_notional = trans.get("notional_change")  # 6250
       security = trans.get("security")

       # Get position at redemption date
       position = await security.position(date, user, [account.id])  # 10 bonds

       # Calculate per-bond notional
       notional_per_bond = total_notional / abs(position)  # 6250 / 10 = 625
       transaction_data["notional_change"] = notional_per_bond  # ← UPDATED!
   ```

4. **save_transactions → Database:**
   ```sql
   INSERT INTO transactions (
       type, quantity, cash_flow, notional_change, ...
   ) VALUES (
       'Bond redemption', NULL, 6250.00, 625.00, ...
       --                                 ^^^^^^ PER-BOND value
   )
   ```

### Edge Cases and Considerations

#### Case 1: Full Bond Maturity

For `OPERATION_TYPE_BOND_REPAYMENT_FULL`:
- Same logic as partial redemption
- `cash_flow` = full remaining notional
- After this, position should be closed (quantity becomes 0 if you sold all)

#### Case 2: Determining Notional Per Bond

From T-Bank data, we only get **total cash received**:
- If you know you hold N bonds: `notional_per_bond = cash_flow / N`
- If quantity history is complex, may need manual adjustment

**Solution:** Store `notional_change` as total received, calculate per-bond later:

```python
# In transaction
notional_change = 6250.00  # Total cash

# Later, when you know you had 10 bonds
notional_per_bond = 6250.00 / 10  # = 625 per bond

# Update NotionalHistory
NotionalHistory.objects.create(
    asset=bond,
    date=transaction.date,
    notional_per_unit=initial_notional - notional_per_bond,
    change_amount=-notional_per_bond
)
```

#### Case 3: Bought at Premium/Discount

If bond was bought at 95 (below par):
- Initial cost per bond: $950
- Face value: $1000
- Redemption at par: $1000 received

**Realized Gain Calculation:**
- Gain = ($1000 - $950) = $50 per bond
- But this is captured at purchase time (paid less than face)
- Redemption itself is neutral (return of face value)

**Accounting Treatment:**
- Track the premium/discount at purchase
- Amortize it over the life of the bond
- At redemption, close out with no additional gain/loss

### Current Implementation Status

✅ **Implemented:**
- Bond redemption transaction types
- T-Bank API import handling (quantity=0)
- notional_change field in Transactions (stored as PER-BOND value)
- **Automatic per-bond notional calculation during import**
- **Automatic NotionalHistory creation on transaction save**
- Correct realized_gain_loss calculation for redemptions
- Correct IRR treatment

✅ **Fully Automated:**
- Per-bond notional calculated using position() during import
- NotionalHistory created automatically when transaction saved
- No manual intervention required

🔜 **Future Work:**
- Enhanced position() method for amortizing bonds (value calculation)
- Premium/discount amortization over time
- Yield-to-maturity (YTM) calculations
- Duration metrics considering amortization

### Fully Automated Process

**No manual steps required!** The system now automatically:

1. **During Import (`import_transactions_from_api`):**
   ```python
   # For bond redemptions, automatically calculates per-bond notional:
   if trans["type"] in ["Bond redemption", "Bond maturity"]:
       total_notional = trans.get("notional_change")  # From T-Bank
       position = await security.position(date, user, [account.id])

       # Calculate and store per-bond value
       notional_per_bond = total_notional / abs(position)
       transaction_data["notional_change"] = notional_per_bond
   ```

2. **On Transaction Save:**
   ```python
   # Transactions.save() automatically triggers:
   def save(self, *args, **kwargs):
       super().save(*args, **kwargs)

       if self.type in ['Bond redemption', 'Bond maturity']:
           self._create_notional_history()  # Auto-creates NotionalHistory
   ```

3. **NotionalHistory Created:**
   ```python
   NotionalHistory.objects.create(
       asset=bond,
       date=redemption.date,
       notional_per_unit=previous_notional - notional_per_bond,
       change_amount=-notional_per_bond,
       change_reason='REDEMPTION'
   )
   ```

✨ **Everything happens automatically!**

### Testing Bond Redemptions

```python
def test_bond_redemption_import():
    """Test T-Bank bond redemption with quantity=0"""

    # Create bond and initial position
    bond = Assets.objects.create(type='Bond', name='Test Bond')
    BondMetadata.objects.create(
        asset=bond,
        initial_notional=Decimal('1000'),
        is_amortizing=True
    )

    # Buy 10 bonds
    Transactions.objects.create(
        type='Buy',
        security=bond,
        quantity=Decimal('10'),
        price=Decimal('100'),
        date=date(2022, 1, 1)
    )

    # Import redemption (like from T-Bank)
    Transactions.objects.create(
        type='Bond redemption',
        security=bond,
        quantity=None,  # T-Bank gives quantity=0
        cash_flow=Decimal('2000'),  # 10 bonds * 200 per bond
        notional_change=Decimal('2000'),
        date=date(2022, 6, 1)
    )

    # Verify position still shows 10 bonds
    position = bond.position(date(2022, 6, 1), user)
    assert position == Decimal('10')  # Still have 10 bonds

    # Verify notional decreased
    # (requires NotionalHistory to be created manually)

    # Verify IRR treats as cash inflow
    irr = IRR(user.id, date(2022, 12, 31), asset_id=bond.id)
    # Should be positive due to cash received
```

### Best Practices

1. **Always create BondMetadata** for bonds with `is_amortizing=True`
2. **After importing redemptions**, manually create NotionalHistory entries
3. **Verify cash flows** match expected redemption amounts
4. **Document any manual adjustments** in transaction comments
5. **Use "Bond maturity"** type only for final repayment, not partial

### References

- T-Bank API Documentation: [tinkoff.invest](https://tinkoff.github.io/investAPI/)
- Bond Accounting Principles: IFRS 9, FASB ASC 320
- Related Code: `common/models.py` (lines 568-591)

---

**Last Updated:** October 2, 2025
**Status:** Implemented - Manual NotionalHistory creation required
**Next Steps:** Automate per-bond notional calculation
