# Bond Amortization & Derivatives Framework - Quick Reference

## 🎯 What's New

Your portfolio management system now has **comprehensive bond support** including:

✅ **Amortizing bond tracking** - Handle bonds with declining notional/principal
✅ **Accurate IRR calculations** - Redemptions treated as return of capital
✅ **Partial redemptions** - Track each principal repayment event
✅ **T-Bank integration** - Automatic import of bond redemptions
✅ **Derivatives framework** - Ready for options and futures

## 🚀 Quick Start

### 1. Run Migration

```bash
python manage.py migrate common 0064
```

### 2. Add Metadata to Existing Bonds

```python
from common.models import Assets, BondMetadata
from decimal import Decimal

bond = Assets.objects.get(ISIN="YOUR_BOND_ISIN")
BondMetadata.objects.create(
    asset=bond,
    initial_notional=Decimal('1000.00'),
    maturity_date=date(2030, 1, 1),
    coupon_rate=Decimal('5.25'),
    coupon_frequency=2,
    is_amortizing=True,  # Set True if amortizing
    bond_type='FIXED'
)
```

### 3. Record Bond Redemptions

⚠️ **Important:** For amortizing bonds, `quantity` doesn't change (it remains the same number of bonds). Only the notional decreases. See [`BOND_REDEMPTION_SEMANTICS.md`](./BOND_REDEMPTION_SEMANTICS.md) for details.

```python
from common.models import Transactions, NotionalHistory
from constants import TRANSACTION_TYPE_BOND_REDEMPTION

# Record redemption (T-Bank import does this automatically)
Transactions.objects.create(
    investor=user,
    account=account,
    security=bond,
    type=TRANSACTION_TYPE_BOND_REDEMPTION,
    date=date(2025, 6, 1),
    quantity=None,  # Bonds held doesn't change!
    cash_flow=Decimal('2000.00'),  # Cash received
    notional_change=Decimal('2000.00'),  # Total notional redeemed
    currency='USD'
)

# Track notional history
NotionalHistory.objects.create(
    asset=bond,
    date=date(2025, 6, 1),
    notional_per_unit=Decimal('800.00'),  # Now $800 per bond
    change_amount=Decimal('-200.00'),
    change_reason='REDEMPTION'
)
```

## 📊 Key Features

### New Transaction Types

| Type | Constant | Use Case |
|------|----------|----------|
| Bond redemption | `TRANSACTION_TYPE_BOND_REDEMPTION` | Partial principal repayment |
| Bond maturity | `TRANSACTION_TYPE_BOND_MATURITY` | Full maturity/final repayment |

### New Models

| Model | Purpose |
|-------|---------|
| `BondMetadata` | Bond-specific data (coupon, maturity, notional) |
| `NotionalHistory` | Track notional changes over time |
| `OptionMetadata` | Foundation for options (future) |
| `FutureMetadata` | Foundation for futures (future) |

### Enhanced Calculations

- **IRR** - Now treats redemptions as return of capital (not gains)
- **Realized G/L** - Properly handles redemptions vs. sales
- **Position** - Accounts for changing notional in amortizing bonds
- **Buy-in Price** - Notional-weighted for accurate cost basis

## 📁 Documentation

- **User Guide:** [`BOND_AMORTIZATION_GUIDE.md`](./BOND_AMORTIZATION_GUIDE.md) - Comprehensive usage guide with examples
- **Implementation:** [`IMPLEMENTATION_SUMMARY.md`](./IMPLEMENTATION_SUMMARY.md) - Technical details and migration checklist
- **Redemption Semantics:** [`BOND_REDEMPTION_SEMANTICS.md`](./BOND_REDEMPTION_SEMANTICS.md) - How bond redemptions work (quantity=0 from T-Bank)
- **This File:** Quick reference

## 🔧 Modified Files

1. ✅ `constants.py` - New transaction types
2. ✅ `common/models.py` - New models and enhanced methods
3. ✅ `core/portfolio_utils.py` - Updated IRR calculation
4. ✅ `core/tinkoff_utils.py` - Bond redemption import
5. ✅ `migrations/0064_...py` - Database migration

## ⚠️ Breaking Changes

**IRR Values May Change**
If you have bonds with redemptions previously recorded as "Sell" transactions, IRR calculations will change after migration. This is correct behavior - the old method incorrectly treated redemptions as gains.

## 🧪 Testing Checklist

- [ ] Run migration successfully
- [ ] Add metadata to existing bonds
- [ ] Test IRR calculation with bonds
- [ ] Import bond redemptions from T-Bank (if applicable)
- [ ] Verify position calculations for amortizing bonds
- [ ] Check realized/unrealized gain calculations

## 💡 Common Use Cases

### Use Case 1: Regular Bullet Bond
```python
# Non-amortizing bond - no special handling needed
# Just set is_amortizing=False in metadata
```

### Use Case 2: Amortizing Mortgage Bond
```python
# Set is_amortizing=True
# Record each redemption with notional_change
# Update NotionalHistory after each redemption
```

### Use Case 3: Converting Old Redemptions
```python
# Find old "Sell" transactions that were actually redemptions
redemptions = Transactions.objects.filter(
    security__type='Bond',
    type='Sell',
    # Your criteria
)
# Update to new type
redemptions.update(type=TRANSACTION_TYPE_BOND_REDEMPTION)
```

## 🔮 Future Enhancements

Ready for implementation:
- ✨ Options trading support
- ✨ Futures contracts
- ✨ Complex derivatives
- ✨ Duration/convexity calculations
- ✨ Yield curve analysis

## 🐛 Troubleshooting

**Migration fails:**
- Check that migration 0063 is applied
- Verify database permissions

**IRR seems wrong:**
- Verify transaction types are correct
- Check notional_change is set for redemptions
- Ensure cash_flow values are accurate

**Position calculation incorrect:**
- Check is_amortizing flag in BondMetadata
- Verify NotionalHistory entries exist
- Ensure redemption transactions have quantity set

## 📞 Need Help?

1. Read the [full guide](./BOND_AMORTIZATION_GUIDE.md)
2. Check [implementation details](./IMPLEMENTATION_SUMMARY.md)
3. Review test examples in `tests/test_assets_model.py`
4. Examine models in `common/models.py` (lines 985-1210)

## ✨ Example: Complete Bond Lifecycle

```python
# 1. Buy bond
Transactions.objects.create(type='Buy', quantity=10, price=98.5, ...)

# 2. Receive coupons
Transactions.objects.create(type='Coupon', cash_flow=250, ...)

# 3. Partial redemption (if amortizing)
Transactions.objects.create(
    type=TRANSACTION_TYPE_BOND_REDEMPTION,
    quantity=-10,
    cash_flow=2000,
    notional_change=200,
    ...
)

# 4. More coupons (on reduced notional)
Transactions.objects.create(type='Coupon', cash_flow=200, ...)

# 5. Final maturity
Transactions.objects.create(
    type=TRANSACTION_TYPE_BOND_MATURITY,
    quantity=-10,
    cash_flow=8000,  # Remaining principal
    ...
)

# Calculate IRR - now accurate!
irr = IRR(user_id, date, currency, asset_id=bond.id)
```

---

**Status:** ✅ Ready for Production
**Version:** 1.0
**Date:** October 2, 2025

**Next Steps:**
1. Run migration: `python manage.py migrate common 0064`
2. Add metadata to existing bonds
3. Test with your bond portfolio
4. Review IRR calculations

Happy tracking! 📈
