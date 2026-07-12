"""Pricing and split-adjustment service.

Owns the price-lookup, valuation, and split-adjustment logic that previously
lived on the ``Assets`` model:

- :func:`price_at_date` returns the latest ``Prices`` row on or before a date,
  falling back to the last transaction's price, and optionally FX-converting.
- :func:`calculate_value_at_date` returns ``position * price`` (bonds use
  ``position * price * notional / 100``).
- :func:`get_cumulative_split_factor` multiplies ``adjustment_factor`` over
  the relevant ``split_history`` rows.
- :func:`get_split_adjusted_price` multiplies a historical price by the
  cumulative split factor.
- :func:`reverse_split_adjustment` divides an adjusted price by the cumulative
  factor (inverse of :func:`get_split_adjusted_price`).

Parameter names and positions are preserved verbatim from the original model
methods so that existing keyword-argument callers (tests, views, core utils)
keep working unchanged after switching to ``func(asset, ...)``.

Numeric safety: ``Decimal`` everywhere for prices. Never ``float``.

Circular-import notes:
- ``services.fx`` imports ``common.models.FX`` at its top level, but it does
  not import this module, so importing ``get_rate`` here at the top level is
  safe.
- ``services.positions`` does not import this module or ``common.models`` at
  its top level (the asset is passed in by callers), so importing
  ``position`` here at the top level is safe.
- ``common.models`` imports this module lazily (deferred, inside method
  bodies) because importing it at module top level would also pull in
  ``services.fx``, which needs ``common.models.FX``.
"""

import logging
from decimal import Decimal

from services.fx import get_rate as _fx_get_rate
from services.positions import position as _positions_position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# price_at_date
# ---------------------------------------------------------------------------


def price_at_date(asset, price_date, currency=None):
    """Get the price of an asset at a given date.

    Args:
        asset: The ``Assets`` instance.
        price_date: Date/datetime to look the price up as of.
        currency: Optional currency to FX-convert the price into. Bonds are
            never FX-converted here (their price is a percentage of par).

    Returns:
        A lightweight object with ``.price`` and ``.date`` attributes, or
        ``None`` when neither a ``Prices`` quote nor a fallback transaction
        price is available.
    """
    logger.debug(f"Fetching price for {asset.name} as of {price_date} in currency {currency}")
    # Use date directly for query (now using naive datetime objects)
    quote = asset.prices.filter(date__lte=price_date).order_by("-date").first()
    if quote is None:
        # If no quote is found, take the price from the last transaction
        last_transaction = (
            asset.transactions.filter(date__date__lte=price_date, quantity__isnull=False)
            .order_by("-date")
            .first()
        )
        if last_transaction:
            logger.debug(
                f"Using last transaction price for {asset.name} "
                f"as of {last_transaction.date}"
            )
            quote = type(
                "obj",
                (object,),
                {"price": last_transaction.price, "date": last_transaction.date},
            )
        else:
            logger.warning(f"No transaction found for {asset.name} as of {price_date}")
            return None

    if currency is not None:
        if asset.is_bond:
            fx_rate = Decimal(1)
        else:
            fx_rate = _fx_get_rate(asset.currency, currency, price_date)["FX"]

        logger.debug(
            f"Converting price from {asset.currency} to {currency} " f"using FX rate {fx_rate}"
        )
        quote.price = quote.price * fx_rate
    logger.debug(
        f"Price for {asset.name} as of {quote.date} is {quote.price} "
        f"in currency {currency or asset.currency}"
    )
    return quote


# ---------------------------------------------------------------------------
# calculate_value_at_date
# ---------------------------------------------------------------------------


def calculate_value_at_date(asset, date, investor, currency=None, account_ids=None):
    """Calculate the market value of an asset at a given date.

    For bonds, this accounts for the effective notional value.
    For other assets, this is simply position * price.

    Args:
        asset: The ``Assets`` instance.
        date: The date for which to calculate value.
        investor: The investor who owns the asset.
        currency: Optional currency for conversion.
        account_ids: Optional list of account IDs to filter by.

    Returns:
        Decimal: The calculated market value.
    """
    position = _positions_position(asset, date, investor, account_ids)
    if position == 0:
        return Decimal(0)

    price_quote = price_at_date(asset, date, currency)
    if price_quote is None:
        logger.warning(f"No price found for {asset.name} at {date}")
        return Decimal(0)

    price = price_quote.price  # For bonds: percentage of par

    # For bonds: value = position * (price% / 100) * notional
    # For others: value = position * price
    if asset.is_bond:
        effective_notional = asset.get_effective_notional(date, investor, account_ids, currency)
        value = position * price * effective_notional / Decimal(100)
        logger.debug(
            f"Bond value calculation for {asset.name}: "
            f"position={position}, price%={price}, notional={effective_notional}, "
            f"value={value}"
        )
    else:
        value = position * price
        logger.debug(
            f"Standard value calculation for {asset.name}: "
            f"position={position}, price={price}, value={value}"
        )

    return value


# ---------------------------------------------------------------------------
# get_cumulative_split_factor
# ---------------------------------------------------------------------------


def get_cumulative_split_factor(asset, from_date, to_date=None):
    """Get the cumulative split adjustment factor between two dates.

    This is used to adjust historical prices. For example, if there was a
    2:1 split, historical prices should be multiplied by 0.5 to compare
    with current prices.

    Args:
        asset: The ``Assets`` instance.
        from_date: The historical date (price date).
        to_date: The reference date (usually today). If None, uses all
            splits after ``from_date``.

    Returns:
        Decimal: The cumulative adjustment factor. Multiply historical
        prices by this to get equivalent current prices.
    """
    query = asset.split_history.filter(date__gt=from_date)
    if to_date:
        query = query.filter(date__lte=to_date)

    splits = query.values_list("adjustment_factor", flat=True)

    factor = Decimal("1")
    for split_factor in splits:
        factor *= split_factor

    return factor


# ---------------------------------------------------------------------------
# get_split_adjusted_price
# ---------------------------------------------------------------------------


def get_split_adjusted_price(asset, price, price_date, target_date=None):
    """Adjust a historical price for splits that occurred after the price date.

    Args:
        asset: The ``Assets`` instance.
        price: The historical price to adjust.
        price_date: The date of the historical price.
        target_date: The date to adjust to (default: None = adjust for all
            subsequent splits).

    Returns:
        Decimal: The split-adjusted price.
    """
    if price is None:
        return None

    factor = get_cumulative_split_factor(asset, price_date, target_date)
    return price * factor


# ---------------------------------------------------------------------------
# reverse_split_adjustment
# ---------------------------------------------------------------------------


def reverse_split_adjustment(asset, adjusted_price, price_date):
    """Reverse the split adjustment to get the actual historical price.

    T-Bank provides split-adjusted prices. To store actual historical prices,
    we need to reverse this adjustment.

    Args:
        asset: The ``Assets`` instance.
        adjusted_price: The split-adjusted price (from T-Bank).
        price_date: The date of the price.

    Returns:
        Decimal: The actual (non-adjusted) historical price.
    """
    if adjusted_price is None:
        return None

    factor = get_cumulative_split_factor(asset, price_date)
    if factor == Decimal("0"):
        return adjusted_price

    # Reverse the adjustment: if factor is 0.5 (2:1 split),
    # the actual pre-split price was 2x the adjusted price
    return adjusted_price / factor
