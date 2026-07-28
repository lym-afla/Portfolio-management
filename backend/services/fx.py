"""FX rate service.

Owns the FX business logic that previously lived on the ``FX`` model and at
module level in ``common.models``:

- :func:`get_rate` builds a networkx graph of currency pairs from the ``FX``
  model fields, runs bellman-ford shortest path, walks the path querying
  ``FX.objects`` for rates, and inverts via ``1 / fx_rate``.
- :func:`update_fx_rate` gets/creates an ``FX`` row and fetches each missing
  rate from CBR (RUB pairs) or Yahoo.
- :func:`get_investor_fx_entries` returns ``FX.objects.filter(investors=...)``.
- The Yahoo/CBR fetchers and ``CBRRateLimitError``.

Numeric safety: ``Decimal`` everywhere for FX rates. Never ``float``.
"""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, DecimalException

import networkx as nx
import requests
import yfinance as yf
from django.core.cache import cache
from django.db import models
from django.db.models import F, Q

# ``services.fx`` is imported lazily (only when callers need an FX rate), so by
# the time this runs ``common.models`` is fully loaded and ``FX`` is importable
# without triggering a circular-import crash.
from common.models import FX

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Currency graph cache
# ---------------------------------------------------------------------------
#
# ``get_rate`` builds a ``networkx.Graph`` of currency pairs from the ``FX``
# table on every call. With ~35 call sites across the calc layer, a single page
# load may call ``get_rate`` dozens of times, each rebuilding the graph from a
# fresh DB query. This cache stores the built graph keyed by ``(date, investor)`'
# so the DB query + graph construction happen at most once per page load.
#
# Invalidation: a version counter. The cache key embeds the current version
# (``fx_graph:v<version>:<date>:<investor>``); ``_invalidate_fx_graph_cache``
# just increments the version, which makes every existing key unreachable (so
# they age out via the TTL rather than being enumerated and deleted). The
# version-counter approach is portable across cache backends — locmem doesn't
# support pattern deletion and Redis ``scan``-based delete is not available
# through Django's cache API. The counter is wired to ``FX`` ``post_save`` /
# ``post_delete`` signals (see ``common/signals.py``).
#
# Trade-off (FXManager.bulk_create): the manager override in ``common.models``
# saves rows one-by-one for batches <= 50 (firing ``post_save`` per row and so
# invalidating the cache), but falls back to native ``bulk_create`` for larger
# batches which emits no signals and leaves the cache stale until the next
# save/delete of a single row or until the 1h TTL expires. Large bulk loads are
# a rare ops path; if they become hot, call ``_invalidate_fx_graph_cache()``
# explicitly after the load.

_GRAPH_CACHE_PREFIX = "fx_graph"
_GRAPH_CACHE_TIMEOUT = 3600  # 1 hour


def _graph_cache_key(date_as_of, investor):
    """Cache key for the currency graph for ``(date_as_of, investor)``.

    Embeds the current invalidation version so incrementing the version makes
    every previously-written key unreachable.
    """
    version = cache.get(f"{_GRAPH_CACHE_PREFIX}:version") or 0
    investor_id = investor.id if investor is not None else "all"
    return f"{_GRAPH_CACHE_PREFIX}:v{version}:{date_as_of.isoformat()}:{investor_id}"


def _get_graph(date_as_of, investor):
    """Build (or fetch from cache) the FX currency graph for a date + investor.

    The graph is undirected, built from distinct (from_currency, to_currency)
    pairs that exist for the investor (or for anyone when ``investor`` is
    ``None``). Cached per ``(date, investor)`` so repeated ``get_rate`` calls
    within a page load don't re-query the DB.
    """
    key = _graph_cache_key(date_as_of, investor)
    G = cache.get(key)
    if G is not None:
        return G
    G = nx.Graph()
    qs = FX.objects.values("from_currency", "to_currency").distinct()
    if investor is not None:
        qs = qs.filter(investors=investor)
    for row in qs:
        src, dst = row["from_currency"], row["to_currency"]
        if not src or not dst:
            continue
        G.add_edge(src, dst)
    cache.set(key, G, _GRAPH_CACHE_TIMEOUT)
    return G


def _invalidate_fx_graph_cache(sender=None, instance=None, **kwargs):
    """Invalidate every FX currency graph cache entry.

    Connected to ``FX.post_save`` / ``post_delete`` (see ``common/signals.py``).
    Increments the version counter embedded in cache keys, which makes all
    existing graph entries unreachable; they then age out via the TTL.
    """
    version = (cache.get(f"{_GRAPH_CACHE_PREFIX}:version") or 0) + 1
    cache.set(f"{_GRAPH_CACHE_PREFIX}:version", version)


# ---------------------------------------------------------------------------
# get_rate
# ---------------------------------------------------------------------------


def get_rate(source, target, date_as_of, investor=None):
    """Get FX rate for a given currency and target currency at a given date.

    The output is a dictionary with the following keys:
    - FX: the FX rate to multiply to get target currency from source
    - conversions: number of conversions needed from source to target
    - dates_async: whether the dates are asynchronous
    - dates: the dates used to get the FX rate

    Storage convention (quote-per-base): a long-format row
    ``from_currency=X, to_currency=Y, rate=r`` stores "r units of X per 1 unit of
    Y" (r X/Y). To turn that into the "multiply source -> target" multiplier we
    walk the shortest path hop by hop and, for each hop, divide when the stored
    row is oriented the same way as the hop (``from_currency == hop_source``) and
    multiply when it is oriented the opposite way.

    Args:
        source: Source currency code (e.g., 'USD')
        target: Target currency code (e.g., 'EUR')
        date_as_of: Date for which to get the FX rate
        investor: Optional investor filter for FX rates

    Returns:
        dict: Dictionary with FX rate information

    Raises:
        ValueError: If currencies are invalid or no FX rate data is found
    """
    # Validate input currencies and convert to uppercase
    if not source or not isinstance(source, str) or not source.strip():
        raise ValueError("No FX rate found")

    if not target or not isinstance(target, str) or not target.strip():
        raise ValueError("No FX rate found")

    # Convert date to date object if it's a datetime
    if isinstance(date_as_of, datetime):
        date_as_of = date_as_of.date()
    elif isinstance(date_as_of, date):
        pass
    else:
        raise ValueError("Invalid date")

    # Convert to uppercase and strip whitespace
    source = source.upper().strip()
    target = target.upper().strip()

    # Same currency conversion
    if source == target:
        return {
            "FX": Decimal("1"),
            "conversions": 0,
            "dates_async": False,
            "dates": [],
        }

    try:
        investor_filter = {"investors": investor} if investor is not None else {}

        # Check if we have any data for the given investor
        if investor is not None:
            if not FX.objects.filter(investors=investor).exists():
                raise ValueError("No FX rate found")

        # Check date range - don't allow dates too far from available data
        earliest_date = FX.objects.filter(**investor_filter).aggregate(
            min_date=models.Min("date")
        )["min_date"]
        latest_date = FX.objects.filter(**investor_filter).aggregate(
            max_date=models.Max("date")
        )["max_date"]

        if earliest_date is None or latest_date is None:
            raise ValueError("No FX rate found")

        # Don't allow dates more than 5 years before or 1 year after available data
        if date_as_of < earliest_date - timedelta(days=5 * 365):
            raise ValueError("No FX rate found")
        if date_as_of > latest_date + timedelta(days=365):
            raise ValueError("No FX rate found")

        # Build undirected graph of currencies from the long-format rows that
        # exist for this investor (or for anyone when no investor is given).
        # Cached per (date, investor); invalidated via FX post_save/post_delete.
        G = _get_graph(date_as_of, investor)

        if source not in G.nodes:
            raise ValueError("No FX rate found")
        if target not in G.nodes:
            raise ValueError("No FX rate found")

        try:
            path = nx.shortest_path(G, source, target, method="bellman-ford")
        except nx.NetworkXNoPath:
            raise ValueError("No FX rate found")

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error setting up FX rate calculation: {e}")
        raise ValueError("No FX rate found")

    fx_rate = Decimal("1")
    dates_async = False
    dates_list = []

    # Walk the path hop-by-hop, multiplying or dividing based on row orientation.
    for i in range(1, len(path)):
        hop_source = path[i - 1]
        hop_target = path[i]

        base_qs = FX.objects.filter(
            Q(from_currency=hop_source, to_currency=hop_target)
            | Q(from_currency=hop_target, to_currency=hop_source),
            rate__isnull=False,
            **investor_filter,
        )

        # Try the most recent rate on or before the requested date first.
        row = base_qs.filter(date__lte=date_as_of).order_by("-date").first()

        # Fall back to the closest future rate if there is no past rate.
        if row is None:
            row = base_qs.filter(date__gte=date_as_of).order_by("date").first()

        if row is None:
            raise ValueError("No FX rate found")

        # Quote-per-base: rate = "from_currency per 1 to_currency".
        # If the row is oriented the same way as the hop we DIVIDE (we need the
        # reciprocal "target per source"); if it is reversed we MULTIPLY.
        try:
            if row.from_currency == hop_source:
                fx_rate /= row.rate
            else:
                fx_rate *= row.rate
        except (ZeroDivisionError, DecimalException):
            # A zero stored rate makes the conversion undefined.
            raise ValueError("No FX rate found")

        dates_async = (dates_list and dates_list[0] != row.date) or dates_async
        dates_list.append(row.date)

    # Round to 6 dp to match the precision the previous wide-column
    # implementation produced via ``round(Decimal(1/fx_rate), 6)``.
    try:
        fx_rate = fx_rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except DecimalException:
        raise ValueError("No FX rate found")

    return {
        "FX": fx_rate,
        "conversions": len(path) - 1,
        "dates_async": dates_async,
        "dates": dates_list,
    }


# ---------------------------------------------------------------------------
# update_fx_rate
# ---------------------------------------------------------------------------


# Currency pairs to populate when ``update_fx_rate`` runs. The first element of
# each pair is the ``from_currency`` (quote), the second is the ``to_currency``
# (base), matching the quote-per-base storage convention. This is the long-format
# equivalent of the old named columns USDEUR, USDGBP, CHFGBP, RUBUSD, PLNUSD,
# CNYUSD.
FX_PAIRS = (
    ("USD", "EUR"),
    ("USD", "GBP"),
    ("CHF", "GBP"),
    ("RUB", "USD"),
    ("PLN", "USD"),
    ("CNY", "USD"),
)


def update_fx_rate(date, investor):
    """Update FX rate for a given date and investor.

    For each currency pair in :data:`FX_PAIRS` that does not already have a
    long-format row on ``date`` linked to ``investor``, fetch the rate (CBR for
    RUB pairs, Yahoo otherwise) and create the row.
    """
    for source, target in FX_PAIRS:
        # Skip pairs we already have a rate for on this date for this investor.
        already = FX.objects.filter(
            date=date,
            from_currency=source,
            to_currency=target,
            investors=investor,
            rate__isnull=False,
        ).exists()
        if already:
            continue

        use_cbr = "RUB" in (source, target)
        fetcher = update_FX_from_CBR if use_cbr else update_FX_from_Yahoo
        source_name = "CBR" if use_cbr else "Yahoo Finance"
        try:
            rate_data = fetcher(source, target, date)
        except CBRRateLimitError as exc:
            logger.error(
                "%s%s for %s NOT updated: CBR is rate-limiting us (%s). "
                "The stored value was left untouched - please retry later.",
                source,
                target,
                date,
                exc,
            )
            continue
        except Exception:
            logger.warning(
                "%s%s for %s was NOT updated (%s source failed)",
                source,
                target,
                date,
                source_name,
            )
            continue

        if rate_data is None:
            continue

        row, _ = FX.objects.get_or_create(
            date=date,
            from_currency=source,
            to_currency=target,
            defaults={"rate": rate_data["exchange_rate"]},
        )
        row.rate = rate_data["exchange_rate"]
        row.save()
        row.investors.add(investor)


# ---------------------------------------------------------------------------
# get_investor_fx_entries
# ---------------------------------------------------------------------------


def get_investor_fx_entries(investor):
    """Get FX entries for a given investor."""
    return FX.objects.filter(investors=investor)


# ---------------------------------------------------------------------------
# Yahoo Finance fetcher
# ---------------------------------------------------------------------------


def is_yahoo_finance_available():
    """
    Check yahoo finance availability.

    Check if Yahoo Finance is available by making a test request with proper headers.

    Returns:
        True if Yahoo Finance is available, False otherwise.
    """
    url = "https://finance.yahoo.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # noqa: E501
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",  # noqa: E501
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return True
    except (requests.ConnectionError, requests.Timeout):
        pass
    return False


def update_FX_from_Yahoo(base_currency, target_currency, date, max_attempts=5):
    """
    Fetch FX rate from Yahoo Finance.

    Note: Modern yfinance uses curl_cffi internally
    to handle headers and browser mimicking.
    We let yfinance handle the session to avoid conflicts.

    Args:
        base_currency: Base currency code (e.g., 'USD')
        target_currency: Target currency code (e.g., 'EUR')
        date: Date for which to fetch the rate
        max_attempts: Number of attempts to try fetching data

    Returns:
        dict with exchange_rate, actual_date, requested_date or None if failed
    """
    if not is_yahoo_finance_available():
        raise ConnectionError("Yahoo Finance is not available")

    # Define the currency pair (Yahoo Finance format: XXXYYY=X)
    currency_pair = f"{target_currency}{base_currency}=X"

    # Initialize a counter for the number of attempts
    attempt = 0

    while attempt < max_attempts:
        # Define the date for which you want the exchange rate
        end_date = date - timedelta(days=attempt - 1)  # Go back in time for each attempt.
        # Need to deduct 1 to get rate for exactly the date
        start_date = end_date - timedelta(days=1)  # Go back one day to ensure the date is covered

        # Fetch historical data for the currency pair within the date range
        try:
            # Let yfinance handle the session internally (uses curl_cffi for better browser mimicking) # noqa: E501
            ticker = yf.Ticker(currency_pair)
            # Note: Only set start and end, not period
            # (yfinance allows max 2 of period/start/end)
            exchange_rate_data = ticker.history(
                start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d")
            )

            # Add small delay to avoid rate limiting
            import time

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error fetching exchange rate data for {currency_pair}: {e}")
            attempt += 1
            continue

        if not exchange_rate_data.empty and not exchange_rate_data["Close"].isnull().all():
            # Get the exchange rate for the specified date
            exchange_rate = round(exchange_rate_data["Close"].iloc[0], 6)
            actual_date = exchange_rate_data.index[0].date()  # Extract the actual date

            logger.info(
                f"Successfully fetched {currency_pair} rate for {actual_date}: " f"{exchange_rate}"
            )

            return {
                "exchange_rate": exchange_rate,
                "actual_date": actual_date,
                "requested_date": date,
            }

        # Increment the attempt counter
        attempt += 1
        logger.warning(f"Attempt {attempt}/{max_attempts} failed for {currency_pair} on {date}")

    # If no data is found after max_attempts,
    # return None or an appropriate error message
    logger.error(f"Failed to fetch {currency_pair} after {max_attempts} attempts for date {date}")
    return None


# ---------------------------------------------------------------------------
# Central Bank of Russia fetcher + constants
# ---------------------------------------------------------------------------

# Central Bank of Russia official daily rates SOAP endpoint.
CBR_SOAP_URL = "http://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
CBR_SOAP_TIMEOUT = 30
CBR_SOAP_HEADERS = {
    "Content-Type": "application/soap+xml; charset=utf-8",
    "SOAPAction": "http://web.cbr.ru/GetCursOnDate",
}
CBR_XML_NAMESPACES = {"diffgr": "urn:schemas-microsoft-com:xml-diffgram-v1"}
# Rate-limit handling: exponential backoff per query_date (does not consume walk-back attempts).
# Default of 3 retries keeps worst-case interactive block to 2+4+8 = 14s.
# Bulk jobs (e.g. backfill) pass a larger value via the ``rate_limit_retries`` arg.
CBR_RATE_LIMIT_RETRIES = 3
CBR_RATE_LIMIT_BASE_SLEEP = 2.0


class CBRRateLimitError(Exception):
    """Raised when CBR returns HTTP 429 and rate-limit retries are exhausted."""


def update_FX_from_CBR(
    base_currency, target_currency, for_date, max_attempts=5, rate_limit_retries=None
):
    """Fetch FX rate from the Central Bank of Russia daily rates SOAP API.

    Used for any pair that includes RUB. CBR's ``GetCursOnDate`` returns, for each
    foreign currency, ``Vcurs / Vnom`` in rubles per ``Vnom`` units of that
    currency. For a pair named ``{source}{target}`` we store the rate in the same
    "RUB per foreign currency" semantic already used by the Yahoo Finance path
    (e.g. ``RUBUSD`` stores ~90 RUB / USD).

    Args:
        base_currency: Source currency code (e.g. 'RUB').
        target_currency: Target currency code (e.g. 'USD').
        for_date: Date for which to fetch the rate.
        max_attempts: Maximum number of dates to walk back when CBR has no
            rate for the requested date (weekends, Russian holidays).

    Returns:
        dict with ``exchange_rate`` (Decimal, 6 dp), ``actual_date`` (the
        CBR-published date used), and ``requested_date``; or ``None`` if no
        rate can be obtained after ``max_attempts``.
    """
    if for_date is None:
        logger.error("update_FX_from_CBR called with for_date=None")
        return None

    base = (base_currency or "").upper().strip()
    target = (target_currency or "").upper().strip()
    # CBR only has foreign-currency-vs-RUB quotes; pick the non-RUB side.
    foreign = target if base == "RUB" else base
    if foreign == "RUB" or not foreign:
        logger.error(
            "update_FX_from_CBR called with unsupported pair base=%s target=%s",
            base_currency,
            target_currency,
        )
        return None

    for attempt in range(max_attempts):
        query_date = for_date - timedelta(days=attempt)
        soap_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap12:Envelope '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            "<soap12:Body>"
            '<GetCursOnDate xmlns="http://web.cbr.ru/">'
            f"<On_date>{query_date.strftime('%Y-%m-%d')}</On_date>"
            "</GetCursOnDate>"
            "</soap12:Body>"
            "</soap12:Envelope>"
        )

        response = None
        retries = (
            rate_limit_retries if rate_limit_retries is not None else CBR_RATE_LIMIT_RETRIES
        )
        for rl_retry in range(retries):
            try:
                response = requests.post(
                    CBR_SOAP_URL,
                    data=soap_body,
                    headers=CBR_SOAP_HEADERS,
                    timeout=CBR_SOAP_TIMEOUT,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "CBR request failed for %s on %s (attempt %d/%d): %s",
                    foreign,
                    query_date,
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                response = None
                break

            if response.status_code != 429:
                break

            sleep_for = CBR_RATE_LIMIT_BASE_SLEEP * (2 ** rl_retry)
            logger.warning(
                "CBR rate-limited (HTTP 429) for %s on %s; sleeping %.1fs "
                "(rate-limit retry %d/%d)",
                foreign,
                query_date,
                sleep_for,
                rl_retry + 1,
                retries,
            )
            time.sleep(sleep_for)
        else:
            raise CBRRateLimitError(
                f"CBR rate limit persists for {foreign} on {query_date} "
                f"after {retries} retries"
            )

        if response is None:
            continue

        if response.status_code == 429:
            # Safety net: shouldn't reach here because the for/else raises.
            raise CBRRateLimitError(
                f"CBR rate limit for {foreign} on {query_date}"
            )

        if response.status_code != 200:
            logger.warning(
                "CBR returned HTTP %d for %s on %s (attempt %d/%d)",
                response.status_code,
                foreign,
                query_date,
                attempt + 1,
                max_attempts,
            )
            continue

        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            logger.warning(
                "CBR XML parse error for %s on %s (attempt %d/%d): %s",
                foreign,
                query_date,
                attempt + 1,
                max_attempts,
                exc,
            )
            continue

        rate = _extract_cbr_rate(root, foreign, query_date)
        if rate is not None:
            logger.info(
                "CBR %s rate for %s (requested %s): %s",
                foreign,
                query_date,
                for_date,
                rate,
            )
            return {
                "exchange_rate": rate,
                "actual_date": query_date,
                "requested_date": for_date,
            }

        logger.info(
            "CBR has no %s rate for %s, backing off (attempt %d/%d)",
            foreign,
            query_date,
            attempt + 1,
            max_attempts,
        )

    logger.error(
        "Failed to fetch CBR %s rate for %s after %d attempts",
        foreign,
        for_date,
        max_attempts,
    )
    return None


def _extract_cbr_rate(root, currency_code, query_date):
    """Parse a CBR GetCursOnDate response and return ``Vcurs / Vnom`` as Decimal.

    Returns ``None`` when the requested ``currency_code`` is absent from the
    payload or any numeric field fails to parse.
    """
    path = ".//diffgr:diffgram/ValuteData/ValuteCursOnDate"
    for valute in root.findall(path, CBR_XML_NAMESPACES):
        code_node = valute.find("VchCode")
        if code_node is None or not code_node.text:
            continue
        if code_node.text.strip().upper() != currency_code:
            continue
        vcurs_node = valute.find("Vcurs")
        vnom_node = valute.find("Vnom")
        if vcurs_node is None or not vcurs_node.text:
            return None
        try:
            vcurs = Decimal(vcurs_node.text.strip().replace(",", "."))
            if vnom_node is not None and vnom_node.text:
                vnom = Decimal(vnom_node.text.strip().replace(",", "."))
            else:
                vnom = Decimal("1")
            if vnom == 0:
                logger.warning(
                    "CBR returned Vnom=0 for %s on %s", currency_code, query_date
                )
                return None
            return (vcurs / vnom).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        except DecimalException as exc:
            logger.warning(
                "CBR rate parse error for %s on %s: %s",
                currency_code,
                query_date,
                exc,
            )
            return None
    return None
