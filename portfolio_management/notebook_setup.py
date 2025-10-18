#!/usr/bin/env python
"""
Safe Django initialization for Jupyter notebooks.
Import this at the top of your notebook:

```python
import sys
import os

# Add the project root to the path
if os.path.abspath('.') not in sys.path:
    sys.path.append(os.path.abspath('.'))

# Import the setup module
from notebook_setup import setup_django
setup_django()

# Now you can import Django models
from common.models import Brokers, Prices, Transactions, FX, Assets
from users.models import CustomUser
from datetime import date, datetime, timedelta
from django.db.models import F, Sum
```
"""

import os

import django
from django import conf


def setup_django():
    """
    Safe setup for Django in notebooks that doesn't cause
    'populate() isn't reentrant' errors.
    """
    # Set environment variables
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    # A safer way to initialize Django only once
    if not hasattr(conf, "settings") or not conf.settings.configured:
        django.setup()
        print("Django initialized successfully!")
    else:
        print("Django was already initialized!")

    # Return True for confirmation
    return True


# If run directly, initialize Django
if __name__ == "__main__":
    setup_django()
