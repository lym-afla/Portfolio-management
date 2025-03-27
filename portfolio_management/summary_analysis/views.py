import logging
from datetime import date, datetime
from decimal import Decimal

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.models import Accounts, Assets, Transactions
from core.formatting_utils import currency_format, format_percentage, format_table_data
from core.portfolio_utils import get_fx_rate
from core.summary_utils import accounts_summary_data

logger = logging.getLogger(__name__)


class SummaryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["GET"])
    def summary_data(self, request):
        user = request.user
        effective_current_date = datetime.strptime(
            request.session.get("effective_current_date", datetime.now().strftime("%Y-%m-%d")),
            "%Y-%m-%d",
        ).date()
        currency_target = user.default_currency
        number_of_digits = user.digits

        summary_data = accounts_summary_data(
            user, effective_current_date, "all", None, currency_target, number_of_digits
        )

        # Format the data
        formatted_data = {
            "public_markets_context": format_table_data(
                summary_data["public_markets_context"], currency_target, number_of_digits
            ),
            "restricted_investments_context": format_table_data(
                summary_data["restricted_investments_context"], currency_target, number_of_digits
            ),
            "total_context": format_table_data(
                summary_data["total_context"], currency_target, number_of_digits
            ),
        }

        return Response(formatted_data)

    @action(detail=False, methods=["GET"])
    def portfolio_breakdown(self, request):
        user = request.user
        timespan = request.GET.get("year")
        effective_current_date = datetime.strptime(
            request.session.get("effective_current_date", datetime.now().strftime("%Y-%m-%d")),
            "%Y-%m-%d",
        ).date()
        currency_target = user.default_currency
        number_of_digits = user.digits

        # Reuse the logic from exposure_table_update
        start_date, end_date = self.get_date_range(timespan, effective_current_date)

        # Get the data using the existing logic
        context = self.get_exposure_table_data(
            user, start_date, end_date, currency_target, number_of_digits
        )

        return Response(context)

    def get_date_range(self, timespan, effective_current_date):
        if timespan == "ytd":
            start_date = date(effective_current_date.year, 1, 1)
            end_date = effective_current_date
        elif timespan == "all_time":
            start_date = None
            end_date = effective_current_date
        else:
            start_date = date(int(timespan), 1, 1)
            end_date = date(int(timespan), 12, 31)
        return start_date, end_date

    def get_exposure_table_data(
        self, user, start_date, end_date, currency_target, number_of_digits
    ):
        account_ids = Accounts.objects.filter(broker__investor=user).values_list("id", flat=True)
        assets = Assets.objects.filter(investors=user)

        # Initialize dictionaries to store the data for each category
        categories = ["Consolidated", "Unrestricted", "Restricted"]
        data = {category: {} for category in categories}

        for category in categories:
            data[category] = {
                "Equity - Int'l": {
                    "cost": 0,
                    "unrealized": 0,
                    "market_value": 0,
                    "realized": 0,
                    "capital_distribution": 0,
                    "commission": 0,
                },
                "Equity - RU": {
                    "cost": 0,
                    "unrealized": 0,
                    "market_value": 0,
                    "realized": 0,
                    "capital_distribution": 0,
                    "commission": 0,
                },
                "Fixed income - Int'l": {
                    "cost": 0,
                    "unrealized": 0,
                    "market_value": 0,
                    "realized": 0,
                    "capital_distribution": 0,
                    "commission": 0,
                },
                "Fixed income - RU": {
                    "cost": 0,
                    "unrealized": 0,
                    "market_value": 0,
                    "realized": 0,
                    "capital_distribution": 0,
                    "commission": 0,
                },
                "Options": {
                    "cost": 0,
                    "unrealized": 0,
                    "market_value": 0,
                    "realized": 0,
                    "capital_distribution": 0,
                    "commission": 0,
                },
                "Other": {
                    "cost": 0,
                    "unrealized": 0,
                    "market_value": 0,
                    "realized": 0,
                    "capital_distribution": 0,
                    "commission": 0,
                },
                "Cash": {"market_value": 0, "commission": 0},
            }

        totals = {
            category: {
                "cost": 0,
                "unrealized": 0,
                "market_value": 0,
                "realized": 0,
                "capital_distribution": 0,
                "commission": 0,
            }
            for category in categories
        }

        # Calculate values for each asset
        for asset in assets:
            asset_category = self.categorize_asset(asset)

            # Calculate values
            asset.current_position = asset.position(end_date, user, account_ids)
            asset.entry_price = asset.calculate_buy_in_price(
                end_date, user, currency_target, account_ids, start_date
            ) or Decimal(0)
            cost = round(asset.entry_price * asset.current_position, 2)

            asset.current_price = Decimal(
                getattr(asset.price_at_date(end_date, currency_target), "price", 0)
            )
            market_value = round(asset.current_price * asset.current_position, 2)

            unrealized = asset.unrealized_gain_loss(
                end_date, user, currency_target, account_ids, start_date
            )["total"]
            realized = asset.realized_gain_loss(
                end_date, user, currency_target, account_ids, start_date
            )["all_time"]["total"]
            capital_distribution = asset.get_capital_distribution(
                end_date, user, currency_target, account_ids, start_date
            )
            commission = asset.get_commission(
                end_date, user, currency_target, account_ids, start_date
            )

            for cat in ["Consolidated", "Restricted" if asset.restricted else "Unrestricted"]:
                data[cat][asset_category]["cost"] += cost
                data[cat][asset_category]["unrealized"] += unrealized
                data[cat][asset_category]["market_value"] += market_value
                data[cat][asset_category]["realized"] += realized
                data[cat][asset_category]["capital_distribution"] += capital_distribution
                data[cat][asset_category]["commission"] += commission

                totals[cat]["cost"] += cost
                totals[cat]["unrealized"] += unrealized
                totals[cat]["market_value"] += market_value
                totals[cat]["realized"] += realized
                totals[cat]["capital_distribution"] += capital_distribution
                totals[cat]["commission"] += commission

        # Calculate cash for all accounts
        accounts = Accounts.objects.filter(broker__investor=user)
        for account in accounts:
            category = "Restricted" if account.restricted else "Unrestricted"
            cash_balances = account.balance(end_date).items()
            for currency, balance in cash_balances:
                fx_rate = get_fx_rate(currency, currency_target, end_date, user)
                balance_to_add = Decimal(round(balance * fx_rate, 2))
                for cat in ["Consolidated", category]:
                    data[cat]["Cash"]["market_value"] += balance_to_add
                    totals[cat]["market_value"] += balance_to_add

            commission_transactions = Transactions.objects.filter(
                investor=user,
                account=account,
                security__isnull=True,
                commission__isnull=False,
                date__range=[start_date, end_date] if start_date else [None, end_date],
            ).values("date", "currency", "commission")

            for transaction in commission_transactions:
                fx_rate = get_fx_rate(
                    transaction["currency"], currency_target, transaction["date"], user
                )
                commission_to_add = Decimal(round(transaction["commission"] * fx_rate, 2))
                for cat in ["Consolidated", category]:
                    data[cat]["Cash"]["commission"] += commission_to_add
                    totals[cat]["commission"] += commission_to_add

        # Prepare context for the template
        context = {
            "consolidated_context": [],
            "unrestricted_context": [],
            "restricted_context": [],
        }

        for category in categories:
            for asset_category, values in data[category].items():
                line = self.prepare_line_data(
                    asset_category, values, currency_target, number_of_digits
                )
                context[f"{category.lower()}_context"].append(line)

        # Calculate portfolio percentages
        for category in categories:
            total_market_value = sum(
                line["market_value"] for line in context[f"{category.lower()}_context"]
            )
            for line in context[f"{category.lower()}_context"]:
                line["portfolio_percent"] = format_percentage(
                    line["market_value"] / total_market_value if total_market_value else 0, digits=1
                )
                line["market_value"] = currency_format(
                    line["market_value"], currency_target, number_of_digits
                )

        # Adding totals to the context
        for category in categories:
            total_line = self.prepare_total_line(
                totals[category], currency_target, number_of_digits
            )
            context[f"{category.lower()}_context"].append(total_line)

        return context

    def categorize_asset(self, asset):
        if asset.exposure == "Equity":
            return "Equity - RU" if asset.currency == "RUB" else "Equity - Int'l"
        elif asset.exposure == "FI":
            return "Fixed income - RU" if asset.currency == "RUB" else "Fixed income - Int'l"
        elif asset.exposure == "Options":
            return "Options"
        else:
            return "Other"

    def prepare_line_data(self, asset_category, values, currency_target, number_of_digits):
        if asset_category == "Cash":
            return {
                "name": asset_category,
                "cost": "",
                "unrealized": "",
                "unrealized_percent": "",
                "market_value": values["market_value"],
                "portfolio_percent": 0,
                "realized": "",
                "realized_percent": "",
                "capital_distribution": "",
                "capital_distribution_percent": "",
                "commission": currency_format(
                    values["commission"], currency_target, number_of_digits
                ),
                "commission_percent": "",
                "total": currency_format(values["commission"], currency_target, number_of_digits),
                "total_percent": "",
            }
        else:
            return {
                "name": asset_category,
                "cost": currency_format(values["cost"], currency_target, number_of_digits),
                "unrealized": currency_format(
                    values["unrealized"], currency_target, number_of_digits
                ),
                "unrealized_percent": format_percentage(
                    values["unrealized"] / values["cost"] if values["cost"] else 0, digits=1
                ),
                "market_value": values["market_value"],
                "portfolio_percent": 0,  # We'll calculate this after summing up all market values
                "realized": currency_format(values["realized"], currency_target, number_of_digits),
                "realized_percent": format_percentage(
                    (values["realized"] / values["cost"]) if values["cost"] else 0, digits=1
                ),
                "capital_distribution": currency_format(
                    values["capital_distribution"], currency_target, number_of_digits
                ),
                "capital_distribution_percent": format_percentage(
                    values["capital_distribution"] / values["cost"] if values["cost"] else 0,
                    digits=1,
                ),
                "commission": currency_format(
                    values["commission"], currency_target, number_of_digits
                ),
                "commission_percent": format_percentage(
                    values["commission"] / values["cost"] if values["cost"] else 0, digits=1
                ),
                "total": currency_format(
                    values["unrealized"]
                    + values["realized"]
                    + values["capital_distribution"]
                    + values["commission"],
                    currency_target,
                    number_of_digits,
                ),
                "total_percent": format_percentage(
                    (
                        values["unrealized"]
                        + values["realized"]
                        + values["capital_distribution"]
                        - values["commission"]
                    )
                    / values["cost"]
                    if values["cost"]
                    else 0,
                    digits=1,
                ),
            }

    def prepare_total_line(self, totals, currency_target, number_of_digits):
        return {
            "name": "TOTAL",
            "cost": currency_format(totals["cost"], currency_target, number_of_digits),
            "unrealized": currency_format(totals["unrealized"], currency_target, number_of_digits),
            "unrealized_percent": format_percentage(
                totals["unrealized"] / totals["cost"] if totals["cost"] else 0, digits=1
            ),
            "market_value": currency_format(
                totals["market_value"], currency_target, number_of_digits
            ),
            "portfolio_percent": "",
            "realized": currency_format(totals["realized"], currency_target, number_of_digits),
            "realized_percent": format_percentage(
                totals["realized"] / totals["cost"] if totals["cost"] else 0, digits=1
            ),
            "capital_distribution": currency_format(
                totals["capital_distribution"], currency_target, number_of_digits
            ),
            "capital_distribution_percent": format_percentage(
                totals["capital_distribution"] / totals["cost"] if totals["cost"] else 0, digits=1
            ),
            "commission": currency_format(totals["commission"], currency_target, number_of_digits),
            "commission_percent": format_percentage(
                totals["commission"] / totals["cost"] if totals["cost"] else 0, digits=1
            ),
            "total": currency_format(
                totals["unrealized"]
                + totals["realized"]
                + totals["capital_distribution"]
                + totals["commission"],
                currency_target,
                number_of_digits,
            ),
            "total_percent": format_percentage(
                (
                    totals["unrealized"]
                    + totals["realized"]
                    + totals["capital_distribution"]
                    - totals["commission"]
                )
                / totals["cost"]
                if totals["cost"]
                else 0,
                digits=1,
            ),
        }
