import logging
from datetime import timedelta
from decimal import Decimal

import networkx as nx
import requests
import yfinance as yf
from django.db import models
from django.db.models import F, Sum

from constants import (
    ACCOUNT_TYPE_ALL,
    ACCOUNT_TYPE_CHOICES,
    ASSET_TYPE_CHOICES,
    CURRENCY_CHOICES,
    EXPOSURE_CHOICES,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CHOICES,
    TRANSACTION_TYPE_SELL,
)

# from .utils import update_FX_database
from users.models import CustomUser

logger = logging.getLogger(__name__)


# Table with FX data
class FX(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField(unique=True)
    investors = models.ManyToManyField(CustomUser, related_name="fx_rates")
    USDEUR = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    USDGBP = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    CHFGBP = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    RUBUSD = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    PLNUSD = models.DecimalField(max_digits=9, decimal_places=5, null=True, blank=True)

    class Meta:
        ordering = ["-date"]

    # Get FX quote for date
    @classmethod
    def get_rate(cls, source, target, date, investor=None):
        fx_rate = 1
        dates_async = False
        dates_list = []

        if source == target:
            return {
                "FX": fx_rate,
                "conversions": 0,
                "dates_async": dates_async,
                "FX dates used": dates_list,
            }

        # Get all existing pairs
        pairs_list = [
            field.name
            for field in FX._meta.get_fields()
            if field.name not in ["date", "id", "investors"]
        ]

        # Create undirected graph with currencies, import networkx library working with graphs
        G = nx.Graph()
        for entry in pairs_list:
            G.add_nodes_from([entry[:3], entry[3:]])
            G.add_edge(entry[:3], entry[3:])

        # Finding shortest path for cross-currency conversion using "Bellman-Ford" algorithm
        cross_currency = nx.shortest_path(G, source, target, method="bellman-ford")

        for i in range(1, len(cross_currency)):
            i_source = cross_currency[i - 1]
            i_target = cross_currency[i]

            for element in pairs_list:
                if i_source in element and i_target in element:
                    if element.find(i_source) == 0:
                        field_name = f"{i_source}{i_target}"
                        multiplier = Decimal("1")
                    else:
                        field_name = f"{i_target}{i_source}"
                        multiplier = Decimal("-1")

                    filter_kwargs = {f"{field_name}__isnull": False}
                    if investor is not None:
                        filter_kwargs["investors"] = investor

                    fx_call = (
                        cls.objects.filter(date__lte=date, **filter_kwargs)
                        .values("date", quote=F(field_name))
                        .order_by("-date")
                        .first()
                    )

                    if fx_call is None or fx_call["quote"] is None:
                        fx_call = (
                            cls.objects.filter(date__gte=date, **filter_kwargs)
                            .values("date", quote=F(field_name))
                            .order_by("date")
                            .first()
                        )
                        if fx_call is None or fx_call["quote"] is None:
                            raise ValueError(f"No FX rate found for {field_name} before {date}")

                    quote = Decimal(str(fx_call["quote"]))
                    if multiplier == Decimal("1"):
                        fx_rate *= quote
                    else:
                        fx_rate /= quote
                    dates_list.append(fx_call["date"])
                    dates_async = (dates_list[0] != fx_call["date"]) or dates_async
                    break

        # The target is to multiply when using, not divide
        fx_rate = round(Decimal(1 / fx_rate), 6)

        return {
            "FX": fx_rate,
            "conversions": len(cross_currency) - 1,
            "dates_async": dates_async,
            "dates": dates_list,
        }

    @classmethod
    def update_fx_rate(cls, date, investor):
        # Get FX model variables, except 'date', 'id' and 'investors'
        fx_variables = [
            field
            for field in cls._meta.get_fields()
            if field.name not in ["date", "id", "investors"]
        ]

        # Extract source and target currencies
        currency_pairs = [(field.name[:3], field.name[3:]) for field in fx_variables]

        # Create or get the fx_instance once before the loop
        fx_instance, created = cls.objects.get_or_create(date=date)
        fx_instance.investors.add(investor)

        for source, target in currency_pairs:
            # Check if an FX rate exists for the date and currency pair
            existing_rate = getattr(fx_instance, f"{source}{target}", None)

            if existing_rate is None:
                # Get the FX rate for the dateaxio
                try:
                    rate_data = update_FX_from_Yahoo(source, target, date)

                    if rate_data is not None:
                        # Update the fx_instance with the new rate
                        setattr(fx_instance, f"{source}{target}", rate_data["exchange_rate"])
                except Exception:
                    print(
                        f"{source}{target} for {date} is NOT updated. "
                        "Yahoo Finance is not responding correctly"
                    )
                    continue

        # Save the fx_instance once after updating all currency pairs
        fx_instance.save()

    @classmethod
    def get_investor_fx_entries(cls, investor):
        return cls.objects.filter(investors=investor)


# Brokers
class Brokers(models.Model):
    """Represents a broker entity (e.g., Tinkoff, Interactive Brokers)"""

    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="brokers")
    name = models.CharField(max_length=30, null=False)
    country = models.CharField(max_length=20)
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["investor", "name"]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Accounts(models.Model):
    """Represents a specific account at a broker"""

    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, related_name="accounts")
    native_id = models.CharField(
        max_length=100, help_text="Native account ID from broker's system", null=True, blank=True
    )
    name = models.CharField(max_length=100, help_text="Account name or description")
    restricted = models.BooleanField(default=False, null=False, blank=False)
    comment = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["broker", "native_id"]
        ordering = ["broker", "name"]

    def __str__(self):
        return f"Account: {self.name}"

    @property
    def full_name(self):
        return f"{self.broker.name} - {self.name}"

    # List of currencies used
    def get_currencies(self):
        currencies = set()
        for transaction in self.transactions.all():
            currencies.add(transaction.currency)
        return currencies

    # Cash balance at date
    def balance(self, date):
        balance = {}

        # This approach in order to match how balances are calculated
        # in 'transactions' app after each transaction
        transactions = self.transactions.filter(date__lte=date)
        for transaction in transactions:
            balance[transaction.currency] = balance.get(transaction.currency, Decimal(0)) - Decimal(
                (transaction.price or Decimal(0)) * Decimal(transaction.quantity or Decimal(0))
                - Decimal(transaction.cash_flow or Decimal(0))
                - Decimal(transaction.commission or Decimal(0))
            )

        # Calculate balance from FX transactions
        fx_transactions = self.fx_transactions.filter(date__lte=date)
        for fx_transaction in fx_transactions:
            balance[fx_transaction.from_currency] = (
                balance.get(fx_transaction.from_currency, Decimal(0)) - fx_transaction.from_amount
            )
            balance[fx_transaction.to_currency] = (
                balance.get(fx_transaction.to_currency, Decimal(0)) + fx_transaction.to_amount
            )
            if fx_transaction.commission:
                balance[fx_transaction.commission_currency] = (
                    balance.get(fx_transaction.commission_currency, Decimal(0))
                    + fx_transaction.commission
                )

        for key, value in balance.items():
            balance[key] = round(Decimal(value), 2)

        return balance


# Public assets
class Assets(models.Model):
    investors = models.ManyToManyField(CustomUser, related_name="assets", blank=True)
    type = models.CharField(max_length=15, choices=ASSET_TYPE_CHOICES, null=False)
    ISIN = models.CharField(max_length=12)
    name = models.CharField(max_length=70, null=False)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD", null=False)
    exposure = models.TextField(null=False, choices=EXPOSURE_CHOICES, default="Equity")
    restricted = models.BooleanField(default=False, null=False)
    comment = models.TextField(null=True, blank=True)
    DATA_SOURCE_CHOICES = [
        ("FT", "Financial Times"),
        ("YAHOO", "Yahoo Finance"),
        ("MICEX", "MICEX")
        # Add more sources as needed
    ]
    data_source = models.CharField(
        max_length=10, choices=[("", "None")] + DATA_SOURCE_CHOICES, blank=True, null=True
    )
    update_link = models.URLField(null=True, blank=True)  # For FT
    yahoo_symbol = models.CharField(
        max_length=50, blank=True, null=True
    )  # For Yahoo Finance symbol
    fund_fee = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    secid = models.CharField(max_length=10, null=True, blank=True)  # For MICEX

    # Returns price at the date or latest available before the date
    def price_at_date(self, price_date, currency=None):
        logger.debug(f"Fetching price for {self.name} as of {price_date} in currency {currency}")
        quote = self.prices.filter(date__lte=price_date).order_by("-date").first()
        if quote is None:
            # If no quote is found, take the price from the last transaction
            last_transaction = (
                self.transactions.filter(date__lte=price_date, quantity__isnull=False)
                .order_by("-date")
                .first()
            )
            if last_transaction:
                logger.debug(
                    f"Using last transaction price for {self.name} as of {last_transaction.date}"
                )
                quote = type(
                    "obj",
                    (object,),
                    {"price": last_transaction.price, "date": last_transaction.date},
                )
            else:
                logger.error(f"No transaction found for {self.name} as of {price_date}")
                return None

        if currency is not None:
            fx_rate = FX.get_rate(self.currency, currency, price_date)["FX"]
            logger.debug(
                f"Converting price from {self.currency} to {currency} using FX rate {fx_rate}"
            )
            quote.price = quote.price * fx_rate
        logger.debug(
            f"Price for {self.name} as of {quote.date} is {quote.price} "
            f"in currency {currency or self.currency}"
        )
        return quote

    # Define position at date by summing all movements to date
    def position(self, date, investor, account_ids=None):
        query = self.transactions.filter(date__lte=date, investor=investor)
        if account_ids is not None:
            query = query.filter(account_id__in=account_ids)
        total_quantity = query.aggregate(total=models.Sum("quantity"))["total"]
        return round(Decimal(total_quantity), 6) if total_quantity else Decimal(0)

    # The very first investment date
    def investment_date(self, investor, account_ids=None):
        queryset = self.transactions.filter(investor=investor)
        if account_ids:
            queryset = queryset.filter(account_id__in=account_ids)
        query = queryset.order_by("date").values_list("date", flat=True).first()
        return query

    def entry_dates(self, date, investor, account_ids=None, start_date=None):
        """
        Returns a list of dates when the position changes from 0 to non-zero.
        """
        transactions = self.transactions.filter(
            date__lte=date, quantity__isnull=False, investor=investor
        )
        if account_ids is not None:
            transactions = transactions.filter(account_id__in=account_ids)

        transactions = transactions.order_by("date")

        entry_dates = []
        position = 0

        for transaction in transactions:
            new_position = position + transaction.quantity
            if position == 0 and new_position != 0:
                if start_date is not None and transaction.date < start_date:
                    position = new_position
                    continue
                entry_dates.append(transaction.date)

            position = new_position

        return entry_dates

    def exit_dates(self, end_date, investor, account_ids=None, start_date=None):
        """
        Returns a list of dates when the position changes from non-zero to 0.
        """
        transactions = self.transactions.filter(
            date__lte=end_date, quantity__isnull=False, investor=investor
        )
        if account_ids is not None:
            transactions = transactions.filter(account_id__in=account_ids)
        if start_date is not None:
            transactions = transactions.filter(date__gte=start_date)

        transactions = transactions.order_by("date")

        exit_dates = []
        if start_date is not None:
            position = self.position(start_date, investor, account_ids)
        else:
            position = 0

        for transaction in transactions:
            new_position = position + transaction.quantity
            if position != 0 and new_position == 0:
                exit_dates.append(transaction.date)
            position = new_position

        return exit_dates

    def calculate_buy_in_price(
        self, date, investor, currency=None, account_ids=None, start_date=None
    ):
        """
        Calculates the buy-in price for the given date, currency,
        broker account IDs, and start date.

        Args:
            date (datetime.date): The date for which to calculate the buy-in price.
            currency (str): The currency in which to calculate the buy-in price.
            account_ids (list): A list of broker account IDs to filter the transactions by.
            start_date (datetime.date): The start date for the calculation.

        Returns:
            float: The calculated buy-in price. Returns None if an error occurs.
        """
        logger.debug(f"Calculating buy-in price for {self.name} as of {date}")
        logger.debug(
            f"Parameters: currency={currency}, account_ids={account_ids}, start_date={start_date}"
        )

        is_long_position = None

        transactions = self.transactions.filter(
            quantity__isnull=False, investor=investor, date__lte=date
        ).order_by("date")

        if account_ids is not None:
            transactions = transactions.filter(account_id__in=account_ids)

        logger.debug(f"Number of transactions: {transactions.count()}")

        if not transactions:
            logger.debug("Buy-in price: No transactions found")
            return None

        # Get latest entry date
        entry_dates = self.entry_dates(date, investor, account_ids)
        if not entry_dates:
            logger.warning("No entry dates found")
            return None
        entry_date = entry_dates[-1]
        logger.debug(f"Latest entry date: {entry_date}")

        if start_date and start_date > entry_date:
            # Add artificial transaction at start_date
            logger.debug(f"Start date {start_date} is after latest entry date {entry_date}")
            position = self.position(start_date, investor, account_ids)
            logger.debug(f"Position at start date: {position}")
            if position != 0:
                price_at_start = self.price_at_date(start_date)
                if price_at_start:
                    logger.debug(f"Price at start date: {price_at_start.price}")
                    artificial_transaction = {
                        "date": start_date,
                        "quantity": position,
                        "price": price_at_start.price,
                        "currency": self.currency,
                    }
                    transactions = list(transactions.filter(date__gte=start_date))
                    transactions.insert(0, type("obj", (object,), artificial_transaction))
                    is_long_position = position > 0
                    logger.debug(f"Added artificial transaction: {artificial_transaction}")
            entry_date = start_date

        transactions = [t for t in transactions if t.date >= entry_date]
        logger.debug(f"Number of transactions after filtering: {len(transactions)}")

        if is_long_position is None and transactions:
            is_long_position = transactions[0].quantity > 0
        logger.debug(f"Is long position: {is_long_position}")

        # Calculate the buy-in price
        value_entry = Decimal(0)
        quantity_entry = Decimal(0)
        previous_entry_price = Decimal(0)

        for transaction in transactions:
            logger.debug(
                f"Processing transaction: Date={transaction.date}, "
                f"Quantity={transaction.quantity}, Price={transaction.price}"
            )

            if currency is not None:
                fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)["FX"]
            else:
                fx_rate = Decimal(1)
            logger.debug(f"FX rate: {fx_rate}")

            current_price = transaction.price * fx_rate
            weight_current = transaction.quantity

            # Calculate entry price
            previous_entry_price = (
                value_entry / quantity_entry if quantity_entry != 0 else Decimal(0)
            )
            weight_entry_previous = quantity_entry
            # If it's a long position and the quantity is positive,
            # or if it's a short position and the quantity is negative,
            # use the current price. Otherwise, use the previous buy-in price.
            entry_price = (
                current_price
                if (is_long_position and transaction.quantity > 0)
                or (not is_long_position and transaction.quantity < 0)
                else previous_entry_price
            )

            if (weight_entry_previous + weight_current) == 0:
                entry_price = previous_entry_price
            else:
                entry_price = (
                    previous_entry_price * weight_entry_previous + entry_price * weight_current
                ) / (weight_entry_previous + weight_current)

            quantity_entry += transaction.quantity
            value_entry = entry_price * quantity_entry

            logger.debug(
                f"After transaction: Entry price={entry_price}, "
                f"Quantity={quantity_entry}, Value={value_entry}"
            )

        final_price = (
            round(Decimal(value_entry / quantity_entry), 6)
            if quantity_entry
            else previous_entry_price
        )
        logger.debug(f"Final buy-in price: {final_price}")
        return final_price

    def realized_gain_loss(self, date, investor, currency=None, account_ids=None, start_date=None):
        def calculate_position_gain_loss(start, end, investor):
            result = {
                "price_appreciation": Decimal(0),
                "fx_effect": Decimal(0),
                "total": Decimal(0),
            }

            transactions = self.transactions.filter(
                date__gte=start, date__lte=end, quantity__isnull=False, investor=investor
            ).order_by("date")
            if account_ids is not None:
                transactions = transactions.filter(account_id__in=account_ids)

            position = self.position(start - timedelta(days=1), investor, account_ids)
            logger.debug(f"Starting position at {start}: {position}")

            for transaction in transactions:
                logger.debug(
                    f"Transaction: {transaction.date}, {transaction.type}, "
                    f"Quantity: {transaction.quantity}, Price: {transaction.price}"
                )

                if (
                    (position > 0 and transaction.type == TRANSACTION_TYPE_SELL)
                    or (position < 0 and transaction.type == TRANSACTION_TYPE_BUY)
                    or (position == 0)
                ):  # This handles same-day open and close
                    buy_in_price_target_currency = self.calculate_buy_in_price(
                        transaction.date, investor, currency, account_ids, start
                    )
                    buy_in_price_lcl_currency = self.calculate_buy_in_price(
                        transaction.date, investor, transaction.currency, account_ids, start
                    )

                    logger.info(
                        f"Buy-in price in target currency: {buy_in_price_target_currency}, "
                        f"in LCL currency: {buy_in_price_lcl_currency}"
                    )

                    if (
                        buy_in_price_target_currency is not None
                        and buy_in_price_lcl_currency is not None
                    ):
                        fx_rate_exit = (
                            FX.get_rate(transaction.currency, currency, transaction.date)["FX"]
                            if currency
                            else 1
                        )

                        price_appreciation = (
                            -(transaction.price - buy_in_price_lcl_currency)
                            * transaction.quantity
                            * fx_rate_exit
                        )
                        gl_target_currency = (
                            -(transaction.price * fx_rate_exit - buy_in_price_target_currency)
                            * transaction.quantity
                        )
                        fx_effect = gl_target_currency - price_appreciation

                        result["total"] += Decimal(gl_target_currency)
                        result["price_appreciation"] += Decimal(price_appreciation)
                        result["fx_effect"] += Decimal(fx_effect)

                        logger.debug(f"Realized G/L for this transaction: {gl_target_currency}")

                position += transaction.quantity
                logger.debug(f"Position after transaction: {position}")

            logger.debug(f"Final position at {end}: {position}")
            return result

        result = {
            "current_position": {
                "price_appreciation": Decimal(0),
                "fx_effect": Decimal(0),
                "total": Decimal(0),
            },
            "all_time": {
                "price_appreciation": Decimal(0),
                "fx_effect": Decimal(0),
                "total": Decimal(0),
            },
        }

        # Calculate all-time realized gain/loss
        exit_dates = self.exit_dates(date, investor, account_ids, start_date)
        entry_dates = self.entry_dates(date, investor, account_ids, start_date)

        if start_date is not None and len(entry_dates) == 0:
            entry_dates = [start_date]

        logger.debug(f"Exit dates: {exit_dates}")
        logger.debug(f"Entry dates: {entry_dates}")

        # Pair entry and exit dates
        date_pairs = []
        for entry_date in entry_dates:
            exit_date = next((d for d in exit_dates if d >= entry_date), date)
            date_pairs.append((entry_date, exit_date))

        # Adjust date pairs based on start_date and end_date
        adjusted_pairs = []
        for entry_date, exit_date in date_pairs:
            logger.debug(f"Unadjusted pair: {entry_date} to {exit_date}")
            if start_date and start_date > entry_date and start_date <= exit_date:
                entry_date = start_date
            if exit_date > date and date >= start_date:
                exit_date = date
            adjusted_pairs.append((entry_date, exit_date))

        logger.debug(f"Adjusted date pairs: {adjusted_pairs}")

        # Calculate gain/loss for each position
        for position_start, position_end in adjusted_pairs:
            logger.debug(f"Calculating for position: {position_start} to {position_end}")
            position_result = calculate_position_gain_loss(position_start, position_end, investor)
            logger.debug(f"Position result: {position_result}")

            for key in result["all_time"]:
                result["all_time"][key] += position_result[key]

            # If this is the current position, update the current_position result as well
            if position_end == date and position_end not in exit_dates:
                result["current_position"] = position_result.copy()

            logger.debug(f"Current position result: {result['current_position']}")

        # Round all results to 2 decimal places
        for period in result:
            for component in result[period]:
                result[period][component] = round(result[period][component], 2)

        return result

    def unrealized_gain_loss(
        self, date, investor, currency=None, account_ids=None, start_date=None
    ):
        """
        Calculates the unrealized gain/loss for an asset and breaks it down into components:
        price appreciation, and FX effect.

        Parameters:
            asset (Asset): The asset object for which unrealized gain/loss is calculated.
            date (datetime.date): The date as of which the calculation is performed.
            currency (str): The reporting currency.
            account_ids (list): List of broker account IDs to filter transactions.
            start_date (datetime.date): The start date for calculating buy-in price.

        Returns:
            dict: A dictionary containing the breakdown of unrealized gain/loss:
                - 'price_appreciation': The price appreciation component in reporting currency.
                - 'fx_effect': The FX effect component in reporting currency.
                - 'total': The total unrealized gain/loss in reporting currency.
        """
        unrealized_gain_loss = 0
        price_appreciation = 0
        fx_effect = 0

        current_position = self.position(date, investor, account_ids)

        current_price_in_lcl_cur = (
            self.price_at_date(date, currency=None).price if self.price_at_date(date) else 0
        )
        current_price_in_target_cur = (
            self.price_at_date(date, currency).price if self.price_at_date(date) else 0
        )
        buy_in_price_in_lcl_cur = self.calculate_buy_in_price(
            date, investor, currency=None, account_ids=account_ids, start_date=start_date
        )
        buy_in_price_in_target_cur = self.calculate_buy_in_price(
            date, investor, currency, account_ids, start_date
        )

        fx_rate_eop = FX.get_rate(self.currency, currency, date)["FX"] if currency else 1

        if buy_in_price_in_lcl_cur is not None and buy_in_price_in_target_cur is not None:
            price_appreciation = (
                (current_price_in_lcl_cur - buy_in_price_in_lcl_cur)
                * current_position
                * fx_rate_eop
            )
            unrealized_gain_loss = (
                current_price_in_target_cur - buy_in_price_in_target_cur
            ) * current_position
            fx_effect = unrealized_gain_loss - price_appreciation

        return {
            "price_appreciation": round(Decimal(price_appreciation), 2),
            "fx_effect": round(Decimal(fx_effect), 2),
            "total": round(Decimal(unrealized_gain_loss), 2),
        }

    def get_capital_distribution(
        self, date, investor, currency=None, account_ids=None, start_date=None
    ):
        """
        Calculate the capital distribution (dividends) for this asset.
        Capital distribution is the total cash flow from 'dividend' type transactions.
        """
        total_dividends = 0
        dividend_transactions = self.transactions.filter(
            type="Dividend", date__lte=date, investor=investor
        )

        if account_ids is not None:
            dividend_transactions = dividend_transactions.filter(account_id__in=account_ids)

        if start_date is not None:
            dividend_transactions = dividend_transactions.filter(date__gte=start_date)

        if dividend_transactions:
            if currency is None:
                total_dividends += dividend_transactions.aggregate(total=Sum("cash_flow"))["total"]
            else:
                for dividend in dividend_transactions:
                    fx_rate = FX.get_rate(dividend.currency, currency, dividend.date)["FX"]
                    if fx_rate:
                        total_dividends += dividend.cash_flow * fx_rate
            return round(Decimal(total_dividends), 2)
        else:
            return Decimal(0)

    def get_commission(self, date, investor, currency=None, account_ids=None, start_date=None):
        """
        Calculate the comission for this asset.
        """
        total_commission = 0
        commission_transactions = self.transactions.filter(
            commission__isnull=False, date__lte=date, investor=investor
        )

        if account_ids is not None:
            commission_transactions = commission_transactions.filter(account_id__in=account_ids)

        if start_date is not None:
            commission_transactions = commission_transactions.filter(date__gte=start_date)

        if commission_transactions:
            if currency is None:
                total_commission += commission_transactions.aggregate(total=Sum("commission"))[
                    "total"
                ]
            else:
                for commission in commission_transactions:
                    fx_rate = FX.get_rate(commission.currency, currency, commission.date)["FX"]
                    if fx_rate:
                        total_commission += commission.commission * fx_rate
            return round(Decimal(total_commission), 2)
        else:
            return Decimal(0)

    def __str__(self):
        return self.name  # Define how the broker is represented as a string


# Table with public asset transactions
class Transactions(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="transactions")
    account = models.ForeignKey(Accounts, on_delete=models.CASCADE, related_name="transactions")
    security = models.ForeignKey(
        Assets, on_delete=models.CASCADE, related_name="transactions", null=True, blank=True
    )
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="USD", null=False, blank=False
    )
    type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES, null=False)
    date = models.DateField(db_index=True, null=False)
    quantity = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    cash_flow = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    commission = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.type} || {self.date}"


# Table with non-public asset prices
class Prices(models.Model):
    date = models.DateField(null=False)
    security = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name="prices")
    price = models.DecimalField(max_digits=15, decimal_places=6, null=False)

    def __str__(self):
        return f"{self.security.name} is at {self.price} on {self.date}"

    class Meta:
        # Add constraints
        constraints = [
            models.UniqueConstraint(
                fields=["date", "security"], name="unique_security_price_entry"
            ),
        ]


def is_yahoo_finance_available():
    url = "https://finance.yahoo.com"  # Replace with the Yahoo Finance API endpoint if needed
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return True
    except requests.ConnectionError:
        pass
    return False


def update_FX_from_Yahoo(base_currency, target_currency, date, max_attempts=5):
    if not is_yahoo_finance_available():
        raise ConnectionError("Yahoo Finance is not available")

    # Define the currency pair
    currency_pair = f"{target_currency}{base_currency}=X"

    # Initialize a counter for the number of attempts
    attempt = 0

    while attempt < max_attempts:
        # Define the date for which you want the exchange rate
        end_date = date - timedelta(
            days=attempt - 1
        )  # Go back in time for each attempt. Need to deduct 1 to get rate for exactly the date
        start_date = end_date - timedelta(days=1)  # Go back one day to ensure the date is covered

        # Fetch historical data for the currency pair within the date range
        data = yf.Ticker(currency_pair)
        # exchange_rate_data = data.history(period="1d", start=start_date, end=end_date)
        try:
            exchange_rate_data = data.history(period="1d", start=start_date, end=end_date)
        except Exception as e:
            logger.error(f"Error fetching exchange rate data: {e}")
            attempt += 1
            continue

        if not exchange_rate_data.empty and not exchange_rate_data["Close"].isnull().all():
            # Get the exchange rate for the specified date
            exchange_rate = round(exchange_rate_data["Close"].iloc[0], 6)
            actual_date = exchange_rate_data.index[0].date()  # Extract the actual date

            return {
                "exchange_rate": exchange_rate,
                "actual_date": actual_date,
                "requested_date": date,
            }

        # Increment the attempt counter
        attempt += 1

    # If no data is found after max_attempts, return None or an appropriate error message
    return None


# Model to store the annual performance data
class AnnualPerformance(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    account_type = models.CharField(
        max_length=50, choices=ACCOUNT_TYPE_CHOICES, default=ACCOUNT_TYPE_ALL  # From constants.py
    )
    account_id = models.IntegerField(null=True, blank=True)
    year = models.IntegerField()
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    bop_nav = models.DecimalField(max_digits=20, decimal_places=2)
    invested = models.DecimalField(max_digits=20, decimal_places=2)
    cash_out = models.DecimalField(max_digits=20, decimal_places=2)
    price_change = models.DecimalField(max_digits=20, decimal_places=2)
    capital_distribution = models.DecimalField(max_digits=20, decimal_places=2)
    commission = models.DecimalField(max_digits=20, decimal_places=2)
    tax = models.DecimalField(max_digits=20, decimal_places=2)
    fx = models.DecimalField(max_digits=20, decimal_places=2)
    eop_nav = models.DecimalField(max_digits=20, decimal_places=2)
    tsr = models.CharField(max_length=10)  # Can be non numeric
    restricted = models.BooleanField(default=False, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["investor", "year", "currency", "restricted", "account_type", "account_id"],
                name="unique_annual_performance",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(account_type=ACCOUNT_TYPE_ALL, account_id__isnull=True)
                    | ~models.Q(account_type=ACCOUNT_TYPE_ALL) & models.Q(account_id__isnull=False)
                ),
                name="valid_annual_performance_selection",
            ),
        ]


class FXTransaction(models.Model):
    investor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="fx_transactions"
    )
    account = models.ForeignKey(Accounts, on_delete=models.CASCADE, related_name="fx_transactions")
    date = models.DateField(null=False)
    from_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    to_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    from_amount = models.DecimalField(max_digits=15, decimal_places=6, null=False)
    to_amount = models.DecimalField(max_digits=15, decimal_places=6, null=False)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, null=False, blank=True)
    commission = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    commission_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, null=True, blank=True
    )
    comment = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.exchange_rate:
            self.exchange_rate = self.from_amount / self.to_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"FX: {self.from_currency} to {self.to_currency} on {self.date}"
