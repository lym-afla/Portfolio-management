"""Common models."""

import logging
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, DecimalException

from django.db import models
from django.db.models import Q, Sum

from constants import (
    ACCOUNT_TYPE_ALL,
    ACCOUNT_TYPE_CHOICES,
    ASSET_TYPE_CRYPTO,
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
    TRANSACTION_TYPE_STOCK_SPLIT,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)

# from .utils import update_FX_database
from users.models import CustomUser

from .fields import NaiveDateTimeField

logger = logging.getLogger(__name__)


def _fx_get_rate(source, target, date_as_of, investor=None):
    """Deferred-import bridge to ``services.fx.get_rate``.

    ``services.fx`` imports the ``FX`` model from this module at its own top
    level, so importing it at the top of ``common.models`` would create a
    circular import. Resolving it lazily (on first call) sidesteps that:
    by the time any model method needs an FX rate, both modules are fully
    loaded.
    """
    from services.fx import get_rate

    return get_rate(source, target, date_as_of, investor)


def _positions_position(asset, date, investor, account_ids=None):
    """Deferred-import bridge to ``services.positions.position``.

    Importing ``services.positions`` at the top of ``common.models`` would
    eventually pull in ``services.pricing`` -> ``services.fx`` -> this module,
    so we resolve it lazily on first call.
    """
    from services.positions import position

    return position(asset, date, investor, account_ids)


# Table with FX data
class FX(models.Model):
    """FX model."""

    id = models.AutoField(primary_key=True)
    date = models.DateField(unique=True)
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


# Brokers
class Brokers(models.Model):
    """Represents a broker entity (e.g., Tinkoff, Interactive Brokers)."""

    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="brokers")
    name = models.CharField(max_length=30, null=False)
    country = models.CharField(max_length=20)
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta class for the Brokers model."""

        unique_together = ["investor", "name"]
        ordering = ["name"]

    def __str__(self):
        """Return the string representation of the Brokers model."""
        return self.name


class Accounts(models.Model):
    """Represents a specific account at a broker."""

    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, related_name="accounts")
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

        Uses the centralized total_cash_flow() method for consistency.
        """
        balance = {}

        # Filter transactions up to and including the given date
        # Use date__date__lte to compare only the date portion, ignoring time component
        # of the DateTimeField

        # Process regular transactions using centralized cash flow calculation
        transactions = self.transactions.filter(date__date__lte=date)
        for transaction in transactions:
            # print(f"Processing transaction: {transaction}")
            cash_flow = transaction.total_cash_flow()
            if cash_flow == 0 and transaction.type in [
                TRANSACTION_TYPE_CRYPTO_REWARD,
                TRANSACTION_TYPE_CRYPTO_TRADE_IN,
                TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
                TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
                TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
            ]:
                continue
            balance[transaction.currency] = (
                balance.get(transaction.currency, Decimal(0)) + cash_flow
            )

        # Calculate balance from FX transactions using centralized method
        fx_transactions = self.fx_transactions.filter(date__date__lte=date)
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
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD", null=False)
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
    fund_fee = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    secid = models.CharField(max_length=10, null=True, blank=True)  # For MICEX
    tbank_instrument_uid = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        """Meta class for the Assets model."""

        constraints = [
            models.UniqueConstraint(
                fields=["ISIN", "currency"], name="unique_asset_currency_entry"
            ),
        ]

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

        reward_transactions = self.transactions.filter(
            type=TRANSACTION_TYPE_CRYPTO_REWARD,
            date__date__lte=query_date,
            investor=investor,
        )

        if account_ids is not None:
            reward_transactions = reward_transactions.filter(account_id__in=account_ids)

        if start_date is not None:
            reward_transactions = reward_transactions.filter(date__date__gte=start_date)

        for transaction in reward_transactions:
            reward_value = transaction.reward_value()
            if currency is not None and transaction.currency != currency:
                fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)["FX"]
                if fx_rate:
                    reward_value *= fx_rate
                else:
                    continue
            total_distributions += reward_value

        # For bonds: subtract ACI paid at acquisition
        # (negative ACI from Buy transactions)
        if self.is_bond:
            aci_transactions = self.transactions.filter(
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
        tax_transactions = self.transactions.filter(
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

    def get_commission(self, date, investor, currency=None, account_ids=None, start_date=None):
        """Calculate the comission for this asset."""
        total_commission = 0
        query_date = date
        commission_transactions = self.transactions.filter(
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

    def __str__(self):
        """Return the string representation of the Assets model."""
        return self.name  # Define how the asset is represented as a string


# Table with public asset transactions
class Transactions(models.Model):
    """Transactions model."""

    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="transactions")
    account = models.ForeignKey(Accounts, on_delete=models.CASCADE, related_name="transactions")
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
    date = NaiveDateTimeField(db_index=True, null=False)
    quantity = models.DecimalField(max_digits=25, decimal_places=9, null=True, blank=True)
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
    cash_flow = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Sign reflects actual commission cash flow
    # (negative for outflow, positive for inflow)
    commission = models.DecimalField(max_digits=15, decimal_places=9, null=True, blank=True)
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
    # For stock splits: ratio of shares before and after split
    split_from = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of shares before split (e.g., 1 for a 2:1 split)",
    )
    split_to = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of shares after split (e.g., 2 for a 2:1 split)",
    )
    comment = models.TextField(null=True, blank=True)
    merger = models.ForeignKey(
        "MergerRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Linked merger record (for Merger in/out transactions)",
    )
    import_provider = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    import_account_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    import_event_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_group_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_event_type = models.CharField(max_length=50, null=True, blank=True)

    def save(self, *args, **kwargs):
        """
        Save the transaction.

        Override save to automatically create:
        - NotionalHistory for bond redemptions
        - SplitHistory for corporate actions (stock splits)
        """
        super().save(*args, **kwargs)

        # Auto-create NotionalHistory for bond redemptions
        if self.type in [
            TRANSACTION_TYPE_BOND_REDEMPTION,
            TRANSACTION_TYPE_BOND_MATURITY,
        ]:
            if self.security and self.notional_change and self.notional_change != 0:
                self._create_notional_history()

        # Auto-create SplitHistory for stock splits
        if self.type == TRANSACTION_TYPE_STOCK_SPLIT:
            if self.security and self.split_from and self.split_to:
                self._create_split_history()

    def _create_notional_history(self):
        """Create NotionalHistory entry for this bond redemption."""
        from datetime import timedelta

        try:
            # Get bond metadata
            bond_meta = self.security.bond_metadata
            if not bond_meta:
                logger.warning(
                    f"No bond metadata for {self.security.name}, " "cannot create NotionalHistory"
                )
                return

            # notional_change is already per-bond (calculated during import)
            notional_per_bond = self.notional_change

            # Calculate change_amount (negative for redemptions)
            change_amount_value = -notional_per_bond

            # Determine change reason
            change_reason = (
                "MATURITY" if self.type == TRANSACTION_TYPE_BOND_MATURITY else "REDEMPTION"
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
                    and abs(entry.change_amount - change_amount_value) <= amount_tolerance
                ):
                    matching_entry = entry
                    break

            if matching_entry:
                # Update existing entry with actual transaction date
                old_date = matching_entry.date
                matching_entry.date = self.date
                matching_entry.change_amount = change_amount_value
                matching_entry.comment = (
                    f"Updated from transaction {self.id} " f"(original API date: {old_date})"
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
                    NotionalHistory.objects.filter(asset=self.security, date__lt=self.date)
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

    def _create_split_history(self):
        """
        Create SplitHistory entry for this Stock Split transaction.

        Uses the split_from and split_to fields directly.
        """
        try:
            # Avoid duplicate entries - check if entry already exists for this transaction
            existing = SplitHistory.objects.filter(transaction=self).first()
            if existing:
                # Update existing entry
                existing.date = self.date
                existing.split_from = self.split_from
                existing.split_to = self.split_to
                existing.comment = self.comment
                existing.save()
                logger.info(
                    f"Updated SplitHistory for {self.security.name}: "
                    f"{self.split_from}:{self.split_to} on {self.date}"
                )
            else:
                # Create new entry
                SplitHistory.objects.create(
                    asset=self.security,
                    transaction=self,
                    date=self.date,
                    split_from=self.split_from,
                    split_to=self.split_to,
                    source="TRANSACTION",
                    comment=self.comment,
                )
                logger.info(
                    f"Created SplitHistory for {self.security.name}: "
                    f"{self.split_from}:{self.split_to} on {self.date}"
                )

            # Update asset comment with split info
            if self.security:
                split_date = self.date.date() if hasattr(self.date, "date") else self.date
                split_note = f"Stock split {self.split_to}:{self.split_from} on {split_date}"
                if self.security.comment:
                    if split_note not in self.security.comment:
                        self.security.comment = f"{self.security.comment}\n{split_note}"
                else:
                    self.security.comment = split_note
                self.security.save(update_fields=["comment"])

        except Exception as e:
            logger.error(
                f"Error creating SplitHistory for transaction {self.id}: {e}",
                exc_info=True,
            )

    def is_position_increase(self):
        """Return True when the transaction increases asset quantity."""
        return self.quantity is not None and self.quantity > 0

    def is_paid_entry_transaction(self):
        """Return True when this transaction should affect paid entry price."""
        return self.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CRYPTO_TRADE_IN]

    def is_reward_transaction(self):
        """Return True when this transaction is crypto income."""
        return self.type == TRANSACTION_TYPE_CRYPTO_REWARD

    def is_disposal_transaction(self):
        """Return True when this transaction should realize gain/loss."""
        return self.type in [TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]

    def is_neutral_transfer_transaction(self):
        """Return True when quantity movement is principal transfer only."""
        return self.type in [
            TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
            TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        ]

    def reward_value(self):
        """Return event-date reward value without creating account cash."""
        if not self.is_reward_transaction() or self.quantity is None or self.price is None:
            return Decimal("0")
        return abs(self.quantity) * self.price

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

    def total_cash_flow(self, target_currency=None):
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

        For corporate actions (stock splits):
            - Always returns 0 (no cash movement)

        Args:
            target_currency: Optional currency code for conversion.
                           If None, returns in transaction's currency.

        Returns:
            Decimal: Net cash flow (can be negative or positive)
        """
        # Corporate actions have no cash flow
        if self.type == TRANSACTION_TYPE_STOCK_SPLIT:
            return Decimal(0)

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

            # Broker commission: the commission field IS the cash flow
            if (
                self.type == TRANSACTION_TYPE_BROKER_COMMISSION
                and not self.cash_flow
            ):
                calculated_cash_flow = self.commission or Decimal(0)

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
            fx_rate = _fx_get_rate(self.currency, target_currency, self.date)["FX"]
            calculated_cash_flow *= fx_rate

        return round(calculated_cash_flow, 2)

    def __str__(self):
        """Return the string representation of the Transactions model."""
        return f"{self.type} || {self.date}"

    class Meta:
        """Meta class for the Transactions model."""

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(import_event_id__isnull=True)
                    | models.Q(import_event_id="")
                    | (
                        models.Q(import_provider__isnull=False)
                        & ~models.Q(import_provider="")
                        & models.Q(import_account_id__isnull=False)
                        & ~models.Q(import_account_id="")
                    )
                ),
                name="transaction_import_event_requires_provider_account",
            ),
            models.UniqueConstraint(
                fields=[
                    "investor",
                    "account",
                    "import_provider",
                    "import_account_id",
                    "import_event_id",
                ],
                condition=models.Q(import_event_id__isnull=False) & ~models.Q(import_event_id=""),
                name="unique_transaction_provider_event",
            ),
        ]


class Prices(models.Model):
    """Prices model."""

    date = models.DateField(null=False)
    security = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name="prices")
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
                condition=(
                    models.Q(account_type=ACCOUNT_TYPE_ALL, account_id__isnull=True)
                    | ~models.Q(account_type=ACCOUNT_TYPE_ALL) & models.Q(account_id__isnull=False)
                ),
                name="valid_annual_performance_selection",
            ),
        ]


class FXTransaction(models.Model):
    """FX transaction model."""

    investor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="fx_transactions"
    )
    account = models.ForeignKey(Accounts, on_delete=models.CASCADE, related_name="fx_transactions")
    date = NaiveDateTimeField(null=False)
    from_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    to_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    from_amount = models.DecimalField(max_digits=20, decimal_places=9, null=False)
    to_amount = models.DecimalField(max_digits=20, decimal_places=9, null=False)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=9, null=False, blank=True)
    commission = models.DecimalField(max_digits=15, decimal_places=9, null=True, blank=True)
    commission_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, null=True, blank=True
    )
    comment = models.TextField(null=True, blank=True)
    import_provider = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    import_account_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    import_event_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_group_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_event_type = models.CharField(max_length=50, null=True, blank=True)

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

    class Meta:
        """Meta class for the FX transaction model."""

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(import_event_id__isnull=True)
                    | models.Q(import_event_id="")
                    | (
                        models.Q(import_provider__isnull=False)
                        & ~models.Q(import_provider="")
                        & models.Q(import_account_id__isnull=False)
                        & ~models.Q(import_account_id="")
                    )
                ),
                name="fx_transaction_import_event_requires_provider_account",
            ),
            models.UniqueConstraint(
                fields=[
                    "investor",
                    "account",
                    "import_provider",
                    "import_account_id",
                    "import_event_id",
                ],
                condition=models.Q(import_event_id__isnull=False) & ~models.Q(import_event_id=""),
                name="unique_fx_transaction_provider_event",
            ),
        ]


# Extensible metadata for different instrument types
class InstrumentMetadata(models.Model):
    """
    Abstract base model for instrument-specific metadata.

    This provides extensibility for bonds, options, futures, and other derivatives.
    """

    asset = models.OneToOneField(
        Assets, on_delete=models.CASCADE, related_name="%(class)s_metadata"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta class for the InstrumentMetadata model."""

        abstract = True


class BondMetadata(InstrumentMetadata):
    """Bond-specific metadata for tracking fixed income instruments."""

    # Core bond characteristics
    issue_date = models.DateField(null=True, blank=True, help_text="Bond issue date")
    maturity_date = models.DateField(null=True, blank=True, help_text="Bond maturity date")
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
        help_text="Optional: predefined amortization schedule as list of " "{date, amount}",
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

    def get_current_notional(self, date, investor=None, account_ids=None, currency=None):
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
        fx_rate = _fx_get_rate(source_currency, currency, date)["FX"]
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
            logger.warning(f"Error fetching NotionalHistory: {e}, falling back to transactions")

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
                BondCouponSchedule.objects.filter(asset=self.asset, coupon_start_date__lte=date)
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
                    logger.error(f"Failed to fetch coupon schedule for {self.asset.name}: {e}")

            # Check if coupon_amount is empty (floating-rate bond)
            # and force_refresh is needed
            if current_coupon and not current_coupon.coupon_amount and user and force_refresh:
                logger.info(f"Coupon amount empty for {self.asset.name}, refreshing schedule")
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
                    logger.error(f"Failed to refresh coupon schedule for {self.asset.name}: {e}")

            if not current_coupon:
                logger.warning(
                    f"No coupon schedule found for {self.asset.name} at {date}. "
                    f"Provide 'user' parameter to fetch from API."
                )
                return None

            # Check if date is past bond maturity
            if self.maturity_date:
                # Convert to date objects for comparison
                if hasattr(self.maturity_date, "date"):
                    maturity_date = self.maturity_date.date()
                else:
                    maturity_date = self.maturity_date

                if hasattr(date, "date"):
                    date_compare = date.date()
                else:
                    date_compare = date

                if date_compare >= maturity_date:
                    logger.debug(f"Bond {self.asset.name} has matured, no ACI")
                    return None

            # Calculate days in period
            coupon_start = current_coupon.coupon_start_date
            coupon_end = current_coupon.coupon_end_date

            # Validate that coupon dates exist
            if not coupon_start or not coupon_end:
                logger.error(
                    f"Invalid coupon schedule for {self.asset.name}: "
                    f"coupon_start={coupon_start}, coupon_end={coupon_end}"
                )
                return None

            # Convert to date objects for comparison
            if hasattr(coupon_start, "date"):
                coupon_start_date = coupon_start.date()
            else:
                coupon_start_date = coupon_start

            if hasattr(coupon_end, "date"):
                coupon_end_date = coupon_end.date()
            else:
                coupon_end_date = coupon_end

            if hasattr(date, "date"):
                date_compare = date.date()
            else:
                date_compare = date

            # Days accrued: from start to current date
            # (inclusive of start, exclusive of end)
            # Standard day count convention: actual/actual for most bonds
            days_accrued = (date_compare - coupon_start_date).days
            total_days = (coupon_end_date - coupon_start_date).days

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
                    aci_amount = period_coupon * Decimal(days_accrued) / Decimal(total_days)
                else:
                    logger.warning(
                        "No coupon_frequency for {self.asset.name}, " "cannot calculate ACI"
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
                            fx_rate = _fx_get_rate(micex_currency, currency, date)["FX"]
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
                fx_rate = _fx_get_rate(source_currency, currency, date)["FX"]
                aci_amount *= fx_rate
            else:
                currency = self.nominal_currency or self.asset.currency

            return {
                "aci_amount": round(aci_amount, 2),
                "aci_days": days_accrued,
                "total_days": total_days,
                "coupon_start": coupon_start_date,
                "coupon_end": coupon_end_date,
                "next_payment": current_coupon.payment_date,
                "currency": currency,
            }

        except Exception as e:
            logger.error(f"Error calculating ACI for {self.asset.name}: {e}", exc_info=True)
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
        position_qty = _positions_position(self.asset, date, investor, account_ids)
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
                date__date__gte=query_coupon_start,
                date__date__lte=query_date,
                investor=investor,
            )

            if account_ids is not None:
                if isinstance(account_ids, int):
                    account_ids = [account_ids]
                aci_paid_in_period = aci_paid_in_period.filter(account_id__in=account_ids)

            # Sum ACI paid (negative values)
            if aci_paid_in_period.exists():
                target_currency = currency or self.nominal_currency or self.asset.currency
                aci_paid_total = Decimal(0)

                for txn in aci_paid_in_period:
                    # Convert date to ensure proper comparison
                    txn_date = txn.date.date() if isinstance(txn.date, datetime) else txn.date
                    fx_rate = _fx_get_rate(txn.currency, target_currency, txn_date)["FX"]
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

    asset = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name="notional_history")
    date = models.DateField(
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

    asset = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name="coupon_schedule")
    coupon_number = models.IntegerField(help_text="Sequential coupon number")
    coupon_start_date = models.DateField(help_text="Start date of the coupon period")
    coupon_end_date = models.DateField(help_text="End date of the coupon period (accrual cutoff)")
    payment_date = models.DateField(help_text="Actual payment date for the coupon")
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
    last_updated = models.DateTimeField(
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
    expiration_date = models.DateField(null=True, blank=True, help_text="Option expiration date")
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

    expiration_date = models.DateField(null=True, blank=True, help_text="Futures expiration date")
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


class SplitHistory(models.Model):
    """
    Track stock split history for securities.

    This is used for:
    1. Adjusting historical prices when importing from T-Bank (which provides split-adjusted prices)
    2. Correctly calculating positions across splits
    3. Displaying split information to users

    Can be auto-created from Corporate Action transactions or manually entered.
    """

    SPLIT_SOURCE_CHOICES = [
        ("TRANSACTION", "From Corporate Action Transaction"),
        ("MANUAL", "Manually Entered"),
        ("IMPORT", "Imported from External Source"),
    ]

    asset = models.ForeignKey(
        Assets, on_delete=models.CASCADE, related_name="split_history"
    )
    transaction = models.ForeignKey(
        "Transactions",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="split_history_entries",
        help_text="Source Corporate Action transaction (if auto-created)",
    )
    date = models.DateField(
        null=False, db_index=True, help_text="Date when the split occurred"
    )
    split_from = models.PositiveIntegerField(
        help_text="Number of shares before split (e.g., 1 for a 2:1 split)"
    )
    split_to = models.PositiveIntegerField(
        help_text="Number of shares after split (e.g., 2 for a 2:1 split)"
    )
    adjustment_factor = models.DecimalField(
        max_digits=15,
        decimal_places=10,
        help_text="Price adjustment factor (split_from / split_to). "
        "Multiply historical prices by this to get post-split equivalent.",
    )
    source = models.CharField(
        max_length=20,
        choices=SPLIT_SOURCE_CHOICES,
        default="MANUAL",
        help_text="How this split record was created",
    )
    comment = models.TextField(null=True, blank=True)

    class Meta:
        """Meta class for the SplitHistory model."""

        ordering = ["date"]
        indexes = [
            models.Index(fields=["asset", "date"]),
        ]

    def save(self, *args, **kwargs):
        """Calculate adjustment_factor before saving."""
        if self.split_from and self.split_to:
            self.adjustment_factor = Decimal(str(self.split_from)) / Decimal(
                str(self.split_to)
            )
        super().save(*args, **kwargs)

    def __str__(self):
        """Return the string representation of the split history."""
        return (
            f"{self.asset.name}: {self.split_from}:{self.split_to} split on {self.date}"
        )


class MergerRecord(models.Model):
    """Track a merger/reorganization between two securities.

    Supports three types:
    - All-stock: old shares converted to new shares at a ratio (no cash)
    - All-cash: old shares liquidated for cash per share (no new security)
    - Hybrid: combination of stock conversion and cash payment
    """

    investor = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="merger_records"
    )
    old_security = models.ForeignKey(
        Assets, on_delete=models.CASCADE, related_name="mergers_out"
    )
    new_security = models.ForeignKey(
        Assets,
        on_delete=models.CASCADE,
        related_name="mergers_in",
        null=True,
        blank=True,
        help_text="New security (null for all-cash mergers)",
    )
    merger_date = models.DateField(help_text="Date when the merger took effect")
    conversion_ratio = models.DecimalField(
        max_digits=18,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="New shares per old share (e.g. 0.75 means 1 old → 0.75 new)",
    )
    cash_per_share = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0"),
        help_text="Cash received per old share (for all-cash or hybrid)",
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-merger_date"]

    def __str__(self):
        new_name = self.new_security.name if self.new_security else "Cash"
        return f"{self.old_security.name} → {new_name} on {self.merger_date}"
