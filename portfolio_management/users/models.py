from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

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
