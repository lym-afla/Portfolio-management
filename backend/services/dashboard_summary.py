"""Phase D reconciled dashboard statement — backend read model.

One cohesive, Decimal-only calculation that certifies, for the selected
accounts at the effective date in the reporting currency and since inception:

- canonical NAV (``services.nav.NAV_at_date``, with omission diagnostics);
- signed net invested capital (external ``Cash in`` / ``Cash out`` flows at
  their own-date FX, phantom in-kind asset-transfer rows included — legacy
  semantics preserved);
- the control total ``NAV - net invested capital``;
- mutually exclusive attributed components: realized price result, unrealized
  price result, gross income (dividends, coupons, interest, crypto rewards,
  bond ACI net), cash-hit fees (trade same-currency commissions, broker
  commission rows, FX-transaction commissions), taxes, and CERTIFIED FX
  (security FX from the engine's per-transaction decomposition + cash-flow FX
  = cash at EOP rates minus the same flows at their own-date rates);
- the unexplained difference against a documented raw tolerance, classified
  by :func:`classify_reconciliation`.

The residual FX in ``services.performance.calculate_performance`` (EoP minus
component sum, zeroed below 0.1) is NOT reused and that surface is unchanged.

Cancellation algebra (why the identity closes; single-currency case):

    GL_a        = value_now_a + SUM(proceeds_a) - SUM(injections_a)  (engine)
    balance     = netCapital + tradesCF + incomeRows + taxRows + feeRows
                  + redemptionCF + optionSettlementCF + fxLegs
    tradesCF    = -injections + tradeProceeds - ACI - sameCcyCommission
    control     = NAV - netCapital
                = SUM(GL) - SUM(proceeds) + SUM(injections) + balance

Redemption/option-settlement cash flows are engine proceeds, so they cancel
against SUM(proceeds); substituting tradesCF and grouping:

    control     = SUM(GL) + (incomeRows + ACI + rewards) + taxRows
                  + feeRows + fxCash + unknownRows
    fxCash      = balance(EOP rates) - flows(own-date rates)  [independent]

Multi-currency adds exactly ``fxCash``. Missing price/FX and structural gaps
(open options, unclassified in-kind transfers) are surfaced as partial states
and force ``reconciliation: incomplete`` — never a forced balance.

Numeric safety: ``Decimal`` everywhere; display strings come from
``core.formatting_utils.currency_format``. Raw values are exact fixed-point
strings; no float touches a financial value (``format_percentage`` floats
only inside an existing display helper).
"""

import logging
from datetime import date, datetime
from decimal import Decimal, DecimalException

from common.models import Accounts, Assets, FXTransaction, Transactions
from constants import (
    CASH_CURRENCIES,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)
from core.formatting_utils import currency_format, format_percentage
from services import options
from services.accounts import balance as account_balance
from services.crypto import is_crypto_code
from services.nav import IRR, NAV_at_date, get_fx_rate
from services.realized import (
    _cash_precision_for,
    _transfer_is_matched,
    realized_gain_loss,
    unrealized_gain_loss,
)
from services.transactions import (
    get_cash_flow_by_currency,
    reward_value as transaction_reward_value,
    total_cash_flow,
)

logger = logging.getLogger(__name__)

SUMMARY_CONTRACT_VERSION = 2

INCOME_TYPES = frozenset({
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_INTEREST_INCOME,
})
TRADE_TYPES = frozenset({
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
})
# Cash-bearing rows whose cash flow is also an engine proceeds term: they
# self-cancel in the algebra and must NOT become components.
PROCEEDS_LIKE_TYPES = TRADE_TYPES | {
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
}
TRANSFER_TYPES = [TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
                  TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT]

REASON_MISSING_PRICE = "missing_price"
REASON_MISSING_FX = "missing_fx"
REASON_OPTION_GAP = "option_unrealized_not_attributed"
REASON_IN_KIND = "in_kind_flows_unclassified"
REASON_COIN_FEE_GAP = "crypto_coin_fee_not_attributed"


class Component:
    """Accumulates one attributed component plus its completeness."""

    def __init__(self):
        self.value = Decimal(0)
        self.complete = True
        self.reasons = set()

    def add(self, value):
        self.value += value

    def fail(self, reason):
        self.complete = False
        self.reasons.add(reason)

    @property
    def first_reason(self):
        return sorted(self.reasons)[0] if self.reasons else None

    @property
    def status(self):
        return "ok" if self.complete else "partial"


def classify_reconciliation(control_total, attributed_sum, tolerance,
                            dependencies_complete):
    """Pure reconciliation classifier.

    Returns ``(outcome, reasons)``:

    - ``incomplete`` when any dependency (NAV, capital, a component) is
      partial — a certified bridge is not claimable even when the arithmetic
      closes;
    - ``unreconciled`` when every dependency is individually certified yet the
      attributed sum still misses the control total beyond tolerance — the
      difference stays visible and is never relabelled;
    - ``reconciled`` otherwise.
    """
    beyond = abs(control_total - attributed_sum) > tolerance
    if not dependencies_complete:
        return "incomplete", (["unexplained_difference"] if beyond else [])
    if beyond:
        return "unreconciled", ["unexplained_difference"]
    return "reconciled", []


def _amount(value, currency, digits, status="ok", reason=None,
            known_subtotal=None):
    """Build the wire amount: exact raw string + backend display string."""
    amount = {
        "raw": format(value, "f"),
        "display": currency_format(value, currency, digits),
        "status": status,
    }
    if reason is not None:
        amount["reason"] = reason
    if known_subtotal is not None:
        amount["knownSubtotal"] = format(known_subtotal, "f")
    return amount


def _component_amount(component, currency, digits):
    return _amount(component.value, currency, digits,
                   status=component.status, reason=component.first_reason)


def _fx_rate(source, target, when):
    """Canonical cached rate lookup (the same one ``NAV_at_date`` uses).
    Raises ValueError when the rate is unknown."""
    if isinstance(when, datetime):
        when = when.date()
    return get_fx_rate(source, target, when)


def _reconciliation_tolerance(asset_precisions, cash_precisions):
    """Documented raw tolerance: per asset 4 rounding half-ULPs (realized
    price/fx and unrealized price/fx are each quantized to the broker's cash
    precision by the engine), plus 1 half-ULP per cash currency for the
    balance re-quantization."""
    tolerance = Decimal(0)
    for precision in asset_precisions:
        tolerance += Decimal(4) * Decimal("0.5").scaleb(-int(precision))
    for precision in cash_precisions:
        tolerance += Decimal("0.5").scaleb(-int(precision))
    return tolerance


def _cash_precision_of_account(account):
    return int(getattr(getattr(account, "broker", None), "cash_precision", 2) or 2)


def _unavailable_return(reason, display="N/A"):
    return {"value": None, "display": display, "status": "not_available",
            "reason": reason}


def _zero_amount(currency, digits):
    return _amount(Decimal(0), currency, digits)


def build_reconciled_summary(user, effective_date, currency_target, digits,
                             account_ids):
    """Build the summaryV2 statement document (JSON-ready; Decimals stringified)."""
    context = {
        "accountSelection": {
            "type": user.selected_account_type,
            "id": user.selected_account_id,
        },
        "accountIds": list(account_ids),
        "effectiveDate": (
            effective_date.isoformat()
            if isinstance(effective_date, date) else str(effective_date)
        ),
        "currency": currency_target,
        "digits": int(digits),
    }

    if not account_ids:
        zero = _zero_amount(currency_target, digits)
        return {
            "version": SUMMARY_CONTRACT_VERSION,
            "kind": "statement",
            "context": context,
            "status": "unavailable",
            "reasons": ["no_accounts_selected"],
            "capital": {
                "invested": dict(zero),
                "cashOut": dict(zero),
                "netInvestedCapital": dict(zero),
            },
            "netResult": {
                "nav": dict(zero),
                "controlTotal": dict(zero),
                "components": {
                    "realizedPrice": dict(zero),
                    "unrealizedPrice": dict(zero),
                    "income": dict(zero),
                    "fees": dict(zero),
                    "taxes": dict(zero),
                    "fx": dict(zero),
                    "otherFlows": dict(zero),
                },
                "fxDetail": {"security": dict(zero), "cashFlows": dict(zero)},
                "attributedSum": dict(zero),
                "unexplainedDifference": dict(zero),
                "toleranceRaw": "0",
                "toleranceBasis": "No accounts in scope.",
                "reconciliation": "incomplete",
            },
            "returns": {
                "totalReturn": _unavailable_return("no_accounts_selected"),
                "irr": _unavailable_return("no_accounts_selected"),
            },
            "diagnostics": {
                "omittedValuations": [],
                "unclassifiedInKindFlows": {"present": False, "count": 0},
                "notes": [],
            },
        }

    reasons = set()
    coin_fee_gap = False
    nav_diagnostics = []
    analysis = NAV_at_date(
        user.id, tuple(account_ids), effective_date, currency_target,
        diagnostics=nav_diagnostics,
    )
    nav_known = analysis["Total NAV"]
    nav_status = "ok"
    for item in nav_diagnostics:
        nav_status = "partial"
        reasons.add(item.get("reason", REASON_MISSING_FX))

    # ------------------------------------------------------------------
    # Flow rows (single pass): capital, income, fees, taxes, other flows.
    # Crypto transfers are excluded here (handled as in-kind candidates);
    # their canonical cash flow is zero either way.
    # ------------------------------------------------------------------
    invested = Component()
    cash_out = Component()
    income = Component()
    fees = Component()
    taxes = Component()
    other_flows = Component()
    ledger = Component()  # every balance-affecting own-date flow (fxCash base)

    def own_value(value, row_currency, when, component):
        """Convert at the row's own-date rate; unknown rate => partial."""
        if value == 0:
            return Decimal(0)
        try:
            rate = _fx_rate(row_currency, currency_target, when)
        except ValueError:
            component.fail(REASON_MISSING_FX)
            reasons.add(REASON_MISSING_FX)
            return Decimal(0)
        return Decimal(value) * rate

    flow_rows = (
        Transactions.objects.filter(
            investor=user,
            account_id__in=account_ids,
            date__date__lte=effective_date,
        )
        .exclude(type__in=TRANSFER_TYPES)
        .select_related("account__broker", "security")
        .order_by("date", "id")
    )

    for row in flow_rows:
        row_type = row.type
        if row_type == TRANSACTION_TYPE_CRYPTO_REWARD:
            # Reward rows carry no cash flow; their income value is the
            # event-date USD value (crypto USD-price convention), converted
            # USD -> target at the event date. They never enter balances.
            income.add(own_value(transaction_reward_value(row), "USD",
                                 row.date, income))
            continue
        # Mirror services.accounts.balance: coin-settled option premiums in
        # non-cash currencies are not cash at all.
        if (
            row.security is not None
            and row.security.type == "Option"
            and (row.currency or "").upper() not in CASH_CURRENCIES
        ):
            continue
        cash_flow = total_cash_flow(row)
        if cash_flow == 0:
            continue
        if row_type == TRANSACTION_TYPE_CASH_IN:
            invested.add(own_value(cash_flow, row.currency, row.date, invested))
        elif row_type == TRANSACTION_TYPE_CASH_OUT:
            cash_out.add(own_value(cash_flow, row.currency, row.date, cash_out))
        elif row_type in INCOME_TYPES:
            income.add(own_value(cash_flow, row.currency, row.date, income))
        elif row_type == TRANSACTION_TYPE_TAX:
            taxes.add(own_value(cash_flow, row.currency, row.date, taxes))
        elif row_type == TRANSACTION_TYPE_BROKER_COMMISSION:
            fees.add(own_value(cash_flow, row.currency, row.date, fees))
        elif row_type in TRADE_TYPES:
            # Only the cash-embedded commission leg and ACI are components;
            # the price leg is engine basis/proceeds and self-cancels.
            if row.commission:
                commission_currency = (row.commission_currency or "").upper()
                if not commission_currency or commission_currency == (
                        row.currency or "").upper():
                    fees.add(own_value(row.commission, row.currency,
                                       row.date, fees))
                elif is_crypto_code(commission_currency):
                    # A coin-denominated fee depletes the coin POSITION (not
                    # cash); the unrealized engine values the raw quantity
                    # sum and therefore misses the burn. Known structural
                    # gap: declared here, never relabelled as FX.
                    reasons.add(REASON_COIN_FEE_GAP)
                    coin_fee_gap = True
            if row.aci:
                income.add(own_value(row.aci, row.currency, row.date, income))
        elif row_type in PROCEEDS_LIKE_TYPES:
            pass  # engine proceeds: self-cancels against SUM(proceeds)
        else:
            # Unknown cash-bearing family: attribute honestly as its own
            # component, never a silent residual.
            other_flows.add(own_value(cash_flow, row.currency, row.date,
                                      other_flows))
        ledger.add(own_value(cash_flow, row.currency, row.date, ledger))
    flows_own = ledger.value

    # FX transactions: the commission is a fee component; the from/to legs
    # are part of the cash ledger.
    fx_rows = FXTransaction.objects.filter(
        account_id__in=account_ids, date__date__lte=effective_date
    )
    for fx_row in fx_rows:
        if fx_row.commission:
            fees.add(own_value(fx_row.commission,
                               fx_row.commission_currency or "USD",
                               fx_row.date, fees))
        involved = {fx_row.from_currency, fx_row.to_currency}
        if fx_row.commission_currency:
            involved.add(fx_row.commission_currency)
        for currency_code in involved:
            leg = get_cash_flow_by_currency(fx_row, currency_code)
            flows_own += own_value(leg, currency_code, fx_row.date, ledger)

    # ------------------------------------------------------------------
    # Cash balances at EOP rates (canonical path) -> certified cash FX.
    # ------------------------------------------------------------------
    accounts = Accounts.objects.filter(
        id__in=account_ids, broker__investor=user
    ).select_related("broker")

    cash_eop = Decimal(0)
    cash_component = Component()
    cash_precisions = set()
    balances_by_currency = {}
    for account in accounts:
        cash_precisions.add(_cash_precision_of_account(account))
        for currency_code, balance_value in account_balance(
                account, effective_date).items():
            balances_by_currency[currency_code] = (
                balances_by_currency.get(currency_code, Decimal(0)) + balance_value
            )
    for currency_code, balance_value in balances_by_currency.items():
        try:
            rate = _fx_rate(currency_code, currency_target, effective_date)
        except ValueError:
            cash_component.fail(REASON_MISSING_FX)
            reasons.add(REASON_MISSING_FX)
            continue
        cash_eop += balance_value * rate

    fxcash = cash_eop - flows_own

    # ------------------------------------------------------------------
    # Per-asset engine decomposition over every asset with quantity activity
    # in scope (open AND fully disposed — realized survives zero positions).
    # ------------------------------------------------------------------
    realized_price = Component()
    realized_fx = Component()
    unrealized_price = Component()
    unrealized_fx = Component()
    asset_precisions = []

    candidates = Assets.objects.filter(
        transactions__investor=user,
        transactions__account_id__in=account_ids,
        transactions__date__date__lte=effective_date,
        transactions__quantity__isnull=False,
    ).distinct()

    from services.pricing import price_at_date as pricing_price_at_date
    from services.positions import position as positions_position

    for asset in candidates:
        asset_precisions.append(_cash_precision_for(asset, account_ids))
        open_option = options.is_option_asset(asset)
        if open_option:
            if positions_position(asset, effective_date, user,
                                  account_ids) != 0:
                reasons.add(REASON_OPTION_GAP)
                unrealized_price.fail(REASON_OPTION_GAP)
                unrealized_fx.fail(REASON_OPTION_GAP)
        else:
            try:
                pricing_price_at_date(asset, effective_date, currency_target)
            except ValueError:
                unrealized_price.fail(REASON_MISSING_PRICE)
                unrealized_fx.fail(REASON_MISSING_PRICE)
                reasons.add(REASON_MISSING_PRICE)

        try:
            realized = realized_gain_loss(
                asset, effective_date, user, currency_target,
                account_ids=account_ids, start_date=None,
            )
        except ValueError:
            # Engine paths raise on unpriced crypto (rate/price lookups);
            # unknown is never zero — the asset's contribution is partial.
            realized = None
            realized_price.fail(REASON_MISSING_PRICE)
            realized_fx.fail(REASON_MISSING_PRICE)
            reasons.add(REASON_MISSING_PRICE)
        if realized is not None:
            realized_price.add(realized["all_time"]["price_appreciation"])
            realized_fx.add(realized["all_time"]["fx_effect"])

        if open_option or realized is None:
            if open_option:
                continue  # engine unrealized is zeros for options by design
            continue
        try:
            unrealized = unrealized_gain_loss(
                asset, effective_date, user, currency_target,
                account_ids=account_ids, start_date=None,
            )
        except ValueError:
            unrealized = None
            unrealized_price.fail(REASON_MISSING_PRICE)
            unrealized_fx.fail(REASON_MISSING_PRICE)
            reasons.add(REASON_MISSING_PRICE)
        if unrealized is not None:
            unrealized_price.add(unrealized["price_appreciation"])
            unrealized_fx.add(unrealized["fx_effect"])

    # ------------------------------------------------------------------
    # Unclassified external (unmatched) crypto transfers in scope.
    # ------------------------------------------------------------------
    in_kind_count = 0
    in_kind_signed_fmv = Decimal(0)
    in_kind_fmv_known = True
    transfer_rows = Transactions.objects.filter(
        investor=user,
        account_id__in=account_ids,
        date__date__lte=effective_date,
        type__in=TRANSFER_TYPES,
    ).select_related("security")
    for transfer in transfer_rows:
        if _transfer_is_matched(transfer, user, account_ids):
            continue
        in_kind_count += 1
        sign = (Decimal(1) if transfer.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
                else Decimal(-1))
        if transfer.price is not None and transfer.quantity is not None:
            # Transfer rows carry the coin's USD spot price (crypto
            # convention): FMV = |qty| x price in USD.
            fmv_usd = abs(transfer.quantity) * transfer.price
            in_kind_signed_fmv += sign * own_value(
                fmv_usd, "USD", transfer.date, Component())
        else:
            in_kind_fmv_known = False
    in_kind_present = in_kind_count > 0
    if in_kind_present:
        reasons.add(REASON_IN_KIND)

    # ------------------------------------------------------------------
    # Statement totals and classification.
    # ------------------------------------------------------------------
    fx_security = realized_fx.value + unrealized_fx.value
    fx_total = fx_security + fxcash
    net_capital = invested.value + cash_out.value
    control_total = nav_known - net_capital
    attributed = (
        realized_price.value
        + realized_fx.value
        + unrealized_price.value
        + unrealized_fx.value
        + income.value
        + fees.value
        + taxes.value
        + fxcash
        + other_flows.value
    )
    unexplained = control_total - attributed
    tolerance = _reconciliation_tolerance(asset_precisions, cash_precisions)

    capital_complete = invested.complete and cash_out.complete
    dependencies_complete = (
        nav_status == "ok"
        and capital_complete
        and income.complete and fees.complete and taxes.complete
        and other_flows.complete and cash_component.complete
        and realized_price.complete and realized_fx.complete
        and unrealized_price.complete and unrealized_fx.complete
        and not in_kind_present
        and not coin_fee_gap
    )
    outcome, classifier_reasons = classify_reconciliation(
        control_total, attributed, tolerance, dependencies_complete
    )
    reasons.update(classifier_reasons)

    statement_status = "complete"
    if outcome != "reconciled" or nav_status != "ok" or not (
            capital_complete and income.complete and fees.complete
            and taxes.complete and other_flows.complete):
        statement_status = "partial"

    fx_status = ("ok" if realized_fx.complete and unrealized_fx.complete
                 and cash_component.complete else "partial")
    fx_reason = (None if fx_status == "ok" else (
        realized_fx.first_reason or unrealized_fx.first_reason
        or cash_component.first_reason))

    document = {
        "version": SUMMARY_CONTRACT_VERSION,
        "kind": "statement",
        "context": context,
        "status": statement_status,
        "reasons": sorted(reasons),
        "capital": {
            "invested": _component_amount(invested, currency_target, digits),
            "cashOut": _component_amount(cash_out, currency_target, digits),
            "netInvestedCapital": _amount(
                net_capital, currency_target, digits,
                status="ok" if capital_complete else "partial",
                reason=None if capital_complete else
                (invested.first_reason or cash_out.first_reason),
            ),
        },
        "netResult": {
            "nav": _amount(
                nav_known, currency_target, digits, status=nav_status,
                known_subtotal=nav_known if nav_status == "partial" else None,
            ),
            "controlTotal": _amount(
                control_total, currency_target, digits,
                status="ok" if dependencies_complete else "partial",
                reason=None if dependencies_complete else sorted(reasons)[0],
            ),
            "components": {
                "realizedPrice": _component_amount(
                    realized_price, currency_target, digits),
                "unrealizedPrice": _component_amount(
                    unrealized_price, currency_target, digits),
                "income": _component_amount(income, currency_target, digits),
                "fees": _component_amount(fees, currency_target, digits),
                "taxes": _component_amount(taxes, currency_target, digits),
                "fx": _amount(fx_total, currency_target, digits,
                              status=fx_status, reason=fx_reason),
                "otherFlows": _component_amount(
                    other_flows, currency_target, digits),
            },
            "fxDetail": {
                "security": _amount(
                    fx_security, currency_target, digits,
                    status=("ok" if realized_fx.complete
                            and unrealized_fx.complete else "partial"),
                    reason=(None if realized_fx.complete
                            and unrealized_fx.complete else
                            (realized_fx.first_reason
                             or unrealized_fx.first_reason)),
                ),
                "cashFlows": _component_amount(
                    cash_component, currency_target, digits)
                if cash_component.value != 0 or not cash_component.complete
                else _amount(fxcash, currency_target, digits,
                             status=cash_component.status,
                             reason=cash_component.first_reason),
            },
            "attributedSum": _amount(attributed, currency_target, digits),
            "unexplainedDifference": _amount(unexplained, currency_target,
                                             digits),
            "toleranceRaw": format(tolerance, "f"),
            "toleranceBasis": (
                "Sum of rounding half-ULPs: 4 per asset (realized/unrealized "
                "price and fx at broker cash precision) plus 1 per cash "
                "currency balance re-quantization."
            ),
            "reconciliation": outcome,
        },
        "returns": _build_returns(
            user, effective_date, currency_target, digits, account_ids,
            nav_known, nav_status, invested, cash_out, capital_complete,
        ),
        "diagnostics": {
            "omittedValuations": [dict(item) for item in nav_diagnostics],
            "unclassifiedInKindFlows": {
                "present": in_kind_present,
                "count": in_kind_count,
                **({"signedFmv": format(in_kind_signed_fmv, "f")}
                   if in_kind_present and in_kind_fmv_known else {}),
                **({"fmvKnown": False} if not in_kind_fmv_known else {}),
            },
            "notes": [],
        },
    }
    return document


def _build_returns(user, effective_date, currency_target, digits, account_ids,
                   nav_known, nav_status, invested, cash_out, capital_complete):
    """Legacy total-return formula + canonical since-inception IRR.

    Total return keeps the incumbent summary definition
    ``(NAV - Cash-out) / Invested - 1`` (null when invested is zero); the
    approved mock's alternative (net result / invested) is a financial-review
    decision and is deliberately NOT adopted here.
    """
    total_return = _unavailable_return("zero_invested_capital")
    if capital_complete and invested.value != 0:
        try:
            ratio = (nav_known - cash_out.value) / invested.value - 1
            status = "ok" if nav_status == "ok" else "partial"
            total_return = {
                "value": format(ratio, "f"),
                "display": format_percentage(ratio, digits=1),
                "status": status,
                "reason": "observed" if status == "ok" else "omitted_valuations",
            }
        except (ZeroDivisionError, DecimalException):
            pass

    try:
        irr_result = IRR(
            user.id, effective_date, currency_target,
            asset_id=None, account_ids=account_ids, cached_nav=nav_known,
        )
    except ValueError:
        # An unknown rate on a flow row (e.g. a cash currency with no FX
        # data) makes the IRR uncertifiable — unknown, never zero.
        return {
            "totalReturn": total_return,
            "irr": _unavailable_return(REASON_MISSING_FX),
        }
    except Exception:
        logger.exception("IRR calculation failed for the summary statement")
        return {
            "totalReturn": total_return,
            "irr": _unavailable_return("solver_unavailable"),
        }
    if isinstance(irr_result, Decimal):
        status = "ok" if nav_status == "ok" else "partial"
        irr = {
            "value": format(irr_result, "f") if status == "ok" else None,
            "display": format_percentage(irr_result, digits=1),
            "status": status,
            "reason": "observed" if status == "ok" else "omitted_valuations",
        }
    elif irr_result == "N/A":
        irr = _unavailable_return("solver_unavailable")
    else:  # 'N/R'
        irr = _unavailable_return("not_relevant", display="N/R")
    return {"totalReturn": total_return, "irr": irr}
