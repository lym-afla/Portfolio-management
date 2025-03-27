from rest_framework import serializers

from common.models import Accounts, Assets, FXTransaction, Transactions
from constants import CURRENCY_CHOICES, TRANSACTION_TYPE_CHOICES


class TransactionFormSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(
        queryset=Accounts.objects.all(),
        required=True,
        error_messages={
            "required": "Please select a broker account.",
            "does_not_exist": "Invalid broker account selected.",
        },
    )

    class Meta:
        model = Transactions
        fields = [
            "id",
            "account",
            "security",
            "currency",
            "type",
            "date",
            "quantity",
            "price",
            "cash_flow",
            "commission",
            "comment",
        ]

    def validate_account(self, value):
        """Ensure broker account belongs to the current user through broker"""
        user = self.context.get("user")
        if user and value.broker.investor != user:
            raise serializers.ValidationError("Invalid broker account selected.")
        return value

    def validate(self, data):
        # Existing validation logic remains the same
        transaction_type = data.get("type")
        cash_flow = data.get("cash_flow")
        price = data.get("price")
        quantity = data.get("quantity")
        commission = data.get("commission")
        security = data.get("security")

        # Add broker account specific validation if needed
        account = data.get("account")
        if account and security:
            if security not in account.assets.all():
                raise serializers.ValidationError(
                    {
                        "security": (
                            "This security is not associated with the selected broker account."
                        )
                    }
                )

        # Rest of the validation remains the same
        if transaction_type in ["Buy", "Sell", "Dividend"] and not security:
            raise serializers.ValidationError(
                {"security": "Security must be selected for Buy, Sell, or Dividend transactions."}
            )

        if transaction_type in ["Cash in", "Cash out"] and security:
            raise serializers.ValidationError(
                {"security": "Security must not be selected for Cash in or Cash out transactions."}
            )

        if cash_flow is not None and transaction_type == "Cash out" and cash_flow >= 0:
            raise serializers.ValidationError(
                {"cash_flow": "Cash flow must be negative for cash-out transactions."}
            )

        if cash_flow is not None and transaction_type == "Cash in" and cash_flow <= 0:
            raise serializers.ValidationError(
                {"cash_flow": "Cash flow must be positive for cash-in transactions."}
            )

        if price is not None and price < 0:
            raise serializers.ValidationError({"price": "Price must be positive."})

        if transaction_type == "Buy" and quantity is not None and quantity <= 0:
            raise serializers.ValidationError(
                {"quantity": "Quantity must be positive for buy transactions."}
            )

        if transaction_type == "Sell" and quantity is not None and quantity >= 0:
            raise serializers.ValidationError(
                {"quantity": "Quantity must be negative for sell transactions."}
            )

        if commission is not None and commission >= 0:
            raise serializers.ValidationError({"commission": "Commission must be negative."})

        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["account"] = {
            "id": instance.account.id,
            "name": instance.account.name,
        }
        if instance.security:
            representation["security"] = {
                "id": instance.security.id,
                "name": instance.security.name,
            }
        return representation

    def get_form_structure(self, investor):
        """Return complete form structure including broker accounts"""
        return {
            "account_choices": self.get_account_choices(investor),
            "security_choices": self.get_security_choices(investor),
            "currency_choices": [{"value": c[0], "text": c[1]} for c in CURRENCY_CHOICES],
            "transaction_type_choices": [
                {"value": t[0], "text": t[1]} for t in TRANSACTION_TYPE_CHOICES
            ],
        }

    def get_account_choices(self, investor):
        return [
            {"value": str(account.pk), "text": account.name}
            for account in Accounts.objects.filter(broker__investor=investor).order_by("name")
        ]

    def get_security_choices(self, investor):
        choices = [
            {"value": str(security.pk), "text": security.name}
            for security in Assets.objects.filter(investors=investor).order_by("name")
        ]
        return choices


class FXTransactionFormSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(
        queryset=Accounts.objects.all(),
        required=True,
        error_messages={
            "required": "Please select a broker account.",
            "does_not_exist": "Invalid broker account selected.",
        },
    )

    class Meta:
        model = FXTransaction
        fields = [
            "id",
            "account",
            "date",
            "from_currency",
            "to_currency",
            "commission_currency",
            "from_amount",
            "to_amount",
            "exchange_rate",
            "commission",
            "comment",
        ]

    def validate_account(self, value):
        """Ensure broker account belongs to the current user through broker"""
        user = self.context.get("user")
        if user and value.broker.investor != user:
            raise serializers.ValidationError("Invalid broker account selected.")
        return value

    def validate(self, data):
        # Existing validation with added broker account context
        account = data.get("account")
        from_currency = data.get("from_currency")
        to_currency = data.get("to_currency")

        # Add validation for currencies against broker account if needed
        if account and (from_currency or to_currency):
            # Add any broker account specific currency validation here
            pass

        # Rest of the validation remains the same
        if data.get("from_amount") <= 0:
            raise serializers.ValidationError({"from_amount": "From amount must be positive."})
        if data.get("to_amount") <= 0:
            raise serializers.ValidationError({"to_amount": "To amount must be positive."})
        if data.get("commission") is not None and data["commission"] >= 0:
            raise serializers.ValidationError({"commission": "Commission must be negative."})

        # Calculate exchange rate
        from_amount = data.get("from_amount")
        to_amount = data.get("to_amount")
        if from_amount and to_amount:
            data["exchange_rate"] = from_amount / to_amount

        if data.get("commission") is not None and data["commission"] >= 0:
            raise serializers.ValidationError({"commission": "Commission must be negative."})

        return data

    def get_form_structure(self, investor):
        """Return complete form structure including broker accounts"""
        return {
            "account_choices": self.get_account_choices(investor),
            "currency_choices": self.get_currency_choices(),
            "fields": self.get_fields_structure(),
        }

    def get_fields_structure(self):
        """Return the structure of form fields"""
        return {
            "date": {"type": "date", "required": True},
            "from_amount": {"type": "number", "required": True},
            "to_amount": {"type": "number", "required": True},
            "commission": {"type": "number", "required": False},
            "comment": {"type": "text", "required": False},
        }

    def get_account_choices(self, investor):
        return [
            {"value": str(account.pk), "text": account.name}
            for account in Accounts.objects.filter(broker__investor=investor).order_by("name")
        ]

    def get_currency_choices(self):
        return [
            {"value": currency[0], "text": f"{currency[1]} ({currency[0]})"}
            for currency in CURRENCY_CHOICES
        ]
