"""Portfolio management package.

Deregister peewee's broken SQLite date converters.

yfinance depends on peewee, which registers custom SQLite date/time converters
on import. These converters are broken on Python 3.12+ when date values contain
timezone suffixes (e.g. ``2024-04-15 00:00:00+00:00``), causing:

    ValueError: invalid literal for int() with base 10: b'15 00:00:00+00:00'

Django registers its own converters when ``USE_TZ=False`` (naive datetimes).
We deregister peewee's conflicting converters so Django's handlers take over.
This must run before Django's database layer initializes.
"""

import sqlite3


def _deregister_peewee_sqlite_converters():
    """Remove peewee's date/time converters from SQLite's global registry."""
    for name in ("date", "timestamp", "datetime"):
        sqlite3.register_converter(name, lambda b: b.decode("utf-8"))


_deregister_peewee_sqlite_converters()
