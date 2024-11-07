from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings
from cryptography.fernet import Fernet
import os
import base64

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES

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
    custom_brokers = models.JSONField(default=list, blank=True)  # Store list of broker IDs as JSON

class BaseApiToken(models.Model):
    """Abstract base class for all broker API tokens"""
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='%(class)s_tokens'
    )
    encrypted_token = models.BinaryField(
        help_text="Encrypted API token"
    )
    key_part = models.BinaryField(
        help_text="User-specific part of encryption key"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this token is currently active"
    )

    class Meta:
        abstract = True

    @classmethod
    def get_encryption_key(cls, key_part):
        """Combines server key with user-specific key part"""
        server_key = base64.urlsafe_b64decode(settings.SERVER_ENCRYPTION_KEY)
        combined_key = bytes([a ^ b for a, b in zip(server_key, key_part)])
        return base64.urlsafe_b64encode(combined_key)

    def set_token(self, token):
        """Encrypts and saves the API token"""
        self.key_part = os.urandom(32)
        
        # Get the combined encryption key
        encryption_key = self.get_encryption_key(self.key_part)
        
        # Create Fernet instance with combined key
        f = Fernet(encryption_key)
        
        # Encrypt the token
        self.encrypted_token = f.encrypt(token.encode())
        self.save()

    def get_token(self):
        """
        Decrypts and returns the API token
        """
        # Get the combined encryption key
        encryption_key = self.get_encryption_key(self.key_part)
        
        # Create Fernet instance with combined key
        f = Fernet(encryption_key)
        
        # Decrypt and return the token
        return f.decrypt(self.encrypted_token).decode()

    def __str__(self):
        return f"{self.__class__.__name__} for {self.user.username} ({'Active' if self.is_active else 'Inactive'})"

class TinkoffApiToken(BaseApiToken):
    """Tinkoff-specific API token model"""
    TOKEN_TYPE_CHOICES = [
        ('read_only', 'Read Only'),
        ('full_access', 'Full Access'),
    ]
    
    token_type = models.CharField(
        max_length=20,
        choices=TOKEN_TYPE_CHOICES,
        default='read_only'
    )
    sandbox_mode = models.BooleanField(
        default=False,
        help_text="Whether this token is for sandbox environment"
    )

    class Meta:
        verbose_name = "Tinkoff API Token"
        verbose_name_plural = "Tinkoff API Tokens"
        unique_together = ['user', 'token_type', 'sandbox_mode']

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
