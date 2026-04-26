"""Test-specific Django settings for faster test execution.

Overrides main settings with performance optimizations:
- MD5 password hasher (100x faster than PBKDF2)
- Minimal logging (no structlog overhead)
- No debug_toolbar
- Consistent SECRET_KEY for deterministic encryption
"""

from portfolio_management.settings import *  # noqa: F401,F403

# Use fast password hasher for tests (PBKDF2 is intentionally slow)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Consistent secret key for deterministic test results
SECRET_KEY = "test-secret-key-for-consistent-encryption"

DEBUG = False

# Remove debug_toolbar middleware (keep app to avoid import errors in urls.py)
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa: F405

# Minimal logging for tests — reduce structlog overhead
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "WARNING",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# Consistent encryption key for tests
SERVER_ENCRYPTION_KEY = b"dGVzdC1rZXktZm9yLXRlc3RzLWFsd2F5cy1zYW1l"
