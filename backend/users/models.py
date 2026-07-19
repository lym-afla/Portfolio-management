"""Users models."""

import base64
import logging

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from t_tech.invest import Client, RequestError

from constants import ACCOUNT_TYPE_CHOICES, CURRENCY_CHOICES, NAV_BARCHART_CHOICES

logger = logging.getLogger(__name__)

# Current encryption key version. Increment when rotating keys.
# Version 1 = legacy truncation scheme (backward compat for existing tokens).
# Version 2 = HKDF-SHA256 derivation.
ENCRYPTION_KEY_VERSION = 2


def _derive_key_v1(user):
    """Legacy key derivation (backward compatibility for existing tokens).

    Truncates/pads SECRET_KEY + user_id to 32 bytes. Not a real KDF —
    preserved so existing v1 tokens can still decrypt.
    """
    key_material = f"{settings.SECRET_KEY}_{user.id}"
    return base64.urlsafe_b64encode(key_material.encode()[:32].ljust(32, b"0"))


def _derive_key_v2(user, salt=None):
    """HKDF-based key derivation (current).

    Uses HMAC-SHA256 to derive a 32-byte Fernet key from
    SECRET_KEY + user ID. An optional salt allows per-token key derivation.
    """
    ikm = f"{settings.SECRET_KEY}:{user.id}".encode()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"portfolio-management-token-encryption-v2",
    )
    raw_key = hkdf.derive(ikm)
    return base64.urlsafe_b64encode(raw_key)


def get_encryption_key(user, version=ENCRYPTION_KEY_VERSION, salt=None):
    """Get the Fernet encryption key for a user.

    Supports key versioning for forward migration and rotation.
    Version 1 = legacy truncation (backward compat).
    Version 2 = HKDF-SHA256 (current).
    """
    if version == 1:
        return _derive_key_v1(user)
    return _derive_key_v2(user, salt)


class CustomUser(AbstractUser):
    """Custom user model."""

    default_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="USD", blank=True, null=True
    )
    use_default_currency_where_relevant = models.BooleanField(default=False)
    chart_frequency = models.CharField(max_length=1, default="M")
    chart_timeline = models.CharField(max_length=3, default="6m")
    NAV_barchart_default_breakdown = models.CharField(
        max_length=12,
        choices=NAV_BARCHART_CHOICES,
        default="Asset type",
        blank=True,
        null=True,
    )
    digits = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        error_messages={
            "max_value": "The value for digits must be less than or equal to 6.",
            "min_value": "The value for digits must be greater than or equal to 0.",
        },
    )

    selected_account_type = models.CharField(
        max_length=50,
        choices=ACCOUNT_TYPE_CHOICES,
        default="all",
    )
    selected_account_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the selected account, group, or broker (null for 'all')",
    )

    class Meta(AbstractUser.Meta):
        """Meta class for the custom user model."""

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(selected_account_type="all", selected_account_id__isnull=True)
                    | ~models.Q(selected_account_type="all")
                    & models.Q(selected_account_id__isnull=False)
                ),
                name="valid_account_selection",
            )
        ]


class BaseApiToken(models.Model):
    """Abstract base class for all broker API tokens."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    encrypted_token = models.BinaryField()
    key_version = models.IntegerField(default=1, help_text="Encryption key version")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta class for the base api token model."""

        abstract = True

    def set_token(self, token_value, user):
        """Encrypt and save token value using the current key version."""
        try:
            key = get_encryption_key(user, version=ENCRYPTION_KEY_VERSION)
            f = Fernet(key)
            self.encrypted_token = f.encrypt(token_value.encode())
            self.key_version = ENCRYPTION_KEY_VERSION
            self.save()
        except Exception as e:
            logger.error(f"Error encrypting token for user {user.id}: {str(e)}")
            raise

    def get_token(self, user=None):
        """Get decrypted token value.

        Uses the token's stored key_version to select the correct derivation.
        Legacy tokens (version 1) decrypt with the old truncation scheme.
        """
        if not user:
            raise ValueError("User is required to decrypt token")

        try:
            key = get_encryption_key(user, version=self.key_version)
            f = Fernet(key)
            if not self.encrypted_token:
                raise ValueError("No token stored")
            return f.decrypt(self.encrypted_token).decode()
        except Exception as e:
            logger.error(f"Error decrypting token for user {user.id}: {str(e)}")
            raise

    def __str__(self):
        """Return the string representation of the base api token."""
        return (
            f"{self.__class__.__name__} for {self.user.username} "
            f"({'Active' if self.is_active else 'Inactive'})"
        )


class TinkoffApiToken(BaseApiToken):
    """Tinkoff-specific API token model."""

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
        """Meta class for the tinkoff api token model."""

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
        """Validate token by attempting to connect to Tinkoff API."""
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
        """Save the tinkoff api token."""
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
        """Return the string representation of the tinkoff api token."""
        return (
            f"{self.get_token_type_display()} Token " f"({self.user.username} - {self.broker.name})"
        )


class BybitApiToken(BaseApiToken):
    """Bybit-specific API credentials."""

    broker = models.ForeignKey(
        "common.Brokers", on_delete=models.CASCADE, related_name="bybit_tokens"
    )
    api_key = models.CharField(max_length=120)
    testnet = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        """Meta class for the bybit api token model."""

        verbose_name = "Bybit API Token"
        verbose_name_plural = "Bybit API Tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker", "testnet"],
                condition=models.Q(is_active=True),
                name="unique_active_bybit_token",
            )
        ]

    def save(self, *args, **kwargs):
        """Save the bybit api token."""
        if self.is_active:
            BybitApiToken.objects.filter(
                user=self.user,
                broker=self.broker,
                testnet=self.testnet,
                is_active=True,
            ).exclude(pk=self.pk).update(is_active=False)
        elif not self.pk:
            self.is_active = True
            BybitApiToken.objects.filter(
                user=self.user,
                broker=self.broker,
                testnet=self.testnet,
                is_active=True,
            ).update(is_active=False)
        super().save(*args, **kwargs)

    def set_api_secret(self, api_secret, user):
        """Encrypt and save the Bybit API secret."""
        self.set_token(api_secret, user)

    def get_api_secret(self, user):
        """Decrypt the Bybit API secret."""
        return self.get_token(user)

    def __str__(self):
        """Return the string representation of the bybit api token."""
        return f"Bybit token ({self.user.username} - {self.broker.name})"


class OKXApiToken(BaseApiToken):
    """OKX-specific API credentials."""

    broker = models.ForeignKey(
        "common.Brokers", on_delete=models.CASCADE, related_name="okx_tokens"
    )
    api_key = models.CharField(max_length=120)
    encrypted_passphrase = models.BinaryField()
    simulated_trading = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        """Meta class for the okx api token model."""

        verbose_name = "OKX API Token"
        verbose_name_plural = "OKX API Tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker", "simulated_trading"],
                condition=models.Q(is_active=True),
                name="unique_active_okx_token",
            )
        ]

    def save(self, *args, **kwargs):
        """Save the OKX api token."""
        if self.is_active:
            OKXApiToken.objects.filter(
                user=self.user,
                broker=self.broker,
                simulated_trading=self.simulated_trading,
                is_active=True,
            ).exclude(pk=self.pk).update(is_active=False)
        elif not self.pk:
            self.is_active = True
            OKXApiToken.objects.filter(
                user=self.user,
                broker=self.broker,
                simulated_trading=self.simulated_trading,
                is_active=True,
            ).update(is_active=False)
        super().save(*args, **kwargs)

    def set_credentials(self, api_secret, passphrase, user):
        """Encrypt and save the OKX API secret and passphrase."""
        try:
            key = get_encryption_key(user, version=ENCRYPTION_KEY_VERSION)
            f = Fernet(key)
            self.encrypted_token = f.encrypt(api_secret.encode())
            self.encrypted_passphrase = f.encrypt(passphrase.encode())
            self.key_version = ENCRYPTION_KEY_VERSION
            self.save()
        except Exception as e:
            logger.error(f"Error encrypting OKX credentials for user {user.id}: {str(e)}")
            raise

    def get_api_secret(self, user):
        """Decrypt the OKX API secret."""
        return self.get_token(user)

    def set_passphrase(self, passphrase, user):
        """Encrypt and save the OKX passphrase."""
        try:
            key = get_encryption_key(user, version=self.key_version)
            f = Fernet(key)
            self.encrypted_passphrase = f.encrypt(passphrase.encode())
            self.save()
        except Exception as e:
            logger.error(f"Error encrypting OKX passphrase for user {user.id}: {str(e)}")
            raise

    def get_passphrase(self, user):
        """Decrypt the OKX passphrase."""
        try:
            key = get_encryption_key(user, version=self.key_version)
            f = Fernet(key)
            return f.decrypt(self.encrypted_passphrase).decode()
        except Exception as e:
            logger.error(f"Error decrypting OKX passphrase for user {user.id}: {str(e)}")
            raise

    def __str__(self):
        """Return the string representation of the okx api token."""
        return f"OKX token ({self.user.username} - {self.broker.name})"


class InteractiveBrokersApiToken(BaseApiToken):
    """Interactive Brokers-specific API token model."""

    account_id = models.CharField(
        max_length=50,
        help_text="IB Account ID associated with this token",
    )
    paper_trading = models.BooleanField(
        default=False,
        help_text="Whether this token is for paper trading",
    )

    class Meta:
        """Meta class for the interactive brokers api token model."""

        verbose_name = "Interactive Brokers API Token"
        verbose_name_plural = "Interactive Brokers API Tokens"
        unique_together = ["user", "account_id"]


class AccountGroup(models.Model):
    """Account group model."""

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="account_groups")
    name = models.CharField(max_length=50)
    accounts = models.ManyToManyField("common.Accounts", related_name="groups")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta class for the account group model."""

        unique_together = ["user", "name"]
        ordering = ["name"]

    def __str__(self):
        """Return the string representation of the account group."""
        return f"{self.user.username}'s {self.name} group"
