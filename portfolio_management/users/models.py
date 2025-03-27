import base64
import logging

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from tinkoff.invest import Client, RequestError

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES

logger = logging.getLogger(__name__)


def get_encryption_key(user):
    """Generate a user-specific encryption key"""
    # Combine the user's ID with the SECRET_KEY
    key_material = f"{settings.SECRET_KEY}_{user.id}"
    # Create a consistent key by hashing the combined material
    key = base64.urlsafe_b64encode(key_material.encode()[:32].ljust(32, b"0"))
    return key


class CustomUser(AbstractUser):
    default_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="USD", blank=True, null=True
    )
    use_default_currency_where_relevant = models.BooleanField(default=False)
    chart_frequency = models.CharField(max_length=1, default="M")
    chart_timeline = models.CharField(max_length=3, default="6m")
    NAV_barchart_default_breakdown = models.CharField(
        max_length=12, choices=NAV_BARCHART_CHOICES, default="Asset type", blank=True, null=True
    )
    digits = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        error_messages={
            "max_value": "The value for digits must be less than or equal to 6.",
            "min_value": "The value for digits must be greater than or equal to 0.",
        },
    )
    ACCOUNT_TYPE_CHOICES = [
        ("account", "Individual Account"),
        ("group", "Account Group"),
        ("broker", "Broker"),
        ("all", "All Accounts"),
    ]

    selected_account_type = models.CharField(
        max_length=50, choices=ACCOUNT_TYPE_CHOICES, default="all"
    )
    selected_account_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the selected account, group, or broker (null for 'all')",
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(selected_account_type="all", selected_account_id__isnull=True)
                    | ~models.Q(selected_account_type="all")
                    & models.Q(selected_account_id__isnull=False)
                ),
                name="valid_account_selection",
            )
        ]


class BaseApiToken(models.Model):
    """Abstract base class for all broker API tokens"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    encrypted_token = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def set_token(self, token_value, user):
        """Encrypt and save token value"""
        try:
            key = get_encryption_key(user)
            f = Fernet(key)
            self.encrypted_token = f.encrypt(token_value.encode())
            self.save()
        except Exception as e:
            logger.error(f"Error encrypting token for user {user.id}: {str(e)}")
            raise

    def get_token(self, user=None):
        """Get decrypted token value"""
        if not user:
            raise ValueError("User is required to decrypt token")

        try:
            key = get_encryption_key(user)
            f = Fernet(key)
            if not self.encrypted_token:
                raise ValueError("No token stored")
            return f.decrypt(self.encrypted_token).decode()
        except Exception as e:
            logger.error(f"Error decrypting token for user {user.id}: {str(e)}")
            raise

    def __str__(self):
        return (
            f"{self.__class__.__name__} for {self.user.username} "
            f"({'Active' if self.is_active else 'Inactive'})"
        )


class TinkoffApiToken(BaseApiToken):
    """Tinkoff-specific API token model"""

    broker = models.ForeignKey(
        "common.Brokers", on_delete=models.CASCADE, related_name="tinkoff_tokens"
    )
    token_type = models.CharField(
        max_length=20,
        choices=[
            ("read_only", "Read Only"),
            ("full_access", "Full Access"),
        ],
    )
    sandbox_mode = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Tinkoff API Token"
        verbose_name_plural = "Tinkoff API Tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker", "token_type", "sandbox_mode"],
                condition=models.Q(is_active=True),
                name="unique_active_token",
            )
        ]

    def clean(self):
        """Validate token by attempting to connect to Tinkoff API"""
        try:
            token = self.get_token(self.user)
            with Client(token) as client:
                # Try to get accounts - this will fail if token is invalid
                client.users.get_accounts()
        except RequestError as e:
            metadata = e.args[2] if len(e.args) > 2 else None
            error_message = (
                metadata.message if metadata and hasattr(metadata, "message") else "Invalid token"
            )
            logger.error(f"Token validation failed: {error_message}")
            raise ValidationError(
                {"encrypted_token": f"Invalid Tinkoff API token: {error_message}"}
            )
        except Exception as e:
            logger.error(f"Token validation failed with unexpected error: {str(e)}")
            raise ValidationError({"encrypted_token": "Could not validate Tinkoff API token"})

    def save(self, *args, **kwargs):
        if not self.pk:  # New token
            # Deactivate existing active tokens of same type
            TinkoffApiToken.objects.filter(
                user=self.user,
                broker=self.broker,
                token_type=self.token_type,
                sandbox_mode=self.sandbox_mode,
                is_active=True,
            ).update(is_active=False)
            # Set new token as active
            self.is_active = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_token_type_display()} Token ({self.user.username} - {self.broker.name})"


class InteractiveBrokersApiToken(BaseApiToken):
    """Interactive Brokers-specific API token model"""

    account_id = models.CharField(
        max_length=50, help_text="IB Account ID associated with this token"
    )
    paper_trading = models.BooleanField(
        default=False, help_text="Whether this token is for paper trading"
    )

    class Meta:
        verbose_name = "Interactive Brokers API Token"
        verbose_name_plural = "Interactive Brokers API Tokens"
        unique_together = ["user", "account_id"]


class AccountGroup(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="account_groups")
    name = models.CharField(max_length=50)
    accounts = models.ManyToManyField("common.Accounts", related_name="groups")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "name"]
        ordering = ["name"]

    def __str__(self):
        return f"{self.user.username}'s {self.name} group"
