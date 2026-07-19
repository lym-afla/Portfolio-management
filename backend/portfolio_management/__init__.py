"""Portfolio management package.

Performs two startup fixups that must run before downstream code imports
its dependencies:

1. Deregister peewee's broken SQLite date converters.
   yfinance depends on peewee, which registers custom SQLite date/time
   converters on import. These converters are broken on Python 3.12+ when
   date values contain timezone suffixes (e.g. ``2024-04-15 00:00:00+00:00``),
   causing:

       ValueError: invalid literal for int() with base 10: b'15 00:00:00+00:00'

   Django registers its own converters when ``USE_TZ=False`` (naive
   datetimes). We deregister peewee's conflicting converters so Django's
   handlers take over. This must run before Django's database layer
   initializes.

2. Trust the Russian Trusted Root CA for the Tinkoff (T-Bank) gRPC API.
   Since 2024 T-Bank serves its public API at ``invest-public-api.tbank.ru``
   with a certificate chain rooted in the Russian Ministry of Digital
   Development's CA ("Russian Trusted Root CA"), which is not present in the
   default trust stores of Windows, Python, or gRPC's BoringSSL. Without
   intervention every API import fails with
   ``CERTIFICATE_VERIFY_FAILED: self signed certificate in certificate chain``.

   The ``t_tech.invest`` SDK ships the authoritative root CA as an embedded
   resource and loads it into the gRPC channel only when the
   ``SSL_TBANK_VERIFY=true`` environment variable is set (see
   ``t_tech.invest.channels.create_channel``). We set that variable here, at
   the earliest point of Django startup and before any module can construct
   a gRPC channel, so the Tinkoff adapter in ``services.broker_api`` is
   trusted by default. Explicit ``0``/``false`` values are respected so the
   behavior can still be overridden for testing or air-gapped environments.
"""

import os
import sqlite3


def _deregister_peewee_sqlite_converters():
    """Remove peewee's date/time converters from SQLite's global registry."""
    for name in ("date", "timestamp", "datetime"):
        sqlite3.register_converter(name, lambda b: b.decode("utf-8"))


def _enable_tinkoff_ssl_trust():
    """Opt into the t_tech SDK's bundled Russian Trusted Root CA.

    Uses ``setdefault`` so an explicit value from the real environment (or
    ``-D`` flags, ``os.environ[...] = ...`` in tests, a future ``.env``
    loader) always wins. Only defaults to enabled when unset.
    """
    os.environ.setdefault("SSL_TBANK_VERIFY", "true")


_deregister_peewee_sqlite_converters()
_enable_tinkoff_ssl_trust()
