"""Common models."""

import logging
from datetime import date
from decimal import Decimal

from django.db import models

from constants import (
    ACCOUNT_TYPE_ALL,
    ACCOUNT_TYPE_CHOICES,
    ASSET_TYPE_CHOICES,
    ALL_CURRENCY_CHOICES,
    CURRENCY_CHOICES,
    DATA_SOURCE_CHOICES,
    EXPOSURE_CHOICES,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_CHOICES,
    TRANSACTION_TYPE_STOCK_SPLIT,
)

# from .utils import update_FX_database
from users.models import CustomUser

from .fields import NaiveDateTimeField

logger = logging.getLogger(__name__)


# Table with FX data
class FXManager(models.Manager):
    """Manager that emits post_save on bulk_create so cache invalidation fires.

    Django's default bulk_create skips signals, which would leave the FX graph
    cache stale after a bulk insert. This override creates rows individually
    when the batch is small (the common case for FX) and falls back to native
    bulk_create for large batches where per-row signals are impractical.
    """

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        objs_list = list(objs)
        if len(objs_list) <= 50:
            created = []
            for obj in objs_list:
                obj.save()
                created.append(obj)
            return created
        return super().bulk_create(
            objs_list, batch_size=batch_size, ignore_conflicts=ignore_conflicts
        )


class FX(models.Model):
    """FX rate storage.

    Long-format schema: one row per (date, currency pair) with a single
    ``rate`` column. Long-format storage convention: ``rate`` stores
    "from_currency per 1 to_currency" (quote-per-base). E.g. from="USD",
    to="EUR", rate=1.09 means "1.09 USD per EUR". ``get_rate`` inverts/divides
    as needed to return the "multiply source to get target" multiplier.
    """

    id = models.AutoField(primary_key=True)
    from_currency = models.CharField(max_length=3, null=True, blank=True)
    to_currency = models.CharField(max_length=3, null=True, blank=True)
    rate = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    # NOTE: ``date`` is intentionally NOT unique — multiple pairs share a date.
    date = models.DateField()
    investors = models.ManyToManyField(CustomUser, related_name="fx_rates")

    objects = FXManager()

    class Meta:
        """Meta class for the FX model."""

        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "from_currency", "to_currency"],
                name="unique_fx_date_pair",
            ),
        ]


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


# Public assets
class Assets(models.Model):
    """Assets model."""

    investors = models.ManyToManyField(CustomUser, related_name="assets", blank=True)
    type = models.CharField(max_length=15, choices=ASSET_TYPE_CHOICES, null=False)
    ISIN = models.CharField(max_length=12)
    name = models.CharField(max_length=70, null=False)
    ticker = models.CharField(max_length=10, null=True, blank=True)
    currency = models.CharField(max_length=4, choices=ALL_CURRENCY_CHOICES, default="USD", null=False)
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

        # Deferred import: services.bonds imports models from this module.
        from services.bonds import get_current_notional

        return get_current_notional(bond_meta, date, investor, account_ids, currency)

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
        max_length=4, choices=ALL_CURRENCY_CHOICES, default="USD", null=False, blank=False
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
    # Currency/asset of the commission (e.g. "BTC" for a BTC-denominated fee on
    # a BTC-USDT trade). Mirrors FXTransaction.commission_currency. Null when
    # the commission is in the trade's own currency or absent.
    commission_currency = models.CharField(
        max_length=4, choices=ALL_CURRENCY_CHOICES, null=True, blank=True
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

        The history-creation helpers live in ``services.transactions`` and are
        imported lazily here (Django calls ``save()`` as a lifecycle hook, and
        importing ``services.transactions`` at module top level would pull in
        ``services.fx`` -> this module, creating a cycle).
        """
        super().save(*args, **kwargs)

        # Auto-create NotionalHistory for bond redemptions
        if self.type in [
            TRANSACTION_TYPE_BOND_REDEMPTION,
            TRANSACTION_TYPE_BOND_MATURITY,
        ]:
            if self.security and self.notional_change and self.notional_change != 0:
                from services.transactions import create_notional_history

                create_notional_history(self)

        # Auto-create SplitHistory for stock splits
        if self.type == TRANSACTION_TYPE_STOCK_SPLIT:
            if self.security and self.split_from and self.split_to:
                from services.transactions import create_split_history

                create_split_history(self)

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
    from_currency = models.CharField(max_length=4, choices=ALL_CURRENCY_CHOICES, null=False)
    to_currency = models.CharField(max_length=4, choices=ALL_CURRENCY_CHOICES, null=False)
    from_amount = models.DecimalField(max_digits=20, decimal_places=9, null=False)
    to_amount = models.DecimalField(max_digits=20, decimal_places=9, null=False)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=9, null=False, blank=True)
    commission = models.DecimalField(max_digits=15, decimal_places=9, null=True, blank=True)
    commission_currency = models.CharField(
        max_length=4, choices=ALL_CURRENCY_CHOICES, null=True, blank=True
    )
    comment = models.TextField(null=True, blank=True)
    import_provider = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    import_account_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    import_event_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_group_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    import_event_type = models.CharField(max_length=50, null=True, blank=True)

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
