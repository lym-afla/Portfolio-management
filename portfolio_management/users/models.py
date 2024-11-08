from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import logging

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES

logger = logging.getLogger(__name__)

def get_encryption_key(user):
    """Generate a user-specific encryption key"""
    # Combine the user's ID with the SECRET_KEY
    key_material = f"{settings.SECRET_KEY}_{user.id}"
    # Create a consistent key by hashing the combined material
    key = base64.urlsafe_b64encode(key_material.encode()[:32].ljust(32, b'0'))
    return key

class CustomUser(AbstractUser):
    
    default_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', blank=True, null=True)
    use_default_currency_where_relevant = models.BooleanField(default=False)
    chart_frequency = models.CharField(max_length=1, default='M')
    chart_timeline = models.CharField(max_length=3, default='6m')
    NAV_barchart_default_breakdown = models.CharField(max_length=12, choices=NAV_BARCHART_CHOICES, default='Asset type', blank=True, null=True)
    digits = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        error_messages={
            'max_value': 'The value for digits must be less than or equal to 6.',
            'min_value': 'The value for digits must be greater than or equal to 0.',
            }
        )
    custom_broker_accounts = models.CharField(max_length=255, blank=True)

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
        return f"{self.__class__.__name__} for {self.user.username} ({'Active' if self.is_active else 'Inactive'})"

class TinkoffApiToken(BaseApiToken):
    """Tinkoff-specific API token model"""
    token_type = models.CharField(max_length=20, choices=[
        ('read_only', 'Read Only'),
        ('full_access', 'Full Access'),
    ])
    sandbox_mode = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Tinkoff API Token'
        verbose_name_plural = 'Tinkoff API Tokens'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'token_type', 'sandbox_mode'],
                condition=models.Q(is_active=True),
                name='unique_active_token'
            )
        ]

    def save(self, *args, **kwargs):
        if not self.pk:  # New token
            # Deactivate existing active tokens of same type
            TinkoffApiToken.objects.filter(
                user=self.user,
                token_type=self.token_type,
                sandbox_mode=self.sandbox_mode,
                is_active=True
            ).update(is_active=False)
            # Set new token as active
            self.is_active = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_token_type_display()} Token ({self.user.username})"

class InteractiveBrokersApiToken(BaseApiToken):
    """Interactive Brokers-specific API token model"""
    account_id = models.CharField(
        max_length=50,
        help_text="IB Account ID associated with this token"
    )
    paper_trading = models.BooleanField(
        default=False,
        help_text="Whether this token is for paper trading"
    )

    class Meta:
        verbose_name = "Interactive Brokers API Token"
        verbose_name_plural = "Interactive Brokers API Tokens"
        unique_together = ['user', 'account_id']

class AccountGroup(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='account_groups')
    name = models.CharField(max_length=50)
    broker_accounts = models.ManyToManyField('common.BrokerAccounts', related_name='groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.user.username}'s {self.name} group"
