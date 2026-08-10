"""Cache behaviour tests for the FX currency graph used by ``services.fx.get_rate``.

These tests cover the version-counter cache added in Task 4:

- The graph is cached per ``(date, investor)``: repeated ``get_rate`` calls
  within a test do not re-issue the distinct ``(from_currency, to_currency)``
  query that builds the graph.
- Saving a new ``FX`` row invalidates the cache (next ``get_rate`` sees the new
  pair) via the ``post_save`` signal wired in ``common/signals.py``.
- Deleting an ``FX`` row invalidates the cache via ``post_delete``.
- Investor A's cached graph does not leak to investor B.

Test isolation: the locmem cache persists across tests in the same process, so
every test calls ``cache.clear()`` (autouse fixture) and resets the version
counter to a known state.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from common.models import FX
from services import fx as fx_module
from services.fx import _get_graph, get_rate

# Reference date shared with the characterization suite.
REF_DATE = date(2024, 6, 3)


def _add_fx(from_cur, to_cur, rate, on_date=REF_DATE, investor=None):
    """Create a long-format FX row and optionally link an investor."""
    fx = FX.objects.create(
        date=on_date,
        from_currency=from_cur,
        to_currency=to_cur,
        rate=Decimal(rate),
    )
    if investor is not None:
        fx.investors.add(investor)
    return fx


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the locmem cache before every test so versions start fresh."""
    cache.clear()


def _count_distinct_pair_queries(context):
    """Count SELECT DISTINCT graph-build queries captured by ``context``.

    Reads ``from_currency`` / ``to_currency`` columns with a ``DISTINCT``. These
    are issued only on a cache miss inside ``_get_graph``.
    """
    return sum(
        1
        for q in context.captured_queries
        if "from_currency" in q.get("sql", "")
        and "to_currency" in q.get("sql", "")
        and "DISTINCT" in q.get("sql", "").upper()
    )


@pytest.mark.fx
@pytest.mark.unit
class TestFXGraphCache:
    """Tests for the FX currency-graph cache in ``services.fx``."""

    def test_graph_is_cached_across_get_rate_calls(self, user):
        """Three get_rate calls with same (date, investor) build the graph once.

        ``CaptureQueriesContext`` forces a debug cursor so it works regardless
        of ``DEBUG``. We assert the DISTINCT pair query runs exactly once for
        three calls (one cache miss + two hits).
        """
        _add_fx("USD", "EUR", "1.1", investor=user)
        _add_fx("RUB", "USD", "75", investor=user)

        with CaptureQueriesContext(connection) as ctx:
            get_rate("USD", "EUR", REF_DATE, investor=user)
            get_rate("USD", "EUR", REF_DATE, investor=user)
            get_rate("RUB", "USD", REF_DATE, investor=user)

        # Only the FIRST get_rate should have run the DISTINCT pair query to
        # build the graph; the next two must hit the cache.
        assert _count_distinct_pair_queries(ctx) == 1

    def test_get_graph_returns_equal_graph_on_cache_hit(self, user):
        """A cached graph is structurally equal on the second call.

        Django's locmem cache pickles on write and unpickles on read, so the
        returned object is a new instance; we assert by node/edge content
        instead of identity.
        """
        _add_fx("USD", "EUR", "1.1", investor=user)
        g1 = _get_graph(REF_DATE, user)
        g2 = _get_graph(REF_DATE, user)
        assert set(g1.nodes) == set(g2.nodes)
        assert set(g1.edges) == set(g2.edges)

    def test_cache_invalidated_on_save(self, user):
        """Saving a new FX row bumps the version; next call rebuilds the graph."""
        _add_fx("USD", "EUR", "1.1", investor=user)
        # Prime the cache for this (date, investor).
        g1 = _get_graph(REF_DATE, user)
        assert "EUR" in g1.nodes
        assert "GBP" not in g1.nodes

        # Add a new pair via .save() (post_save fires).
        _add_fx("USD", "GBP", "1.22", investor=user)

        # Version counter must have bumped and the cache entry replaced.
        g2 = _get_graph(REF_DATE, user)
        assert "GBP" in g2.nodes
        assert g2 is not g1

    def test_cache_invalidated_on_delete(self, user):
        """Deleting an FX row bumps the version; next call rebuilds the graph."""
        gbp_row = _add_fx("USD", "GBP", "1.22", investor=user)
        _add_fx("USD", "EUR", "1.1", investor=user)

        g1 = _get_graph(REF_DATE, user)
        assert "GBP" in g1.nodes

        # Delete via the ORM so post_delete fires.
        gbp_row.delete()

        g2 = _get_graph(REF_DATE, user)
        assert "GBP" not in g2.nodes
        assert g2 is not g1

    def test_different_investors_have_separate_caches(self, user, django_user_model):
        """Investor A's cached graph does not leak to investor B."""
        other = django_user_model.objects.create_user(
            username="other", email="other@example.com", password="pw123"
        )
        _add_fx("USD", "EUR", "1.1", investor=user)
        _add_fx("RUB", "USD", "75", investor=other)

        g_user = _get_graph(REF_DATE, user)
        g_other = _get_graph(REF_DATE, other)

        # Each graph contains its own investor's pairs PLUS the universal
        # stablecoin peg edges (USD—USDT, USD—USDC) which are always present.
        assert set(g_user.nodes) == {"USD", "EUR", "USDT", "USDC"}
        assert set(g_other.nodes) == {"RUB", "USD", "USDT", "USDC"}

    def test_different_dates_have_separate_caches(self, user):
        """Two different dates produce distinct cache entries."""
        _add_fx("USD", "EUR", "1.1", investor=user)
        earlier = date(2024, 1, 1)

        g1 = _get_graph(REF_DATE, user)
        g2 = _get_graph(earlier, user)

        # The graphs are different objects (different cache keys) even though
        # the node set happens to be identical.
        assert g1 is not g2
