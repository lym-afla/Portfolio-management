"""Django REST Framework serializers for database models.

This module provides serializers for Assets, Accounts, Brokers, FX, Prices,
Transactions, and other database models used in the portfolio management system.
"""

from decimal import Decimal

from rest_framework import serializers

from common.models import (
    FX,
    Accounts,
    Assets,
    BondMetadata,
    Brokers,
    FXTransaction,
    Prices,
    Transactions,
)
from services.asset_resolver import BOND_FIELDS, resolve_or_create_asset
from constants import (
    ACCOUNT_TYPE_ALL,
    ACCOUNT_TYPE_BROKER,
    ACCOUNT_TYPE_GROUP,
    ACCOUNT_TYPE_INDIVIDUAL,
    CURRENCY_CHOICES,
    DATA_SOURCE_CHOICES,
)
from core.formatting_utils import format_bond_price, format_value
from core.user_utils import prepare_account_choices
from services.transactions import (
    get_cash_flow_by_currency,
    get_price,
    total_cash_flow,
)


class PriceImportSerializer(serializers.Serializer):
    """Serializer for price import requests.

    Validates parameters for bulk security price import operations
    including date ranges, frequencies, and target securities/accounts.
    """

    securities = serializers.PrimaryKeyRelatedField(
        queryset=Assets.objects.all(), many=True, required=False
    )
    accounts = serializers.PrimaryKeyRelatedField(
        queryset=Accounts.objects.all(), many=True, required=False
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    frequency = serializers.ChoiceField(
        choices=[
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
        ],
        required=False,
        allow_null=True,
    )
    single_date = serializers.DateField(
        required=False, input_formats=["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"]
    )

    def validate(self, data):
        """Validate the serializer data.

        Args:
            data: Dictionary containing fields to validate.

        Returns:
            Validated data dictionary.

        Raises:
            ValidationError: If validation fails.
        """
        print("Received data:", data)
        if not data.get("securities") and not data.get("accounts"):
            raise serializers.ValidationError(
                "Either securities or broker accounts must be selected."
            )

        if data.get("securities") and data.get("accounts"):
            raise serializers.ValidationError(
                "Only one of securities or broker accounts can be selected."
            )

        if (data.get("start_date") or data.get("end_date") or data.get("frequency")) and data.get(
            "single_date"
        ):
            raise serializers.ValidationError(
                "Either date range or single date should be provided, not both."
            )

        if data.get("start_date") or data.get("end_date"):
            if not data.get("frequency"):
                raise serializers.ValidationError("Frequency must be provided with date range.")
            if not (data.get("start_date") and data.get("end_date")):
                raise serializers.ValidationError(
                    "Both start date and end date must be provided for date range."
                )

        if not (
            data.get("start_date") and data.get("end_date") and data.get("frequency")
        ) and not data.get("single_date"):
            raise serializers.ValidationError(
                "Either date range with frequency or single date must be provided."
            )

        return data


class AccountSerializer(serializers.ModelSerializer):
    """Serializer for Account model.

    Serializes account information including broker details.
    """

    broker = serializers.SerializerMethodField()

    class Meta:
        """Meta class for AccountSerializer."""

        model = Accounts
        fields = ["id", "name", "broker", "restricted", "comment"]

    def get_broker(self, obj):
        """Get broker information for the account.

        Args:
            obj: Account instance.

        Returns:
            Dictionary with broker value and text, or None.
        """
        if obj.broker:
            return {"value": obj.broker.id, "text": obj.broker.name}
        return None

    def to_internal_value(self, data):
        """Convert external data to internal representation.

        Args:
            data: Dictionary of external data.

        Returns:
            Dictionary of internal model field values.
        """
        internal_data = super().to_internal_value(data)

        # Handle broker field consistently
        broker_data = data.get("broker")
        broker_id = None

        if isinstance(broker_data, dict):
            broker_id = broker_data.get("value")
        elif isinstance(broker_data, (int, str)):
            broker_id = int(broker_data)

        if broker_id:
            try:
                broker = Brokers.objects.get(id=broker_id)
                internal_data["broker"] = broker
            except Brokers.DoesNotExist:
                raise serializers.ValidationError({"broker": "Invalid broker ID"})

        return internal_data


class AccountPerformanceSerializer(serializers.Serializer):
    """Serializer for account performance calculation requests.

    Validates parameters for annual performance calculations including
    account selection, currency, and date ranges.
    """

    selection_account_type = serializers.ChoiceField(
        choices=[
            ACCOUNT_TYPE_ALL,
            ACCOUNT_TYPE_INDIVIDUAL,
            ACCOUNT_TYPE_GROUP,
            ACCOUNT_TYPE_BROKER,
        ]
    )
    selection_account_id = serializers.IntegerField(required=False, allow_null=True)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES + (("All", "All Currencies"),))
    is_restricted = serializers.ChoiceField(
        choices=[
            ("All", "All"),
            ("None", "No flag"),
            ("True", "Restricted"),
            ("False", "Not restricted"),
        ]
    )
    skip_existing_years = serializers.BooleanField(required=False, default=False)
    effective_current_date = serializers.DateField(required=True)

    def __init__(self, *args, **kwargs):
        """Initialize the serializer with investor context.

        Args:
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments, including 'investor'.
        """
        self.investor = kwargs.pop("investor", None)
        super().__init__(*args, **kwargs)

        # Get choices data using prepare_account_choices
        choices_data = prepare_account_choices(self.investor)
        self.choices_data = choices_data["options"]

    def validate(self, data):
        """Validate the complete data set.

        Called after individual field validation and only if all fields are valid.

        Args:
            data: Dictionary containing all field data.

        Returns:
            Validated data dictionary.

        Raises:
            ValidationError: If validation fails.
        """
        account_type = data.get("selection_account_type")
        account_id = data.get("selection_account_id")

        # Special case for 'all' type
        if account_type == "all":
            if account_id is not None:
                raise serializers.ValidationError(
                    {"selection_account_id": 'Should be null when type is "all"'}
                )
            return data

        # For other types, account_id is required
        if account_id is None:
            raise serializers.ValidationError(
                {"selection_account_id": 'Required when type is not "all"'}
            )

        # Check if the account type and ID combination exists in choices_data
        valid_selection = False
        for section, items in self.choices_data:
            if section != "__SEPARATOR__":
                for _, item_data in items:
                    if item_data["type"] == account_type and item_data.get("id") == account_id:
                        valid_selection = True
                        break

        if not valid_selection:
            raise serializers.ValidationError(
                {"selection_account_type": "Invalid account selection"}
            )

        return data

    def get_form_data(self):
        """Return the form structure for frontend.

        Returns:
            Dictionary containing form field choices and structure.
        """
        return {
            "account_choices": self.choices_data,
            "currency_choices": dict(self.fields["currency"].choices),
            "is_restricted_choices": dict(self.fields["is_restricted"].choices),
        }


class FXSerializer(serializers.ModelSerializer):
    """Serializer for FX (foreign exchange) model."""

    class Meta:
        """Meta class for FXSerializer."""

        model = FX
        fields = [
            "id",
            "date",
            "from_currency",
            "to_currency",
            "rate",
        ]
        read_only_fields = ["id"]  # Remove 'investor' from read_only_fields


class FXRateSerializer(serializers.Serializer):
    """Serializer for FX rate queries."""

    source = serializers.CharField(max_length=3)
    target = serializers.CharField(max_length=3)
    date = serializers.DateField()


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model with formatted output.

    Provides serialized transaction data with formatted values for
    display purposes including quantity, price, value, and cash flow.
    """

    # Model ID and type info
    id = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()

    # Formatted fields
    date = serializers.SerializerMethodField()
    type = serializers.CharField()
    quantity = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()
    cash_flow = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()
    aci = serializers.SerializerMethodField()
    cur = serializers.CharField(source="currency")  # Frontend expects 'cur'

    # Security info
    security = serializers.SerializerMethodField()
    instrument_type = serializers.SerializerMethodField()

    # Account info
    account = serializers.SerializerMethodField()

    # Bond-specific
    notional_change = serializers.SerializerMethodField()
    notional = serializers.SerializerMethodField()

    # Optional balance tracking
    balances = serializers.SerializerMethodField()

    # Merger info
    merger_info = serializers.SerializerMethodField()

    class Meta:
        """Meta class for TransactionSerializer."""

        model = Transactions
        fields = [
            "id",
            "transaction_type",
            "date",
            "type",
            "quantity",
            "price",
            "value",
            "cash_flow",
            "commission",
            "aci",
            "cur",
            "security",
            "instrument_type",
            "account",
            "notional_change",
            "notional",
            "balances",
            "merger_info",
        ]

    def get_digits(self):
        """Get the number of decimal places for formatting.

        Returns:
            int: Number of decimal places (default 2).
        """
        return self.context.get("digits", 2)  # Default to 2 if not provided

    def get_id(self, obj):
        """Return prefixed ID for frontend identification."""
        return f"regular_{obj.id}"

    def get_transaction_type(self, obj):
        """Return 'regular' to distinguish from FX transactions.

        Args:
            obj: Transaction instance.

        Returns:
            str: Transaction type identifier.
        """
        return "regular"

    def get_date(self, obj):
        """Format transaction date for display.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted date string.
        """
        return format_value(obj.date, "date", None, None)

    def get_quantity(self, obj):
        """Format transaction quantity for display.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted quantity string.
        """
        quantity = abs(obj.quantity) if obj.quantity else None
        return format_value(quantity, "quantity", None, 0)

    def get_price(self, obj):
        """Format price based on instrument type.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted price string.
        """
        instrument_type = self.get_instrument_type(obj)

        # For bonds, show price as percentage (as stored)
        if instrument_type and instrument_type.lower() == "bond":
            return format_bond_price(obj.price, self.get_digits())

        # For others, use get_price() which returns actual price
        effective_price = get_price(obj)
        return format_value(effective_price, "price", obj.currency, self.get_digits())

    def get_value(self, obj):
        """Calculate transaction value using centralized method.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted value string or None.
        """
        if obj.quantity and obj.price:
            value = -Decimal(obj.quantity) * Decimal(get_price(obj))
            return format_value(value, "value", obj.currency, self.get_digits())
        return None

    def get_cash_flow(self, obj):
        """Use centralized cash flow calculation.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted cash flow string or None.
        """
        # Use the centralized calculation method
        calculated_cash_flow = total_cash_flow(obj)
        return format_value(calculated_cash_flow, "cash_flow", obj.currency, self.get_digits())

    def get_commission(self, obj):
        """Format commission for display.

        Uses commission_currency (the fee's native asset, e.g. BTC for a
        BTC-denominated crypto fee) when set; otherwise the trade's currency.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted commission string or None.
        """
        fee_currency = obj.commission_currency or obj.currency
        return format_value(
            obj.commission, "commission", fee_currency, self.get_digits()
        )

    def get_aci(self, obj):
        """Format accrued interest for display.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted ACI string or None.
        """
        return format_value(obj.aci, "aci", obj.currency, self.get_digits())

    def get_security(self, obj):
        """Return security info as dictionary.

        Args:
            obj: Transaction instance.

        Returns:
            dict: Security information or None.
        """
        if obj.security:
            return {
                "id": obj.security.id,
                "name": obj.security.name,
                "type": obj.security.type,
            }
        return None

    def get_instrument_type(self, obj):
        """Return instrument type for frontend formatting.

        Args:
            obj: Transaction instance.

        Returns:
            str: Instrument type or None.
        """
        return obj.security.type if obj.security else None

    def get_account(self, obj):
        """Get account information for transaction.

        Args:
            obj: Transaction instance.

        Returns:
            dict: Account information or None.
        """
        return (
            {
                "id": obj.account.id,
                "name": obj.account.name,
                "broker_name": obj.account.broker.name,
            }
            if obj.account
            else None
        )

    def get_notional_change(self, obj):
        """Format notional change for display.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted notional change string or None.
        """
        return format_value(
            obj.notional_change, "notional_change", obj.currency, self.get_digits()
        )

    def get_notional(self, obj):
        """Format notional for display.

        Args:
            obj: Transaction instance.

        Returns:
            str: Formatted notional string or None.
        """
        return format_value(obj.notional, "notional", obj.currency, self.get_digits())

    def get_balances(self, obj):
        """Return balances if balance tracking is enabled in context."""
        if not self.context.get("include_balances", False):
            return None

        balance_tracker = self.context.get("balance_tracker", {})
        return balance_tracker.get(obj.id, {})

    def get_merger_info(self, obj):
        """Return merger details if this transaction is part of a merger."""
        if not obj.merger_id:
            return None
        merger = obj.merger
        return {
            "merger_id": merger.id,
            "old_security": {"id": merger.old_security_id, "name": merger.old_security.name},
            "new_security": (
                {"id": merger.new_security_id, "name": merger.new_security.name}
                if merger.new_security
                else None
            ),
            "conversion_ratio": str(merger.conversion_ratio) if merger.conversion_ratio else None,
            "cash_per_share": str(merger.cash_per_share),
        }


class FXTransactionSerializer(serializers.ModelSerializer):
    """Serializer for FX transactions with consistent formatting."""

    # Model ID and type info
    id = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()

    # Formatted fields
    date = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    # FX specific fields
    from_cur = serializers.CharField(source="from_currency")
    to_cur = serializers.CharField(source="to_currency")
    from_amount = serializers.SerializerMethodField()
    to_amount = serializers.SerializerMethodField()
    exchange_rate = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()
    commission_currency = serializers.CharField(allow_null=True)

    # Account info
    account = serializers.SerializerMethodField()

    # Optional balance tracking
    balances = serializers.SerializerMethodField()

    class Meta:
        """Meta class for FXTransactionSerializer."""

        model = FXTransaction
        fields = [
            "id",
            "transaction_type",
            "date",
            "type",
            "from_cur",
            "to_cur",
            "from_amount",
            "to_amount",
            "exchange_rate",
            "commission",
            "commission_currency",
            "account",
            "balances",
        ]

    def get_digits(self):
        """Get the number of decimal places for formatting.

        Returns:
            int: Number of decimal places (default 2).
        """
        return self.context.get("digits", 2)

    def get_id(self, obj):
        """Return prefixed ID for frontend identification.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Prefixed ID string.
        """
        return f"fx_{obj.id}"

    def get_transaction_type(self, obj):
        """Return 'fx' to distinguish from regular transactions.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Transaction type identifier.
        """
        return "fx"

    def get_date(self, obj):
        """Format transaction date for display.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Formatted date string.
        """
        return format_value(obj.date, "date", None, None)

    def get_type(self, obj):
        """Return transaction type string.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Transaction type.
        """
        return "FX"

    def get_from_amount(self, obj):
        """Use centralized cash flow calculation for from_currency.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Formatted from amount string.
        """
        cash_flow = get_cash_flow_by_currency(obj, obj.from_currency)
        return format_value(cash_flow, "value", obj.from_currency, self.get_digits())

    def get_to_amount(self, obj):
        """Use centralized cash flow calculation for to_currency.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Formatted to amount string.
        """
        cash_flow = get_cash_flow_by_currency(obj, obj.to_currency)
        return format_value(cash_flow, "value", obj.to_currency, self.get_digits())

    def get_exchange_rate(self, obj):
        """Format exchange rate for display.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Formatted exchange rate string.
        """
        return format_value(obj.exchange_rate, "fx_rate", None, 6)

    def get_commission(self, obj):
        """Format commission for display.

        Args:
            obj: FXTransaction instance.

        Returns:
            str: Formatted commission string or None.
        """
        if obj.commission:
            return format_value(
                obj.commission, "commission", obj.commission_currency, self.get_digits()
            )
        return None

    def get_account(self, obj):
        """Get account information for transaction.

        Args:
            obj: FXTransaction instance.

        Returns:
            dict: Account information or None.
        """
        return (
            {
                "id": obj.account.id,
                "name": obj.account.name,
                "broker_name": obj.account.broker.name,
            }
            if obj.account
            else None
        )

    def get_balances(self, obj):
        """Return balances if balance tracking is enabled in context.

        Args:
            obj: FXTransaction instance.

        Returns:
            dict: Balance information or None.
        """
        if not self.context.get("include_balances", False):
            return None

        balance_tracker = self.context.get("balance_tracker", {})
        return balance_tracker.get(obj.id, {})


class BrokerSerializer(serializers.ModelSerializer):
    """Serializer for Broker model."""

    class Meta:
        """Meta class for BrokerSerializer."""

        model = Brokers
        fields = ["id", "name", "country", "comment"]


class PriceSerializer(serializers.ModelSerializer):
    """Serializer for Price model with investor filtering."""

    class Meta:
        """Meta class for PriceSerializer."""

        model = Prices
        fields = ["id", "date", "security", "price"]

    def __init__(self, *args, **kwargs):
        """Initialize the serializer with investor context.

        Args:
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments, including 'investor'.
        """
        self.investor = kwargs.pop("investor", None)
        super().__init__(*args, **kwargs)

        if self.investor:
            # Filter securities by investor and order by name
            self.fields["security"].queryset = Assets.objects.filter(
                investors__id=self.investor.id
            ).order_by("name")


class SecuritySerializer(serializers.ModelSerializer):
    """Serializer for creating and updating Assets (securities).

    Handles bond metadata upsert and links the requesting user as an investor.
    Replaces the former SecurityForm (Django ModelForm).
    """

    # Bond metadata fields (not on the Assets model itself)
    initial_notional = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True
    )
    nominal_currency = serializers.ChoiceField(
        choices=CURRENCY_CHOICES, required=False, allow_null=True, allow_blank=True
    )
    issue_date = serializers.DateField(required=False, allow_null=True)
    maturity_date = serializers.DateField(required=False, allow_null=True)
    coupon_rate = serializers.DecimalField(
        max_digits=8, decimal_places=4, required=False, allow_null=True
    )
    coupon_frequency = serializers.IntegerField(required=False, allow_null=True)
    is_amortizing = serializers.BooleanField(required=False)
    bond_type = serializers.ChoiceField(
        choices=[
            ("FIXED", "Fixed Rate"),
            ("FLOATING", "Floating Rate"),
            ("ZERO_COUPON", "Zero Coupon"),
            ("INFLATION_LINKED", "Inflation Linked"),
            ("CONVERTIBLE", "Convertible"),
        ],
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    credit_rating = serializers.CharField(
        max_length=10, required=False, allow_null=True, allow_blank=True
    )
    confirm = serializers.BooleanField(required=False, default=False, write_only=True)

    class Meta:
        """Meta class for SecuritySerializer."""

        model = Assets
        fields = [
            "name",
            "ISIN",
            "ticker",
            "type",
            "currency",
            "exposure",
            "fund_fee",
            "initial_notional",
            "nominal_currency",
            "issue_date",
            "maturity_date",
            "coupon_rate",
            "coupon_frequency",
            "is_amortizing",
            "bond_type",
            "credit_rating",
            "restricted",
            "data_source",
            "yahoo_symbol",
            "update_link",
            "secid",
            "tbank_instrument_uid",
            "comment",
            "confirm",
        ]
        # Disable the auto-generated UniqueTogetherValidator on (ISIN, currency):
        # resolve_or_create_asset handles the unique constraint itself (with race
        # recovery), and the interactive flow needs duplicate (ISIN, currency)
        # submissions to reach serializer.save() so the view can return HTTP 409
        # with the field_diff/fillable conflict payload.
        validators = []

    def validate(self, attrs):
        """Replicate SecurityForm.clean() data-source + bond validation."""
        data_source = attrs.get("data_source")
        yahoo_symbol = attrs.get("yahoo_symbol")
        update_link = attrs.get("update_link")
        secid = attrs.get("secid")
        tbank_instrument_uid = attrs.get("tbank_instrument_uid")
        asset_type = attrs.get("type") or (self.instance.type if self.instance else None)

        if data_source == "YAHOO" and not yahoo_symbol:
            raise serializers.ValidationError(
                {"yahoo_symbol": "Yahoo symbol is required for Yahoo Finance data source."}
            )
        elif data_source == "FT" and not update_link:
            raise serializers.ValidationError(
                {"update_link": "Update link is required for Financial Times data source."}
            )
        elif data_source == "MICEX" and not secid:
            raise serializers.ValidationError({"secid": "Secid is required for MICEX data source."})
        elif data_source == "TBANK" and not tbank_instrument_uid:
            raise serializers.ValidationError(
                {
                    "tbank_instrument_uid": "T-Bank instrument UID is required for T-Bank data source."
                }
            )

        if asset_type == "Bond":
            if attrs.get("is_amortizing") and not attrs.get("initial_notional"):
                raise serializers.ValidationError(
                    {"initial_notional": "Initial notional is required for amortizing bonds."}
                )

        return attrs

    def _save_bond_metadata(self, asset):
        """Upsert BondMetadata for a bond asset. No-op for non-bonds."""
        if asset.type != "Bond":
            return
        bond_data = {}
        for field in BOND_FIELDS:
            value = self.validated_data.get(field)
            if value is not None:
                bond_data[field] = value
        if bond_data:
            BondMetadata.objects.update_or_create(asset=asset, defaults=bond_data)

    def create(self, validated_data):
        """Delegate to resolve_or_create_asset in interactive mode.

        May raise services.asset_resolver.AssetConflict if the security already
        exists and the user has not confirmed. The view catches this and returns
        HTTP 409.

        Note: the production create path (api_create_security) calls
        resolve_or_create_asset directly so it can read the full ResolveResult
        (created/linked) for the response. This method remains as a valid
        standalone entry point and is exercised by the serializer unit tests.
        """
        user = validated_data.pop("user", None)
        confirm = validated_data.pop("confirm", False)
        result = resolve_or_create_asset(
            user=user,
            isin=validated_data["ISIN"],
            currency=validated_data["currency"],
            submitted_fields=validated_data,
            mode="interactive",
            confirm=confirm,
        )
        return result.asset

    def update(self, instance, validated_data):
        """Update the Asset fields and upsert bond metadata."""
        user = validated_data.pop("user", None)
        validated_data.pop("confirm", False)  # write-only, not used on update
        for field, value in validated_data.items():
            if field not in BOND_FIELDS:
                setattr(instance, field, value)
        instance.save()
        if user is not None and not instance.investors.filter(pk=user.pk).exists():
            instance.investors.add(user)
        self._save_bond_metadata(instance)
        return instance
