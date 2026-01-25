"""Django REST Framework serializers for user models.

This module provides serializers for User, AccountGroup, API tokens,
and other user-related models in the portfolio management system.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from common.models import Accounts, Brokers
from constants import (
    ACCOUNT_TYPE_ALL,
    ACCOUNT_TYPE_BROKER,
    ACCOUNT_TYPE_CHOICES,
    ACCOUNT_TYPE_GROUP,
    ACCOUNT_TYPE_INDIVIDUAL,
    CURRENCY_CHOICES,
    FREQUENCY_CHOICES,
    NAV_BARCHART_CHOICES,
    TIMELINE_CHOICES,
)
from users.models import AccountGroup, InteractiveBrokersApiToken, TinkoffApiToken

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user registration and profile management."""

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        """Meta class for UserSerializer."""

        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
        )
        extra_kwargs = {
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def validate(self, attrs):
        """Validate password fields match.

        Args:
            attrs: Dictionary of field data.

        Returns:
            dict: Validated data.

        Raises:
            ValidationError: If passwords don't match.
        """
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )
        return attrs

    def create(self, validated_data):
        """Create a new user instance.

        Args:
            validated_data: Dictionary of validated field data.

        Returns:
            User: Created user instance.
        """
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile information."""

    class Meta:
        """Meta class for UserProfileSerializer."""

        model = User
        fields = ("username", "first_name", "last_name", "email", "default_currency")
        read_only_fields = ("username",)


class UserSettingsSerializer(serializers.ModelSerializer):
    """Serializer for user settings and preferences."""

    default_currency = serializers.ChoiceField(choices=CURRENCY_CHOICES)
    default_currency = serializers.ChoiceField(choices=CURRENCY_CHOICES)
    chart_frequency = serializers.ChoiceField(choices=FREQUENCY_CHOICES)
    chart_timeline = serializers.ChoiceField(choices=TIMELINE_CHOICES)
    NAV_barchart_default_breakdown = serializers.ChoiceField(
        choices=NAV_BARCHART_CHOICES
    )
    selected_account_type = serializers.ChoiceField(choices=ACCOUNT_TYPE_CHOICES)
    selected_account_id = serializers.IntegerField(allow_null=True)

    class Meta:
        """Meta class for UserSettingsSerializer."""

        model = User
        fields = [
            "default_currency",
            "use_default_currency_where_relevant",
            "chart_frequency",
            "chart_timeline",
            "NAV_barchart_default_breakdown",
            "digits",
            "selected_account_type",
            "selected_account_id",
        ]

    def validate_digits(self, value):
        """Validate digits field is not too large.

        Args:
            value: Digits value to validate.

        Returns:
            int: Validated digits value.

        Raises:
            ValidationError: If value exceeds 6.
        """
        if value > 6:
            raise serializers.ValidationError(
                "The value for digits must be less than or equal to 6."
            )
        return value

    def validate(self, data):
        """Validate the combination of account_type and account_id.

        Args:
            data: Dictionary of field data.

        Returns:
            dict: Validated data.

        Raises:
            ValidationError: If validation fails.
        """
        account_type = data.get("selected_account_type")
        account_id = data.get("selected_account_id")
        user = self.context.get("request").user

        if account_type == ACCOUNT_TYPE_ALL:
            if account_id is not None:
                raise serializers.ValidationError(
                    {"selected_account_id": "'all' type should have null ID"}
                )
        elif account_type and account_id is not None:
            try:
                if account_type == ACCOUNT_TYPE_INDIVIDUAL:
                    Accounts.objects.get(id=account_id, broker__investor=user)
                elif account_type == ACCOUNT_TYPE_GROUP:
                    AccountGroup.objects.get(id=account_id, user=user)
                elif account_type == ACCOUNT_TYPE_BROKER:
                    Brokers.objects.get(id=account_id, investor=user)
            except (
                Accounts.DoesNotExist,
                AccountGroup.DoesNotExist,
                Brokers.DoesNotExist,
            ):
                raise serializers.ValidationError(
                    {"selected_account_id": f"Invalid {account_type} ID"}
                )
        elif account_type and account_id is None:
            raise serializers.ValidationError(
                {"selected_account_id": f"{account_type} type requires an ID"}
            )

        return data


class UserSettingsChoicesSerializer(serializers.Serializer):
    """Serializer for user settings choices."""

    currency_choices = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField())
    )
    frequency_choices = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField())
    )
    timeline_choices = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField())
    )
    nav_breakdown_choices = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField())
    )
    account_choices = serializers.ListField(child=serializers.ListField())


class DashboardSettingsSerializer(serializers.ModelSerializer):
    """Serializer for dashboard settings."""

    table_date = serializers.DateField(default=timezone.now().date())

    class Meta:
        """Meta class for DashboardSettingsSerializer."""

        model = User
        fields = ["default_currency", "digits", "table_date"]
        extra_kwargs = {
            "default_currency": {"label": "Currency"},
            "digits": {"label": "Number of digits"},
        }


class DashboardSettingsChoicesSerializer(serializers.Serializer):
    """Serializer for dashboard settings choices."""

    default_currency = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField())
    )


# Add new serializers for token management
class BaseApiTokenSerializer(serializers.ModelSerializer):
    """Base serializer for API token management."""

    token = serializers.CharField(write_only=True)

    class Meta:
        """Meta class for BaseApiTokenSerializer."""

        abstract = True
        fields = ["id", "token"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        """Create API token instance.

        Args:
            validated_data: Dictionary of validated field data.

        Returns:
            Created model instance.
        """
        token = validated_data.pop("token")
        user = validated_data.get("user")
        instance = super().create(validated_data)
        instance.set_token(token, user)
        return instance

    def update(self, instance, validated_data):
        """Update API token instance.

        Args:
            instance: Model instance to update.
            validated_data: Dictionary of validated field data.

        Returns:
            Updated model instance.
        """
        if "token" in validated_data:
            token = validated_data.pop("token")
            user = validated_data.get("user")
            instance = super().update(instance, validated_data)
            instance.set_token(token, user)
            return instance
        return super().update(instance, validated_data)


class TinkoffApiTokenSerializer(BaseApiTokenSerializer):
    """Serializer for T-Bank API token management."""

    broker = serializers.PrimaryKeyRelatedField(
        queryset=Brokers.objects.all(), write_only=True  # We only need it for writing
    )
    token_type = serializers.ChoiceField(
        choices=[
            ("read_only", "Read Only"),
            ("full_access", "Full Access"),
        ]
    )
    sandbox_mode = serializers.BooleanField(default=False)
    is_active = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta(BaseApiTokenSerializer.Meta):
        """Meta class for TinkoffApiTokenSerializer."""

        model = TinkoffApiToken
        fields = BaseApiTokenSerializer.Meta.fields + [
            "broker",
            "token_type",
            "sandbox_mode",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate_broker(self, value):
        """Check if the broker belongs to the user and is appropriate for the token type.

        Args:
            value: Broker instance to validate.

        Returns:
            Brokers: Validated broker instance.

        Raises:
            ValidationError: If broker doesn't belong to user.
        """
        if not value.investor == self.context["request"].user:
            raise serializers.ValidationError("Invalid broker selection")
        return value


class InteractiveBrokersApiTokenSerializer(BaseApiTokenSerializer):
    """Serializer for Interactive Brokers API token management."""

    class Meta(BaseApiTokenSerializer.Meta):
        """Meta class for InteractiveBrokersApiTokenSerializer."""

        model = InteractiveBrokersApiToken
        fields = BaseApiTokenSerializer.Meta.fields


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer that includes effective_current_date in the token payload."""

    def validate(self, attrs):
        """Validate and customize token response.

        Args:
            attrs: Dictionary of authentication attributes.

        Returns:
            dict: Token response data with effective_current_date.
        """
        data = super().validate(attrs)

        # Get or create default effective_current_date
        effective_date = date.today().isoformat()

        # Try to get effective_date from user's existing session data if migrating
        try:
            from django.contrib.sessions.models import Session

            recent_sessions = (
                Session.objects.filter(
                    session_data__contains=f'"_auth_user_id": "{self.user.id}"'
                )
                .order_by("-expire_date")
                .first()
            )

            if recent_sessions:
                session_data = recent_sessions.get_decoded()
                if session_data and "effective_current_date" in session_data:
                    effective_date = session_data["effective_current_date"]
        except Exception:
            # If anything goes wrong, just use today's date
            pass

        # Create custom refresh token with effective_current_date in payload
        refresh = RefreshToken.for_user(self.user)
        refresh["effective_current_date"] = effective_date

        # Add the tokens to the response data
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        data["effective_current_date"] = effective_date

        return data


class AccountGroupSerializer(serializers.ModelSerializer):
    """Serializer for account group management."""

    accounts = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Accounts.objects.all()
    )

    class Meta:
        """Meta class for AccountGroupSerializer."""

        model = AccountGroup
        fields = ["id", "name", "accounts", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, data):
        """Ensure user can only add their own broker accounts to groups.

        Args:
            data: Dictionary of field data.

        Returns:
            dict: Validated data.

        Raises:
            ValidationError: If invalid accounts are included.
        """
        # Ensure user can only add their own broker accounts to groups
        request = self.context.get("request")
        if request and request.user:
            user_accounts = Accounts.objects.filter(broker__investor=request.user)
            invalid_accounts = set(data["accounts"]) - set(user_accounts)

            if invalid_accounts:
                raise serializers.ValidationError(
                    {"accounts": "You can only add your own broker accounts to groups"}
                )

        return data

    def to_representation(self, instance):
        """Convert instance to representation with account details.

        Args:
            instance: AccountGroup instance.

        Returns:
            dict: Dictionary representation.
        """
        representation = super().to_representation(instance)
        # Add broker account details to the response
        representation["accounts"] = [
            {
                "id": account.id,
                "name": account.name,
            }
            for account in instance.accounts.all()
        ]
        return representation

    def create(self, validated_data):
        """Create account group for user.

        Args:
            validated_data: Dictionary of validated field data.

        Returns:
            AccountGroup: Created instance.
        """
        user = self.context["request"].user
        validated_data["user"] = user
        return super().create(validated_data)
