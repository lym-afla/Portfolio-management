from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MaxValueValidator

from constants import CURRENCY_CHOICES

class CustomUser(AbstractUser):
    
    default_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', blank=True, null=True)
    chart_frequency = models.CharField(max_length=1, default='M')
    chart_timeline = models.CharField(max_length=3, default='6m')
    digits = models.IntegerField(
        default=0,
        validators=[MaxValueValidator(6)],
        error_messages={
            'max_value': 'The value for digits must be less than or equal to 6.',
            }
        )
