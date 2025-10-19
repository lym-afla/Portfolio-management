"""Common models."""

import logging
from datetime import datetime, timedelta
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
    DATA_SOURCE_CHOICES,
    EXPOSURE_CHOICES,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_CHOICES,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)
# from .utils import update_FX_database
from users.models import CustomUser

from .fields import TimezoneAwareDateField, TimezoneAwareDateTimeField

logger = logging.getLogger(__name__)


# Table with FX data
class FX(models.Model):
    """FX model."""

    id = models.AutoField(primary_key=True)
    date = TimezoneAwareDateField(unique=True)
    investors = models.ManyToManyField(CustomUser, related_name="fx_rates")
    USDEUR = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    USDGBP = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    CHFGBP = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    RUBUSD = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    PLNUSD = models.DecimalField(max_digits=9, decimal_places=5, null=True, blank=True)
    CNYUSD = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    class Meta:
        """Meta class for the FX model."""

        ordering = ["-date"]

    # Get FX quote for date
    @classmethod
    def get_rate(cls, source, target, date, investor=None):
        """Get FX rate for a given currency and target currency at a given date."""
        fx_rate = 1
        dates_async = False
        dates_list = []

        # Convert to uppercase
        source = source.upper()
        target = target.upper()

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

        # Create undirected graph with currencies, import networkx library
        # working with graphs
        G = nx.Graph()
        for entry in pairs_list:
            G.add_nodes_from([entry[:3], entry[3:]])
            G.add_edge(entry[:3], entry[3:])

        # Finding shortest path for cross-currency conversion using
        # "Bellman-Ford" algorithm
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
                            raise ValueError(
                                f"No FX rate found for {field_name} before {date}"
                            )

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
        """Update FX rate for a given date and investor."""
        # Get FX model variables, except 'date', 'id' and 'investors'
        fx_variables = [
            field
            for field in cls._meta.get_fields()
            if field.name not in ["date", "id", "investors"]
        ]

        # Extract source and target currencies
        currency_pairs = [(field.name[:3], field.name[3:]) for field in fx_variables]

        # Create or get the fx_instance once before the loop
        fx_instance, _ = cls.objects.get_or_create(date=date)
        fx_instance.investors.add(investor)

        for source, target in currency_pairs:
            # Check if an FX rate exists for the date and currency pair
            existing_rate = getattr(fx_instance, f"{source}{target}", None)

            if existing_rate is None:
                # Get the FX rate for the yahoo finance
                try:
                    rate_data = update_FX_from_Yahoo(source, target, date)

                    if rate_data is not None:
                        # Update the fx_instance with the new rate from yahoo finance
                        setattr(
                            fx_instance, f"{source}{target}", rate_data["exchange_rate"]
                        )
                except Exception:
                    print(
                        f"{source}{target} for {date} is NOT updated. "
                        "Yahoo Finance is not responding correctly"
                    )
                    continue

        # Save the fx_instance once after updating all currency pairs from yahoo finance
        fx_instance.save()

    @classmethod
    def get_investor_fx_entries(cls, investor):
        """Get FX entries for a given investor."""
        return cls.objects.filter(investors=investor)


# Brokers
class Brokers(models.Model):
    """Represents a broker entity (e.g., Tinkoff, Interactive Brokers)."""

    investor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="brokers"
    )
    name = models.CharField(max_length=30, null=False)
    country = models.CharField(max_length=20)
    comment = models.TextField(null=True, blank=True)
    created_at = TimezoneAwareDateTimeField(auto_now_add=True)
    updated_at = TimezoneAwareDateTimeField(auto_now=True)

    class Meta:
        """Meta class for the Brokers model."""

        unique_together = ["investor", "name"]
        ordering = ["name"]

    def __str__(self):
        """Return the string representation of the Brokers model."""
        return self.name


class Accounts(models.Model):
    """Represents a specific account at a broker."""

    broker = models.ForeignKey(
        Brokers, on_delete=models.CASCADE, related_name="accounts"
    )
    native_id = models.CharField(
        max_length=100,
        help_text="Native account ID from broker's system",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100, help_text="Account name or description")
    restricted = models.BooleanField(default=False, null=False, blank=False)
    comment = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = TimezoneAwareDateTimeField(auto_now_add=True)
    updated_at = TimezoneAwareDateTimeField(auto_now=True)

    class Meta:
        """Meta class for the Accounts model."""

        unique_together = ["broker", "native_id"]
        ordering = ["broker", "name"]

    def __str__(self):
        """Return the string representation of the Accounts model."""
        return f"Account: {self.name}"

    @property
    def full_name(self):
        """Get the full name of this account."""
        return f"{self.broker.name} - {self.name}"

    # List of currencies used
    def get_currencies(self):
        """Get currencies for this account."""
        currencies = set()
        for transaction in self.transactions.all():
            currencies.add(transaction.currency)
        return currencies

    # Cash balance at date
    def balance(self, date):
        """
        Calculate account cash balance as of a given date.

        Uses the centralized get_calculated_cash_flow() method for consistency.
        """
        balance = {}

        # Convert date to timezone-aware datetime for query
        query_date = date

        # Process regular transactions using centralized cash flow calculation
        transactions = self.transactions.filter(date__lte=query_date)
        for transaction in transactions:
            cash_flow = transaction.get_calculated_cash_flow()
            balance[transaction.currency] = (
                balance.get(transaction.currency, Decimal(0)) + cash_flow
            )

        # Calculate balance from FX transactions using centralized method
        fx_transactions = self.fx_transactions.filter(date__lte=query_date)
        for fx_transaction in fx_transactions:
            # Get all currencies involved in this FX transaction
            involved_currencies = {
                fx_transaction.from_currency,
                fx_transaction.to_currency,
            }
            if fx_transaction.commission_currency:
                involved_currencies.add(fx_transaction.commission_currency)

            # Update balance for each currency using centralized method
            for currency in involved_currencies:
                cash_flow = fx_transaction.get_cash_flow_by_currency(currency)
                balance[currency] = balance.get(currency, Decimal(0)) + cash_flow

        for key, value in balance.items():
            balance[key] = round(Decimal(value), 2)

        return balance


# Public assets
class Assets(models.Model):
    """Assets model."""

    investors = models.ManyToManyField(CustomUser, related_name="assets", blank=True)
    type = models.CharField(max_length=15, choices=ASSET_TYPE_CHOICES, null=False)
    ISIN = models.CharField(max_length=12)
    name = models.CharField(max_length=70, null=False)
    ticker = models.CharField(max_length=10, null=True, blank=True)
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="USD", null=False
    )
    exposure = models.TextField(null=False, choices=EXPOSURE_CHOICES, default="Equity")
    restricted = models.BooleanField(default=False, null=False)
    comment = models.TextField(null=True, blank=True)
    data_source = models.CharField(
        max_length=10,
        choices=[("", "None")] + DATA_SOURCE_CHOICES,
        blank=True,
        null=True,
    )
    update_link = models.URLField(null=True, blank=True)  # For FT
    yahoo_symbol = models.CharField(
        max_length=50, blank=True, null=True
    )  # For Yahoo Finance symbol
    fund_fee = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True
    )
    secid = models.CharField(max_length=10, null=True, blank=True)  # For MICEX
    tbank_instrument_uid = models.CharField(
        max_length=50, blank=True, null=True
    )  # For T-Bank

    # Helper properties for bond handling
    @property
    def is_bond(self):
        """Check if this asset is a bond."""
        return self.type == "Bond"

    @property
    def bond_metadata(self):
        """Get bond metadata if this is a bond, otherwise None."""
        if not self.is_bond:
            return None
        try:
            return self.bondmetadata_metadata
        except Exception:
            return None

    def get_effective_notional(self, date, investor, account_ids=None, currency=None):
        """
        Get the effective notional value per bond at a given date.

        For amortizing bonds, this accounts for partial redemptions.
        For other assets, returns 1.0 (representing standard quantity).
        """
        bond_meta = self.bond_metadata
        if not bond_meta:
            return None

        return bond_meta.get_current_notional(date, investor, account_ids, currency)

    # Returns price at the date or latest available before the date
    def price_at_date(self, price_date, currency=None):
        """Get the price of an asset at a given date."""
        logger.debug(
            f"Fetching price for {self.name} as of {price_date} in currency {currency}"
        )
        # Convert date to timezone-aware datetime for query
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
                    f"Using last transaction price for {self.name} "
                    f"as of {last_transaction.date}"
                )
                quote = type(
                    "obj",
                    (object,),
                    {"price": last_transaction.price, "date": last_transaction.date},
                )
            else:
                logger.warning(
                    f"No transaction found for {self.name} as of {price_date}"
                )
                return None

        if currency is not None:
            if self.is_bond:
                fx_rate = Decimal(1)
            else:
                fx_rate = FX.get_rate(self.currency, currency, price_date)["FX"]

            logger.debug(
                f"Converting price from {self.currency} to {currency} "
                f"using FX rate {fx_rate}"
            )
            quote.price = quote.price * fx_rate
        logger.debug(
            f"Price for {self.name} as of {quote.date} is {quote.price} "
            f"in currency {currency or self.currency}"
        )
        return quote

    def calculate_value_at_date(self, date, investor, currency=None, account_ids=None):
        """
        Calculate the market value of this asset at a given date.

        For bonds, this accounts for the effective notional value.
        For other assets, this is simply position * price.

        Args:
            date: The date for which to calculate value
            investor: The investor who owns the asset
            currency: Optional currency for conversion
            account_ids: Optional list of account IDs to filter by

        Returns:
            Decimal: The calculated market value
        """
        position = self.position(date, investor, account_ids)
        if position == 0:
            return Decimal(0)

        price_quote = self.price_at_date(date, currency)
        if price_quote is None:
            logger.warning(f"No price found for {self.name} at {date}")
            return Decimal(0)

        price = price_quote.price  # For bonds: percentage of par

        # For bonds: value = position * (price% / 100) * notional
        # For others: value = position * price
        if self.is_bond:
            effective_notional = self.get_effective_notional(
                date, investor, account_ids, currency
            )
            value = position * price * effective_notional / Decimal(100)
            logger.debug(
                f"Bond value calculation for {self.name}: "
                f"position={position}, price%={price}, notional={effective_notional}, "
                f"value={value}"
            )
        else:
            value = position * price
            logger.debug(
                f"Standard value calculation for {self.name}: "
                f"position={position}, price={price}, value={value}"
            )

        return value

    # Define position at date by summing all movements to date
    def position(self, date, investor, account_ids=None):
        """Get the position of an asset at a given date."""
        query = self.transactions.filter(date__lte=date, investor=investor)
        if account_ids is not None:
            query = query.filter(account_id__in=account_ids)
        total_quantity = query.aggregate(total=models.Sum("quantity"))["total"]
        return round(Decimal(total_quantity), 6) if total_quantity else Decimal(0)

    def get_accounts_with_positions(self, date, investor):
        """
        Get list of accounts with non-zero positions at a given date.

        Args:
            date: Date to check positions at
            investor: Investor to check for

        Returns:
            list: List of account IDs with non-zero positions
        """
        # Get all accounts that have transactions for this security
        account_ids = (
            self.transactions.filter(investor=investor, quantity__isnull=False)
            .values_list("account_id", flat=True)
            .distinct()
        )

        # Check position for each account and keep only non-zero ones
        accounts_with_positions = []
        for account_id in account_ids:
            position = self.position(
                date=date, investor=investor, account_ids=[account_id]
            )
            if position and position != 0:
                accounts_with_positions.append(account_id)

        return accounts_with_positions

    # The very first investment date
    def investment_date(self, investor, account_ids=None):
        """Get the investment date for this security."""
        queryset = self.transactions.filter(investor=investor)
        if account_ids:
            queryset = queryset.filter(account_id__in=account_ids)
        query = queryset.order_by("date").values_list("date", flat=True).first()
        return query

    def entry_dates(self, date, investor, account_ids=None, start_date=None):
        """Get a list of dates when the position changes from 0 to non-zero."""
        query_date = date
        transactions = self.transactions.filter(
            date__lte=query_date, quantity__isnull=False, investor=investor
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
        """Get a list of dates when the position changes from non-zero to 0."""
        query_end_date = end_date
        transactions = self.transactions.filter(
            date__lte=query_end_date, quantity__isnull=False, investor=investor
        )
        if account_ids is not None:
            transactions = transactions.filter(account_id__in=account_ids)
        if start_date is not None:
            query_start_date = start_date
            transactions = transactions.filter(date__gte=query_start_date)

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
        Calculate average buy-in price for an asset.

        Calculates the average buy-in price for the given date, currency,
        broker account IDs, and start date.

        Args:
            date (datetime.date): Date for which to calculate the buy-in price.
            currency (str): Currency in which to calculate the buy-in price.
            account_ids (list): List of broker account IDs to filter transactions by.
            start_date (datetime.date): Start date for the calculation.

        Returns:
            float: Calculated buy-in price. Returns None if an error occurs.
        """
        logger.debug(f"Calculating buy-in price for {self.name} as of {date}")
        logger.debug(
            f"Parameters: currency={currency}, account_ids={account_ids}, "
            f"start_date={start_date}"
        )

        is_long_position = None

        query_date = date
        transactions = self.transactions.filter(
            quantity__isnull=False, investor=investor, date__lte=query_date
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
            logger.debug(
                f"Start date {start_date} is after latest entry date {entry_date}"
            )
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
                    transactions.insert(
                        0, type("obj", (object,), artificial_transaction)
                    )
                    is_long_position = position > 0
                    logger.debug(
                        f"Added artificial transaction: {artificial_transaction}"
                    )
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
                fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)[
                    "FX"
                ]
            else:
                fx_rate = Decimal(1)
            logger.debug(f"FX rate: {fx_rate}")

            # Use price as-is (percentage for bonds, actual for others)
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
                    previous_entry_price * weight_entry_previous
                    + entry_price * weight_current
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

    def realized_gain_loss(
        self, date, investor, currency=None, account_ids=None, start_date=None
    ):
        """
        Calculate the realized gain/loss for an asset.

        Calculates the realized gain/loss for an asset
        and breaks it down into components price appreciation, and FX effect.

        Parameters:
            self (Asset): The asset object for which realized gain/loss is calculated.
            date (datetime.date): The date as of which the calculation is performed.
            currency (str): The reporting currency.
            account_ids (list): The list of account IDs.
            start_date (datetime.date): The start date for the calculation.
        """

        def calculate_position_gain_loss(start, end, investor):
            """Calculate the position gain/loss helper function."""
            result = {
                "price_appreciation": Decimal(0),
                "fx_effect": Decimal(0),
                "total": Decimal(0),
            }

            query_start = start
            query_end = end
            transactions = self.transactions.filter(
                date__gte=query_start,
                date__lte=query_end,
                quantity__isnull=False,
                investor=investor,
            ).order_by("date")
            if account_ids is not None:
                transactions = transactions.filter(account_id__in=account_ids)

            position = self.position(start - timedelta(days=1), investor, account_ids)
            logger.debug(f"Starting position at {start}: {position}")

            for transaction in transactions:
                logger.debug(
                    f"Transaction: {transaction.date}, {transaction.type}, "
                    f"Quantity: {transaction.quantity}, "
                    f"Price: {transaction.get_price()}"
                )

                # Check if this is a bond redemption transaction
                is_bond_redemption = transaction.type in [
                    TRANSACTION_TYPE_BOND_REDEMPTION,
                    TRANSACTION_TYPE_BOND_MATURITY,
                ]

                # Handle bond redemptions separately
                if is_bond_redemption:
                    # For bond redemption:
                    # gain = cash_received - (notional_redeemed * buy_in_price)
                    # Gain is zero only if bought at par and redeemed at par
                    cash_received = transaction.cash_flow or Decimal(0)
                    notional_redeemed_per_bond = getattr(
                        transaction, "notional_change", None
                    )
                    notional_redeemed = (
                        notional_redeemed_per_bond
                        * transaction.security.position(
                            transaction.date, investor, account_ids
                        )
                    )

                    logger.debug(
                        f"Bond redemption: cash_flow={cash_received}, "
                        f"Total notional redeemed={notional_redeemed}, "
                        f"Per-bond notional redeemed={notional_redeemed_per_bond}"
                    )

                    if notional_redeemed and notional_redeemed != 0:
                        buy_in_price_target_currency = self.calculate_buy_in_price(
                            transaction.date, investor, currency, account_ids, start
                        )
                        buy_in_price_lcl_currency = self.calculate_buy_in_price(
                            transaction.date,
                            investor,
                            transaction.currency,
                            account_ids,
                            start,
                        )

                        if (
                            buy_in_price_target_currency is not None
                            and buy_in_price_lcl_currency is not None
                        ):
                            fx_rate_exit = (
                                FX.get_rate(
                                    transaction.currency, currency, transaction.date
                                )["FX"]
                                if currency
                                else 1
                            )

                            # Redemption G/L = notional_redeemed_per_bond * quantity * (100 - buy_in_price%) # noqa: E501
                            # For bonds, buy_in_price is in percentage terms

                            # Price appreciation in local currency (100 = 100% of par = redemption at par) # noqa: E501
                            price_appreciation_lcl = (
                                cash_received
                                - notional_redeemed
                                * buy_in_price_lcl_currency
                                / Decimal(100)
                            )
                            price_appreciation = price_appreciation_lcl * fx_rate_exit

                            # Total G/L in target currency
                            gl_target_currency = (
                                cash_received * fx_rate_exit
                                - notional_redeemed
                                * buy_in_price_target_currency
                                / Decimal(100)
                            )

                            # FX effect
                            fx_effect = gl_target_currency - price_appreciation

                            result["total"] += Decimal(gl_target_currency)
                            result["price_appreciation"] += Decimal(price_appreciation)
                            result["fx_effect"] += Decimal(fx_effect)

                            logger.debug(
                                "Redemption G/L: notional_redeemed="
                                f"{notional_redeemed}, "
                                f"buy_in_price%={buy_in_price_lcl_currency}, "
                                f"gain={gl_target_currency}"
                            )

                    # Position doesn't change for partial redemptions
                    # (quantity is None/0)
                    # For final redemption with negative quantity, update position
                    if transaction.quantity:
                        position += transaction.quantity

                    logger.debug(f"Position after redemption: {position}")
                    continue

                is_position_reducing = (
                    (position > 0 and transaction.type == TRANSACTION_TYPE_SELL)
                    or (position < 0 and transaction.type == TRANSACTION_TYPE_BUY)
                    or (position == 0)  # This handles same-day open and close
                )

                if is_position_reducing:
                    buy_in_price_target_currency = self.calculate_buy_in_price(
                        transaction.date, investor, currency, account_ids, start
                    )
                    buy_in_price_lcl_currency = self.calculate_buy_in_price(
                        transaction.date,
                        investor,
                        transaction.currency,
                        account_ids,
                        start,
                    )

                    logger.debug(
                        "Buy-in price in target currency: "
                        f"{buy_in_price_target_currency}, in LCL currency: "
                        f"{buy_in_price_lcl_currency}"
                    )

                    if (
                        buy_in_price_target_currency is not None
                        and buy_in_price_lcl_currency is not None
                    ):
                        fx_rate_exit = (
                            FX.get_rate(
                                transaction.currency, currency, transaction.date
                            )["FX"]
                            if currency
                            else 1
                        )

                        # For bonds: G/L = notional_at_sell * (sale_price% - buy_in_price%) * quantity_sold # noqa: E501
                        # For others: G/L = (sale_price - buy_in_price) * quantity_sold
                        if self.is_bond:
                            notional_at_sell = self.get_effective_notional(
                                transaction.date,
                                investor,
                                account_ids,
                                transaction.currency,
                            )

                            # Prices are in percentage terms
                            price_appreciation_lcl = (
                                notional_at_sell
                                * (transaction.price - buy_in_price_lcl_currency)
                                * (-transaction.quantity)
                                / Decimal(100)
                            )
                            price_appreciation = price_appreciation_lcl * fx_rate_exit

                            gl_target_currency = (
                                notional_at_sell
                                * (
                                    transaction.price * fx_rate_exit
                                    - buy_in_price_target_currency
                                )
                                * (-transaction.quantity)
                                / Decimal(100)
                            )
                        else:
                            # Standard calculation for non-bonds
                            price_appreciation = (
                                -(transaction.price - buy_in_price_lcl_currency)
                                * transaction.quantity
                                * fx_rate_exit
                            )
                            gl_target_currency = (
                                -(
                                    transaction.price * fx_rate_exit
                                    - buy_in_price_target_currency
                                )
                                * transaction.quantity
                            )

                        fx_effect = gl_target_currency - price_appreciation

                        result["total"] += Decimal(gl_target_currency)
                        result["price_appreciation"] += Decimal(price_appreciation)
                        result["fx_effect"] += Decimal(fx_effect)

                        logger.debug(
                            f"Realized G/L for this transaction: {gl_target_currency}"
                        )

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
            logger.debug(
                f"Calculating for position: {position_start} to {position_end}"
            )
            position_result = calculate_position_gain_loss(
                position_start, position_end, investor
            )
            logger.debug(f"Position result: {position_result}")

            for key in result["all_time"]:
                result["all_time"][key] += position_result[key]

            # If this is the current position,
            # update the current_position result as well
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
        Calculate the unrealized gain/loss for an asset.

        Calculates the unrealized gain/loss for an asset
        and breaks it down into components price appreciation, and FX effect.

        Parameters:
            self (Asset): The asset object for which unrealized gain/loss is calculated.
            date (datetime.date): The date as of which the calculation is performed.
            currency (str): The reporting currency.
            account_ids (list): List of broker account IDs to filter transactions.
            start_date (datetime.date): The start date for calculating buy-in price.

        Returns:
            dict: A dictionary containing the breakdown of unrealized gain/loss:
                - 'price_appreciation': Price appreciation in reporting currency.
                - 'fx_effect': FX effect in reporting currency.
                - 'total': Total unrealized gain/loss in reporting currency.
        """
        unrealized_gain_loss = 0
        price_appreciation = 0
        fx_effect = 0

        current_position = self.position(date, investor, account_ids)

        current_price_in_lcl_cur = (
            self.price_at_date(date, currency=None).price
            if self.price_at_date(date)
            else 0
        )
        current_price_in_target_cur = (
            self.price_at_date(date, currency).price if self.price_at_date(date) else 0
        )
        buy_in_price_in_lcl_cur = self.calculate_buy_in_price(
            date,
            investor,
            currency=None,
            account_ids=account_ids,
            start_date=start_date,
        )
        buy_in_price_in_target_cur = self.calculate_buy_in_price(
            date, investor, currency, account_ids, start_date
        )

        fx_rate_eop = (
            FX.get_rate(self.currency, currency, date)["FX"] if currency else 1
        )

        if (
            buy_in_price_in_lcl_cur is not None
            and buy_in_price_in_target_cur is not None
        ):
            # For bonds: unrealized G/L = notional_at_date * (price_at_date% - buy_in_price%) * position / 100 # noqa: E501
            # For others: unrealized G/L = (current_price - buy_in_price) * position
            if self.is_bond:
                notional_lcl = self.get_effective_notional(date, investor, account_ids)

                price_appreciation = (
                    notional_lcl
                    * (current_price_in_lcl_cur - buy_in_price_in_lcl_cur)
                    * current_position
                    * fx_rate_eop
                    / Decimal(100)
                )
                unrealized_gain_loss = (
                    notional_lcl
                    * (current_price_in_target_cur - buy_in_price_in_target_cur)
                    * current_position
                    / Decimal(100)
                )
            else:
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
        distribution_transactions = self.transactions.filter(
            type__in=["Dividend", "Coupon"], date__lte=query_date, investor=investor
        )

        if account_ids is not None:
            distribution_transactions = distribution_transactions.filter(
                account_id__in=account_ids
            )

        if start_date is not None:
            query_start_date = start_date
            distribution_transactions = distribution_transactions.filter(
                date__gte=query_start_date
            )

        # Calculate dividends and coupons
        if distribution_transactions:
            if currency is None:
                total_distributions += (
                    distribution_transactions.aggregate(total=Sum("cash_flow"))["total"]
                    or 0
                )
            else:
                for transaction in distribution_transactions:
                    fx_rate = FX.get_rate(
                        transaction.currency, currency, transaction.date
                    )["FX"]
                    if fx_rate:
                        total_distributions += transaction.cash_flow * fx_rate

        # For bonds: subtract ACI paid at acquisition
        # (negative ACI from Buy transactions)
        # This nets the ACI paid when buying against the coupons received
        if self.is_bond:
            aci_paid_transactions = self.transactions.filter(
                type="Buy", aci__lt=0, date__lte=query_date, investor=investor
            )

            if account_ids is not None:
                aci_paid_transactions = aci_paid_transactions.filter(
                    account_id__in=account_ids
                )

            if start_date is not None:
                aci_paid_transactions = aci_paid_transactions.filter(
                    date__gte=query_start_date
                )

            # Subtract ACI paid (it's negative, so this reduces distributions)
            if aci_paid_transactions:
                if currency is None:
                    total_distributions += (
                        aci_paid_transactions.aggregate(total=Sum("aci"))["total"] or 0
                    )
                else:
                    for transaction in aci_paid_transactions:
                        fx_rate = FX.get_rate(
                            transaction.currency, currency, transaction.date
                        )["FX"]
                        if fx_rate:
                            total_distributions += transaction.aci * fx_rate

        # Get tax transactions (typically negative, reducing net distributions)
        tax_transactions = self.transactions.filter(
            type="Tax", date__lte=date, investor=investor
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
                    fx_rate = FX.get_rate(
                        transaction.currency, currency, transaction.date
                    )["FX"]
                    if fx_rate:
                        total_distributions += transaction.cash_flow * fx_rate

        return round(Decimal(total_distributions), 2)

    def get_commission(
        self, date, investor, currency=None, account_ids=None, start_date=None
    ):
        """Calculate the comission for this asset."""
        total_commission = 0
        query_date = date
        commission_transactions = self.transactions.filter(
            commission__isnull=False, date__lte=query_date, investor=investor
        )

        if account_ids is not None:
            commission_transactions = commission_transactions.filter(
                account_id__in=account_ids
            )

        if start_date is not None:
            query_start_date = start_date
            commission_transactions = commission_transactions.filter(
                date__gte=query_start_date
            )

        if commission_transactions:
            if currency is None:
                total_commission += commission_transactions.aggregate(
                    total=Sum("commission")
                )["total"]
            else:
                for commission in commission_transactions:
                    fx_rate = FX.get_rate(
                        commission.currency, currency, commission.date
                    )["FX"]
                    if fx_rate:
                        total_commission += commission.commission * fx_rate
            return round(Decimal(total_commission), 2)
        else:
            return Decimal(0)

    def __str__(self):
        """Return the string representation of the Brokers model."""
        return self.name  # Define how the broker is represented as a string


# Table with public asset transactions
class Transactions(models.Model):
    """Transactions model."""

    investor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="transactions"
    )
    account = models.ForeignKey(
        Accounts, on_delete=models.CASCADE, related_name="transactions"
    )
    security = models.ForeignKey(
        Assets,
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
    )
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="USD", null=False, blank=False
    )
    type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES, null=False)
    date = TimezoneAwareDateTimeField(db_index=True, null=False)
    quantity = models.DecimalField(
        max_digits=25, decimal_places=9, null=True, blank=True
    )
    price = models.DecimalField(
        max_digits=18, decimal_places=9, null=True, blank=True
    )  # For bonds: stored as percentage of par (e.g., 98.5 = 98.5%).
    # For others: actual price
    notional = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Notional/par value per bond at transaction time (for bonds only)",
    )
    cash_flow = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    # Sign reflects actual commission cash flow
    # (negative for outflow, positive for inflow)
    commission = models.DecimalField(
        max_digits=15, decimal_places=9, null=True, blank=True
    )
    # Accounts for sign of ACI (negative for buy, positive for sell)
    aci = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    # For bond redemptions: tracks the notional amount redeemed per bond
    notional_change = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Change in notional value (used for bond redemptions)",
    )
    comment = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        """
        Save the transaction.

        Override save to automatically create NotionalHistory for bond redemptions.
        """
        super().save(*args, **kwargs)

        # Auto-create NotionalHistory for bond redemptions
        if self.type in [
            TRANSACTION_TYPE_BOND_REDEMPTION,
            TRANSACTION_TYPE_BOND_MATURITY,
        ]:
            if self.security and self.notional_change and self.notional_change != 0:
                self._create_notional_history()

    def _create_notional_history(self):
        """Create NotionalHistory entry for this bond redemption."""
        from datetime import timedelta

        try:
            # Get bond metadata
            bond_meta = self.security.bond_metadata
            if not bond_meta:
                logger.warning(
                    f"No bond metadata for {self.security.name}, "
                    "cannot create NotionalHistory"
                )
                return

            # notional_change is already per-bond (calculated during import)
            notional_per_bond = self.notional_change

            # Calculate change_amount (negative for redemptions)
            change_amount_value = -notional_per_bond

            # Determine change reason
            change_reason = (
                "MATURITY"
                if self.type == TRANSACTION_TYPE_BOND_MATURITY
                else "REDEMPTION"
            )

            # Search for existing entry within ±7 days with similar change_amount
            # This handles cases where API event dates
            # differ from broker transaction dates
            # (e.g., event on Friday, transaction settles on Monday)
            date_range_start = self.date - timedelta(days=7)
            date_range_end = self.date + timedelta(days=7)

            # Tolerance for matching change_amount (e.g., 0.01 for rounding differences)
            amount_tolerance = Decimal("0.01")

            # Find potential matches
            nearby_entries = NotionalHistory.objects.filter(
                asset=self.security,
                date__gte=date_range_start,
                date__lte=date_range_end,
                change_reason=change_reason,
            )

            # Look for a matching entry based on similar change_amount
            matching_entry = None
            for entry in nearby_entries:
                if (
                    entry.change_amount
                    and abs(entry.change_amount - change_amount_value)
                    <= amount_tolerance
                ):
                    matching_entry = entry
                    break

            if matching_entry:
                # Update existing entry with actual transaction date
                old_date = matching_entry.date
                matching_entry.date = self.date
                matching_entry.change_amount = change_amount_value
                matching_entry.comment = (
                    f"Updated from transaction {self.id} "
                    f"(original API date: {old_date})"
                )
                matching_entry.save()

                logger.info(
                    f"Updated NotionalHistory for {self.security.name}: "
                    f"date {old_date} → {self.date}, "
                    f"notional={matching_entry.notional_per_unit}, "
                    f"change={change_amount_value}"
                )
            else:
                # Get current notional from previous history or initial
                previous_history = (
                    NotionalHistory.objects.filter(
                        asset=self.security, date__lt=self.date
                    )
                    .order_by("-date")
                    .first()
                )

                if previous_history:
                    previous_notional = previous_history.notional_per_unit
                else:
                    previous_notional = bond_meta.initial_notional

                # Calculate new notional per unit
                new_notional = previous_notional - notional_per_bond

                # No matching entry found, create new one
                NotionalHistory.objects.create(
                    asset=self.security,
                    date=self.date,
                    change_reason=change_reason,
                    notional_per_unit=new_notional,
                    change_amount=change_amount_value,
                    comment=f"Auto-created from transaction {self.id}",
                )

                logger.info(
                    f"Created NotionalHistory for {self.security.name}: "
                    f"notional={new_notional}, change={change_amount_value}"
                )

        except Exception as e:
            logger.error(
                f"Error creating NotionalHistory for transaction {self.id}: {e}",
                exc_info=True,
            )

    def get_price(self):
        """
        Get the effective price per unit for this transaction.

        For stocks/ETFs/etc: returns transaction.price as-is
        For bonds: converts percentage to actual price using notional
                   (price_percentage * notional / 100)

        Returns:
            Decimal: Effective price per unit, or None if price is not available
        """
        if not self.price:
            return None

        # Check if this is a bond transaction
        if self.security and self.security.type == "Bond":
            if self.notional:
                notional = self.notional
            else:
                # Pass account_id as a list for the __in lookup
                account_ids = [self.account_id] if self.account_id else None
                notional = self.security.get_effective_notional(
                    self.date, self.investor, account_ids, self.currency
                )
            # Bond price is stored as percentage of par
            # Convert to actual money per bond: price% * notional / 100
            return (self.price * notional) / Decimal(100)
        else:
            # For non-bonds, price is already in actual money terms
            return self.price

    def get_calculated_cash_flow(self, target_currency=None):
        """
        Calculate the net cash flow for this transaction.

        This is the SINGLE SOURCE OF TRUTH for cash flow calculations.
        Handles all transaction types and includes ACI, commission, etc.

        For trades (Buy/Sell):
            - cash_flow = -quantity * price + aci - commission
            - (Buy: negative, Sell: positive)

        For cash transactions/dividends/coupons:
            - Uses the cash_flow field directly

        For bond redemptions:
            - Uses the cash_flow field (amount received)

        Args:
            target_currency: Optional currency code for conversion.
                           If None, returns in transaction's currency.

        Returns:
            Decimal: Net cash flow (can be negative or positive)
        """
        # Initialize cash flow
        calculated_cash_flow = Decimal(0)

        # Types where cash_flow field is directly used
        cash_flow_types = [
            TRANSACTION_TYPE_CASH_IN,
            TRANSACTION_TYPE_CASH_OUT,
            TRANSACTION_TYPE_DIVIDEND,
            TRANSACTION_TYPE_COUPON,
            TRANSACTION_TYPE_TAX,
            TRANSACTION_TYPE_BROKER_COMMISSION,
            TRANSACTION_TYPE_BOND_REDEMPTION,
            TRANSACTION_TYPE_BOND_MATURITY,
            TRANSACTION_TYPE_INTEREST_INCOME,
        ]

        if self.type in cash_flow_types:
            # Use the cash_flow field directly
            calculated_cash_flow = self.cash_flow or Decimal(0)

        elif self.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL]:
            # Calculate from quantity and price
            if self.quantity and self.price is not None:
                effective_price = self.get_price() or Decimal(0)

                # Base cash flow: -quantity * price
                # Buy: negative quantity, negative cash flow
                # Sell: positive quantity, positive cash flow
                calculated_cash_flow = -Decimal(self.quantity) * effective_price

                # Add ACI (accrued interest for bonds)
                # Buy: ACI is negative (you pay it),
                # Sell: ACI is positive (you receive it)
                if self.aci:
                    calculated_cash_flow += Decimal(self.aci)

                # Subtract commission (always reduces cash)
                if self.commission:
                    calculated_cash_flow += Decimal(self.commission)

        # Convert to target currency if requested
        if target_currency and target_currency != self.currency:
            fx_rate = FX.get_rate(self.currency, target_currency, self.date)["FX"]
            calculated_cash_flow *= fx_rate

        return round(calculated_cash_flow, 2)

    def __str__(self):
        """Return the string representation of the Transactions model."""
        return f"{self.type} || {self.date}"


class Prices(models.Model):
    """Prices model."""

    date = TimezoneAwareDateField(null=False)
    security = models.ForeignKey(
        Assets, on_delete=models.CASCADE, related_name="prices"
    )
    price = models.DecimalField(max_digits=15, decimal_places=6, null=False)

    def __str__(self):
        """Return the string representation of the Prices model."""
        return f"{self.security.name} is at {self.price} on {self.date}"

    class Meta:
        """Meta class for the Prices model."""

        # Add constraints
        constraints = [
            models.UniqueConstraint(
                fields=["date", "security"], name="unique_security_price_entry"
            ),
        ]


def is_yahoo_finance_available():
    """
    Check yahoo finance availability.

    Check if Yahoo Finance is available by making a test request with proper headers.

    Returns:
        True if Yahoo Finance is available, False otherwise.
    """
    url = "https://finance.yahoo.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # noqa: E501
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",  # noqa: E501
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return True
    except (requests.ConnectionError, requests.Timeout):
        pass
    return False


def update_FX_from_Yahoo(base_currency, target_currency, date, max_attempts=5):
    """
    Fetch FX rate from Yahoo Finance.

    Note: Modern yfinance uses curl_cffi internally
    to handle headers and browser mimicking.
    We let yfinance handle the session to avoid conflicts.

    Args:
        base_currency: Base currency code (e.g., 'USD')
        target_currency: Target currency code (e.g., 'EUR')
        date: Date for which to fetch the rate
        max_attempts: Number of attempts to try fetching data

    Returns:
        dict with exchange_rate, actual_date, requested_date or None if failed
    """
    if not is_yahoo_finance_available():
        raise ConnectionError("Yahoo Finance is not available")

    # Define the currency pair (Yahoo Finance format: XXXYYY=X)
    currency_pair = f"{target_currency}{base_currency}=X"

    # Initialize a counter for the number of attempts
    attempt = 0

    while attempt < max_attempts:
        # Define the date for which you want the exchange rate
        end_date = date - timedelta(
            days=attempt - 1
        )  # Go back in time for each attempt.
        # Need to deduct 1 to get rate for exactly the date
        start_date = end_date - timedelta(
            days=1
        )  # Go back one day to ensure the date is covered

        # Fetch historical data for the currency pair within the date range
        try:
            # Let yfinance handle the session internally (uses curl_cffi for better browser mimicking) # noqa: E501
            ticker = yf.Ticker(currency_pair)
            # Note: Only set start and end, not period
            # (yfinance allows max 2 of period/start/end)
            exchange_rate_data = ticker.history(
                start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d")
            )

            # Add small delay to avoid rate limiting
            import time

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error fetching exchange rate data for {currency_pair}: {e}")
            attempt += 1
            continue

        if (
            not exchange_rate_data.empty
            and not exchange_rate_data["Close"].isnull().all()
        ):
            # Get the exchange rate for the specified date
            exchange_rate = round(exchange_rate_data["Close"].iloc[0], 6)
            actual_date = exchange_rate_data.index[0].date()  # Extract the actual date

            logger.info(
                f"Successfully fetched {currency_pair} rate for {actual_date}: "
                f"{exchange_rate}"
            )

            return {
                "exchange_rate": exchange_rate,
                "actual_date": actual_date,
                "requested_date": date,
            }

        # Increment the attempt counter
        attempt += 1
        logger.warning(
            f"Attempt {attempt}/{max_attempts} failed for {currency_pair} on {date}"
        )

    # If no data is found after max_attempts,
    # return None or an appropriate error message
    logger.error(
        f"Failed to fetch {currency_pair} after {max_attempts} attempts for date {date}"
    )
    return None


# Model to store the annual performance data
class AnnualPerformance(models.Model):
    """Annual performance model."""

    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    account_type = models.CharField(
        max_length=50,
        choices=ACCOUNT_TYPE_CHOICES,
        default=ACCOUNT_TYPE_ALL,  # From constants.py
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
        """Meta class for the AnnualPerformance model."""

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "investor",
                    "year",
                    "currency",
                    "restricted",
                    "account_type",
                    "account_id",
                ],
                name="unique_annual_performance",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(account_type=ACCOUNT_TYPE_ALL, account_id__isnull=True)
                    | ~models.Q(account_type=ACCOUNT_TYPE_ALL)
                    & models.Q(account_id__isnull=False)
                ),
                name="valid_annual_performance_selection",
            ),
        ]


class FXTransaction(models.Model):
    """FX transaction model."""

    investor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="fx_transactions"
    )
    account = models.ForeignKey(
        Accounts, on_delete=models.CASCADE, related_name="fx_transactions"
    )
    date = TimezoneAwareDateTimeField(null=False)
    from_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    to_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    from_amount = models.DecimalField(max_digits=20, decimal_places=9, null=False)
    to_amount = models.DecimalField(max_digits=20, decimal_places=9, null=False)
    exchange_rate = models.DecimalField(
        max_digits=15, decimal_places=9, null=False, blank=True
    )
    commission = models.DecimalField(
        max_digits=15, decimal_places=9, null=True, blank=True
    )
    commission_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, null=True, blank=True
    )
    comment = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        """Save the FX transaction."""
        if not self.exchange_rate:
            self.exchange_rate = self.from_amount / self.to_amount
        super().save(*args, **kwargs)

    def get_cash_flow_by_currency(self, currency: str) -> Decimal:
        """
        Get the cash flow for this FX transaction in a specific currency.

        This is the SINGLE SOURCE OF TRUTH for FX transaction cash flows per currency.
        Handles commission in different currencies correctly.

        Args:
            currency: The currency code to get cash flow for

        Returns:
            Decimal: Cash flow for the specified currency
                    - Negative for outflow (from_currency)
                    - Positive for inflow (to_currency)
                    - Includes commission in the appropriate currency
        """
        cash_flow = Decimal(0)

        # From currency: outflow (negative)
        if currency == self.from_currency:
            cash_flow = -self.from_amount
            # Add commission if it's in the from_currency (commission is negative, makes flow more negative) # noqa: E501
            if self.commission and self.commission_currency == self.from_currency:
                cash_flow += self.commission

        # To currency: inflow (positive)
        elif currency == self.to_currency:
            cash_flow = self.to_amount
            # Add commission if it's in the to_currency
            # (commission is negative, reduces the inflow)
            if self.commission and self.commission_currency == self.to_currency:
                cash_flow += self.commission

        # Commission in a third currency
        elif self.commission and currency == self.commission_currency:
            cash_flow = self.commission

        return cash_flow

    def __str__(self):
        """Return the string representation of the FX transaction."""
        return f"FX: {self.from_currency} to {self.to_currency} on {self.date}"


# Extensible metadata for different instrument types
class InstrumentMetadata(models.Model):
    """
    Abstract base model for instrument-specific metadata.

    This provides extensibility for bonds, options, futures, and other derivatives.
    """

    asset = models.OneToOneField(
        Assets, on_delete=models.CASCADE, related_name="%(class)s_metadata"
    )
    created_at = TimezoneAwareDateTimeField(auto_now_add=True)
    updated_at = TimezoneAwareDateTimeField(auto_now=True)

    class Meta:
        """Meta class for the InstrumentMetadata model."""

        abstract = True


class BondMetadata(InstrumentMetadata):
    """Bond-specific metadata for tracking fixed income instruments."""

    # Core bond characteristics
    issue_date = TimezoneAwareDateField(
        null=True, blank=True, help_text="Bond issue date"
    )
    maturity_date = TimezoneAwareDateField(
        null=True, blank=True, help_text="Bond maturity date"
    )
    initial_notional = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Initial par/face value per bond",
    )
    nominal_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        null=True,
        blank=True,
        help_text="Currency in which the nominal/face value is denominated",
    )
    coupon_rate = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Annual coupon rate (e.g., 5.25 for 5.25%)",
    )
    coupon_frequency = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of coupon payments per year (e.g., 2 for semi-annual)",
    )

    # Amortization tracking
    is_amortizing = models.BooleanField(
        default=False, help_text="Whether this bond has amortizing principal"
    )
    amortization_schedule = models.JSONField(
        null=True,
        blank=True,
        help_text="Optional: predefined amortization schedule as list of "
        "{date, amount}",
    )

    # Additional characteristics
    bond_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[
            ("FIXED", "Fixed Rate"),
            ("FLOATING", "Floating Rate"),
            ("ZERO_COUPON", "Zero Coupon"),
            ("INFLATION_LINKED", "Inflation Linked"),
            ("CONVERTIBLE", "Convertible"),
        ],
        help_text="Type of bond",
    )
    credit_rating = models.CharField(
        max_length=10, null=True, blank=True, help_text="Credit rating (e.g., AAA, BB+)"
    )

    def __str__(self):
        """Return the string representation of the bond metadata."""
        return f"Bond Metadata for {self.asset.name}"

    def get_current_notional(
        self, date, investor=None, account_ids=None, currency=None
    ):
        """
        Get the current notional value per bond at a given date.

        For non-amortizing bonds, returns the initial notional.
        For amortizing bonds, uses NotionalHistory if available,
        otherwise calculates from redemption transactions.

        Args:
            date: The date for which to get the notional
            investor: Optional investor filter
            account_ids: Optional account IDs filter
            currency: Optional currency filter
        Returns:
            Decimal: The notional value per bond at the given date
        """
        if currency is None:
            currency = self.asset.currency

        # Use nominal_currency if available, otherwise fall back to asset.currency
        source_currency = self.nominal_currency or self.asset.currency
        fx_rate = FX.get_rate(source_currency, currency, date)["FX"]
        logger.debug(
            f"FX rate for {self.asset.name} at {date} "
            f"({source_currency} to {currency}): {fx_rate}"
        )

        if not self.is_amortizing:
            return self.initial_notional * fx_rate

        # Try to get from NotionalHistory first (more efficient and accurate)
        try:
            latest_history = (
                NotionalHistory.objects.filter(asset=self.asset, date__lte=date)
                .order_by("-date")
                .first()
            )

            if latest_history:
                logger.debug(
                    f"Using NotionalHistory for {self.asset.name} at {date}: "
                    f"{latest_history.notional_per_unit}"
                )
                return latest_history.notional_per_unit * fx_rate
        except Exception as e:
            logger.warning(
                f"Error fetching NotionalHistory: {e}, falling back to transactions"
            )

        # Fallback: Calculate from transactions
        if not investor:
            logger.warning(
                "No NotionalHistory found and no investor provided for "
                f"{self.asset.name}, "
                f"returning initial notional"
            )
            return self.initial_notional * fx_rate

        redemption_filter = models.Q(
            security=self.asset,
            investor=investor,
            date__lte=date,
            type__in=[TRANSACTION_TYPE_BOND_REDEMPTION, TRANSACTION_TYPE_BOND_MATURITY],
        )

        # Ensure account_ids is a list for the __in lookup
        if account_ids:
            if isinstance(account_ids, int):
                account_ids = [account_ids]
            redemption_filter &= models.Q(account_id__in=account_ids)

        redemptions = Transactions.objects.filter(redemption_filter).aggregate(
            total_redeemed=Sum("notional_change")
        )["total_redeemed"] or Decimal(0)

        current_notional = (self.initial_notional) - abs(redemptions)
        logger.debug(
            f"Calculated notional from transactions for {self.asset.name}: "
            f"{current_notional} (initial: {self.initial_notional}, "
            f"redeemed: {redemptions})"
        )

        return current_notional

    def get_current_aci(self, date, currency=None, user=None, force_refresh=False):
        """
        Calculate the accrued interest for this bond at a given date.

        Uses the cached coupon schedule from BondCouponSchedule.
        If schedule is not available, and user is provided,
        attempts to fetch it from T-Bank API as fallback.

        Args:
            date: The date for which to calculate ACI
            currency: Optional currency for FX conversion (defaults to nominal_currency)
            user: Optional CustomUser to fetch schedule from API if not cached
            force_refresh: If True, refresh schedule even if it
                (for floating-rate bonds)

        Returns:
            dict with:
                - 'aci_amount': Decimal - ACI amount in requested currency per bond
                - 'aci_days': int - Number of days accrued
                - 'total_days': int - Total days in coupon period
                - 'coupon_start': date - Start of current coupon period
                - 'coupon_end': date - End of current coupon period
                - 'next_payment': date - Next coupon payment date
            Returns None if schedule is not available or bond has matured
        """
        # Find the relevant coupon period for this date
        # Get the most recent coupon end date that is >= date
        try:
            current_coupon = (
                BondCouponSchedule.objects.filter(
                    asset=self.asset, coupon_start_date__lte=date
                )
                .order_by("-coupon_start_date")
                .first()
            )

            # Fallback: fetch schedule if not found and user is provided
            if not current_coupon and user:
                logger.info(
                    f"No coupon schedule found for {self.asset.name}, "
                    "attempting to fetch from API"
                )
                try:
                    from asgiref.sync import async_to_sync

                    from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule

                    success = async_to_sync(fetch_and_cache_bond_coupon_schedule)(
                        self.asset, user, force_refresh=False
                    )

                    if success:
                        # Try again after fetching
                        current_coupon = (
                            BondCouponSchedule.objects.filter(
                                asset=self.asset, coupon_start_date__lte=date
                            )
                            .order_by("-coupon_start_date")
                            .first()
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to fetch coupon schedule for {self.asset.name}: {e}"
                    )

            # Check if coupon_amount is empty (floating-rate bond)
            # and force_refresh is needed
            if (
                current_coupon
                and not current_coupon.coupon_amount
                and user
                and force_refresh
            ):
                logger.info(
                    f"Coupon amount empty for {self.asset.name}, refreshing schedule"
                )
                try:
                    from asgiref.sync import async_to_sync

                    from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule

                    async_to_sync(fetch_and_cache_bond_coupon_schedule)(
                        self.asset, user, force_refresh=True
                    )

                    # Reload current coupon
                    current_coupon = (
                        BondCouponSchedule.objects.filter(
                            asset=self.asset, coupon_start_date__lte=date
                        )
                        .order_by("-coupon_start_date")
                        .first()
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to refresh coupon schedule for {self.asset.name}: {e}"
                    )

            if not current_coupon:
                logger.warning(
                    f"No coupon schedule found for {self.asset.name} at {date}. "
                    f"Provide 'user' parameter to fetch from API."
                )
                return None

            # Check if date is past bond maturity
            if self.maturity_date and date >= self.maturity_date:
                logger.debug(f"Bond {self.asset.name} has matured, no ACI")
                return None

            # Calculate days in period
            coupon_start = current_coupon.coupon_start_date
            coupon_end = current_coupon.coupon_end_date

            # Days accrued: from start to current date
            # (inclusive of start, exclusive of end)
            # Standard day count convention: actual/actual for most bonds
            days_accrued = (date - coupon_start).days
            total_days = (coupon_end - coupon_start).days

            # Don't allow negative days (if date is before coupon start)
            if days_accrued < 0:
                days_accrued = 0

            # Calculate ACI
            if current_coupon.coupon_amount and total_days > 0:
                # Use the exact coupon amount from schedule
                aci_amount = (
                    Decimal(current_coupon.coupon_amount)
                    * Decimal(days_accrued)
                    / Decimal(total_days)
                )
            elif self.coupon_rate and self.initial_notional and total_days > 0:
                # Fallback: calculate from coupon rate and notional
                # Annual coupon = notional * rate / 100
                # Period coupon = annual / frequency
                if self.coupon_frequency:
                    period_coupon = (
                        self.initial_notional
                        * self.coupon_rate
                        / Decimal(100)
                        / self.coupon_frequency
                    )
                    aci_amount = (
                        period_coupon * Decimal(days_accrued) / Decimal(total_days)
                    )
                else:
                    logger.warning(
                        "No coupon_frequency for {self.asset.name}, "
                        "cannot calculate ACI"
                    )
                    return None
            else:
                logger.warning(
                    f"Insufficient data to calculate ACI for {self.asset.name}: "
                    f"coupon_amount={current_coupon.coupon_amount}, "
                    f"coupon_rate={self.coupon_rate}, "
                    f"initial_notional={self.initial_notional}"
                )

                # Fallback: Try to fetch ACI from MICEX for floating-rate bonds
                if self.asset.secid:
                    logger.info(
                        f"Attempting to fetch ACI from MICEX for floating-rate bond "
                        f"{self.asset.name} (secid: {self.asset.secid})"
                    )
                    from core.micex_aci_utils import fetch_aci_from_micex

                    micex_aci = fetch_aci_from_micex(self.asset.secid, date)

                    if micex_aci:
                        # Got ACI from MICEX, convert currency if needed
                        aci_amount = micex_aci["aci_amount"]
                        micex_currency = micex_aci["currency"]

                        if currency and currency != micex_currency:
                            fx_rate = FX.get_rate(micex_currency, currency, date)["FX"]
                            aci_amount *= fx_rate
                            result_currency = currency
                        else:
                            result_currency = micex_currency

                        logger.info(
                            "Successfully retrieved ACI from MICEX for "
                            f"{self.asset.name}: "
                            f"{aci_amount} {result_currency}"
                        )

                        return {
                            "aci_amount": round(aci_amount, 2),
                            "aci_days": days_accrued,
                            "total_days": total_days,
                            "coupon_start": coupon_start,
                            "coupon_end": coupon_end,
                            "next_payment": current_coupon.payment_date,
                            "currency": result_currency,
                            "source": "MICEX",  # Indicate data source
                        }
                    else:
                        logger.warning(
                            f"Failed to fetch ACI from MICEX for {self.asset.name}, "
                            f"returning None"
                        )

                return None

            # Convert currency if requested
            if currency and currency != (self.nominal_currency or self.asset.currency):
                source_currency = self.nominal_currency or self.asset.currency
                fx_rate = FX.get_rate(source_currency, currency, date)["FX"]
                aci_amount *= fx_rate
            else:
                currency = self.nominal_currency or self.asset.currency

            return {
                "aci_amount": round(aci_amount, 2),
                "aci_days": days_accrued,
                "total_days": total_days,
                "coupon_start": coupon_start,
                "coupon_end": coupon_end,
                "next_payment": current_coupon.payment_date,
                "currency": currency,
            }

        except Exception as e:
            logger.error(
                f"Error calculating ACI for {self.asset.name}: {e}", exc_info=True
            )
            return None

    def get_total_aci_for_position(
        self, date, investor, currency=None, account_ids=None, user=None
    ):
        """
        Calculate total ACI for the entire bond position.

        Returns current ACI per bond * position, net of ACI paid at acquisition in the current coupon period. # noqa: E501

        This shows the "net accrued interest" value:
        - Current ACI per bond (what would be received if sold today)
        - Multiplied by position quantity
        - Minus ACI paid when initially acquiring bonds in this coupon period

        Args:
            date: The date for which to calculate total ACI
            investor: The investor whose position to calculate
            currency: Optional currency for conversion
            account_ids: Optional account filter
            user: Optional user for API fallback

        Returns:
            Decimal: Total ACI amount for the position in specified currency
        """
        # Get current ACI per bond
        aci_data = self.get_current_aci(date, currency, user)
        if not aci_data:
            return Decimal(0)

        # Get current position
        position_qty = self.asset.position(date, investor, account_ids)
        if not position_qty or position_qty == 0:
            return Decimal(0)

        # Total ACI for position
        total_aci = aci_data["aci_amount"] * Decimal(position_qty)

        # Subtract ACI paid when buying in the current coupon period
        # (to show net accrued interest since acquisition)
        current_coupon_start = aci_data.get("coupon_start")
        if current_coupon_start:
            query_date = date
            query_coupon_start = current_coupon_start

            aci_paid_in_period = self.asset.transactions.filter(
                type="Buy",
                aci__lt=0,
                date__gte=query_coupon_start,
                date__lte=query_date,
                investor=investor,
            )

            if account_ids is not None:
                if isinstance(account_ids, int):
                    account_ids = [account_ids]
                aci_paid_in_period = aci_paid_in_period.filter(
                    account_id__in=account_ids
                )

            # Sum ACI paid (negative values)
            if aci_paid_in_period.exists():
                target_currency = (
                    currency or self.nominal_currency or self.asset.currency
                )
                aci_paid_total = Decimal(0)

                for txn in aci_paid_in_period:
                    # Convert date to ensure proper comparison
                    txn_date = (
                        txn.date.date() if isinstance(txn.date, datetime) else txn.date
                    )
                    fx_rate = FX.get_rate(txn.currency, target_currency, txn_date)["FX"]
                    if fx_rate:
                        aci_paid_total += txn.aci * Decimal(fx_rate)

                # Add the negative ACI (subtract from total)
                total_aci += aci_paid_total

        return round(total_aci, 2)


class NotionalHistory(models.Model):
    """
    Track notional changes over time for bonds (and potentially other instruments).

    This is particularly important for amortizing bonds where the par value decreases.
    """

    asset = models.ForeignKey(
        Assets, on_delete=models.CASCADE, related_name="notional_history"
    )
    date = TimezoneAwareDateField(
        null=False, db_index=True, help_text="Date when the notional change occurred"
    )
    notional_per_unit = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=False,
        help_text="Notional/par value per unit after this change",
    )
    change_amount = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Amount of notional change (negative for redemptions)",
    )
    change_reason = models.CharField(
        max_length=50,
        choices=[
            ("REDEMPTION", "Partial Redemption"),
            ("MATURITY", "Maturity"),
            ("INITIAL", "Initial Issuance"),
            ("ADJUSTMENT", "Adjustment"),
        ],
        null=True,
        blank=True,
    )
    comment = models.TextField(null=True, blank=True)

    class Meta:
        """Meta class for the NotionalHistory model."""

        ordering = ["date"]
        # Note: Removed strict unique constraint on (asset, date, change_reason)
        # because API event dates may differ from actual broker transaction dates
        # (e.g., T+2 settlement, weekend processing). Instead, we handle duplicates
        # in application logic by matching on date proximity and change_amount.

    def __str__(self):
        """Return the string representation of the notional history."""
        return f"{self.asset.name}: Notional={self.notional_per_unit} on {self.date}"


class BondCouponSchedule(models.Model):
    """
    Cache bond coupon schedule data from T-Bank API.

    Used for calculating accrued interest at any given date.
    """

    asset = models.ForeignKey(
        Assets, on_delete=models.CASCADE, related_name="coupon_schedule"
    )
    coupon_number = models.IntegerField(help_text="Sequential coupon number")
    coupon_start_date = TimezoneAwareDateField(
        help_text="Start date of the coupon period"
    )
    coupon_end_date = TimezoneAwareDateField(
        help_text="End date of the coupon period (accrual cutoff)"
    )
    payment_date = TimezoneAwareDateField(
        help_text="Actual payment date for the coupon"
    )
    coupon_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Coupon payment amount per bond in nominal currency",
    )
    coupon_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        null=True,
        blank=True,
        help_text="Currency of the coupon payment",
    )
    coupon_type = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Coupon type (FIXED, FLOATING, etc.)",
    )
    last_updated = TimezoneAwareDateTimeField(
        auto_now=True, help_text="When this schedule was last fetched from API"
    )

    class Meta:
        """Meta class for the BondCouponSchedule model."""

        ordering = ["asset", "coupon_number"]
        indexes = [
            models.Index(fields=["asset", "coupon_end_date"]),
            models.Index(fields=["asset", "payment_date"]),
        ]
        unique_together = [["asset", "coupon_number"]]

    def __str__(self):
        """Return the string representation of the bond coupon schedule."""
        return f"{self.asset.name} - Coupon #{self.coupon_number} ({self.payment_date})"


class OptionMetadata(InstrumentMetadata):
    """Option-specific metadata. To be implemented in future phases."""

    strike_price = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True, help_text="Strike price"
    )
    expiration_date = TimezoneAwareDateField(
        null=True, blank=True, help_text="Option expiration date"
    )
    option_type = models.CharField(
        max_length=10,
        choices=[("CALL", "Call"), ("PUT", "Put")],
        null=True,
        blank=True,
        help_text="Option type",
    )
    underlying_asset = models.ForeignKey(
        Assets,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="options",
        help_text="Underlying asset",
    )
    contract_size = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Number of underlying units per contract",
    )

    def __str__(self):
        """Return the string representation of the option metadata."""
        return f"Option Metadata for {self.asset.name}"


class FutureMetadata(InstrumentMetadata):
    """Futures-specific metadata. To be implemented in future phases."""

    expiration_date = TimezoneAwareDateField(
        null=True, blank=True, help_text="Futures expiration date"
    )
    underlying_asset = models.ForeignKey(
        Assets,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="futures",
        help_text="Underlying asset",
    )
    contract_size = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Size of one futures contract",
    )
    tick_size = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Minimum price movement",
    )
    initial_margin = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Initial margin requirement",
    )

    def __str__(self):
        """Return the string representation of the future metadata."""
        return f"Future Metadata for {self.asset.name}"
