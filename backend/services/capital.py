"""Capital distribution and commission service.

Owns the capital-distribution and commission calculations that previously
lived as methods on the ``Assets`` model (``common.models``):

- :func:`get_capital_distribution` sums Dividend/Coupon cash flows, crypto
  reward values, bond ACI paid/received, and tax transactions; FX-converts
  each leg via :func:`services.fx.get_rate` when a target currency is
  requested.
- :func:`get_commission` aggregates the ``commission`` field over an asset's
  transactions, optionally FX-converted into a target currency.

Parameter names and positions are preserved verbatim from the original model
methods so that existing keyword-argument callers (tests, views, core utils)
keep working unchanged after switching to ``func(asset, ...)``. Only ``self``
becomes ``asset``.

Numeric safety: ``Decimal`` everywhere with ``ROUND_HALF_UP``. Never ``float``.

Import graph: this module imports from :mod:`services.fx` (one-way, no cycle).
``services.fx`` imports the ``FX`` model from ``common.models`` at its own top
level, but does not import this module, so the import is safe at module load
time. The asset is always passed in by callers, so there is no back-reference
to ``common.models`` here.
"""

import logging
from decimal import Decimal

from django.db.models import Q, Sum

from constants import TRANSACTION_TYPE_CRYPTO_REWARD
from services.fx import get_rate as _fx_get_rate
from services.transactions import reward_value as get_reward_value

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# get_capital_distribution
# ---------------------------------------------------------------------------


def get_capital_distribution(
    asset, date, investor, currency=None, account_ids=None, start_date=None
):
    """
    Calculate the capital distribution for this asset.

    Includes:
    - Dividends (for stocks/ETFs)
    - Coupons received (for bonds)
    - Net of ACI paid at bond acquisition (if any)
    - Taxes (paid on dividends/coupons)

    Note: For bonds, only coupons actually received are counted as capital distribution.
    ACI paid when buying bonds is netted against coupons. If no coupons received yet, returns zero. # noqa: E501
    """
    total_distributions = 0

    # Get dividend and coupon transactions
    query_date = date
    distribution_transactions = asset.transactions.filter(
        type__in=["Dividend", "Coupon"], date__date__lte=query_date, investor=investor
    )

    if account_ids is not None:
        distribution_transactions = distribution_transactions.filter(account_id__in=account_ids)

    if start_date is not None:
        query_start_date = start_date
        distribution_transactions = distribution_transactions.filter(
            date__date__gte=query_start_date
        )

    # Calculate dividends and coupons
    if distribution_transactions:
        if currency is None:
            total_distributions += (
                distribution_transactions.aggregate(total=Sum("cash_flow"))["total"] or 0
            )
        else:
            for transaction in distribution_transactions:
                fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)["FX"]
                if fx_rate:
                    total_distributions += transaction.cash_flow * fx_rate

    reward_transactions = asset.transactions.filter(
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date__date__lte=query_date,
        investor=investor,
    )

    if account_ids is not None:
        reward_transactions = reward_transactions.filter(account_id__in=account_ids)

    if start_date is not None:
        reward_transactions = reward_transactions.filter(date__date__gte=start_date)

    for transaction in reward_transactions:
        reward_value = get_reward_value(transaction)
        if currency is not None and transaction.currency != currency:
            fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)["FX"]
            if fx_rate:
                reward_value *= fx_rate
            else:
                continue
        total_distributions += reward_value

    # For bonds: subtract ACI paid at acquisition
    # (negative ACI from Buy transactions)
    if asset.is_bond:
        aci_transactions = asset.transactions.filter(
            ((Q(type="Buy") & Q(aci__lt=0)) | (Q(type="Sell") & Q(aci__gt=0))),
            date__date__lte=query_date,
            investor=investor,
        )

        if account_ids is not None:
            aci_transactions = aci_transactions.filter(account_id__in=account_ids)

        if start_date is not None:
            aci_transactions = aci_transactions.filter(date__gte=query_start_date)

        # Handle ACI paid and received
        if aci_transactions:
            if currency is None:
                total_distributions += (
                    aci_transactions.aggregate(total=Sum("aci"))["total"] or 0
                )
            else:
                for transaction in aci_transactions:
                    fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)[
                        "FX"
                    ]
                    if fx_rate:
                        total_distributions += transaction.aci * Decimal(fx_rate)

    # Get tax transactions (typically negative, reducing net distributions)
    tax_transactions = asset.transactions.filter(
        type="Tax", date__date__lte=date, investor=investor
    )

    if account_ids is not None:
        tax_transactions = tax_transactions.filter(account_id__in=account_ids)

    if start_date is not None:
        tax_transactions = tax_transactions.filter(date__gte=start_date)

    # Subtract taxes from total distributions
    if tax_transactions:
        if currency is None:
            total_distributions += (
                tax_transactions.aggregate(total=Sum("cash_flow"))["total"] or 0
            )
        else:
            for transaction in tax_transactions:
                fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)["FX"]
                if fx_rate:
                    total_distributions += transaction.cash_flow * fx_rate

    return round(Decimal(total_distributions), 2)


# ---------------------------------------------------------------------------
# get_commission
# ---------------------------------------------------------------------------


def get_commission(asset, date, investor, currency=None, account_ids=None, start_date=None):
    """Calculate the comission for this asset."""
    total_commission = 0
    query_date = date
    commission_transactions = asset.transactions.filter(
        commission__isnull=False, date__date__lte=query_date, investor=investor
    )

    if account_ids is not None:
        commission_transactions = commission_transactions.filter(account_id__in=account_ids)

    if start_date is not None:
        query_start_date = start_date
        commission_transactions = commission_transactions.filter(
            date__date__gte=query_start_date
        )

    if commission_transactions:
        if currency is None:
            total_commission += commission_transactions.aggregate(total=Sum("commission"))[
                "total"
            ]
        else:
            for commission in commission_transactions:
                fx_rate = _fx_get_rate(commission.currency, currency, commission.date)["FX"]
                if fx_rate:
                    total_commission += commission.commission * fx_rate
        return round(Decimal(total_commission), 2)
    else:
        return Decimal(0)
