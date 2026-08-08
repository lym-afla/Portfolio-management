"""Tests for FXViewSet.list_fx: date-based pagination and null-pair filtering.

The /database/fx grid shows one row per date with one column per currency
pair. ``list_fx`` therefore paginates by **distinct date** (a date's pairs
travel together) and excludes legacy null/empty currency-pair shell rows left
by the wide->long migration.
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from common.models import FX

LIST_FX_URL = "/database/api/fx/list_fx/"


@pytest.mark.integration
@pytest.mark.django_db
class TestFXListFxPagination:
    """list_fx must paginate by date, not by individual pair records."""

    def test_count_is_distinct_dates_not_pair_records(self, authenticated_client, fx_rates):
        """`count` reflects the number of date rows the grid renders.

        fx_rates creates 5 dates x 3 pairs = 15 records. The grid shows 5 date
        rows, so count must be 5 (not 15).
        """
        resp = authenticated_client.post(
            LIST_FX_URL, {"page": 1, "itemsPerPage": 100}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 5, "count should be distinct dates, not pair records"

    def test_one_page_does_not_split_a_dates_pairs(self, authenticated_client, fx_rates):
        """With itemsPerPage=3 (3 date rows), each returned date is complete.

        A date must not appear half-empty on one page and complete on the next.
        Here we ask for 3 date rows and verify all 3 dates carry all 3 pairs.
        """
        resp = authenticated_client.post(
            LIST_FX_URL, {"page": 1, "itemsPerPage": 3}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()["results"]
        dates_on_page = {r["date"] for r in results}
        assert len(dates_on_page) == 3, "page should hold exactly 3 date rows"
        # Every date on the page must have all 3 pairs (no splitting).
        for d in dates_on_page:
            pairs = {(r["from_currency"], r["to_currency"]) for r in results if r["date"] == d}
            assert pairs == {("USD", "EUR"), ("USD", "GBP"), ("CHF", "GBP")}, (
                f"date {d} is missing pairs: {pairs}"
            )

    def test_dates_are_newest_first(self, authenticated_client, fx_rates):
        """Default ordering is newest date first."""
        resp = authenticated_client.post(
            LIST_FX_URL, {"page": 1, "itemsPerPage": 100}, format="json"
        )
        results = resp.json()["results"]
        dates = sorted({r["date"] for r in results}, reverse=True)
        seen = [r["date"] for r in results]
        # First occurrence of each date should be in descending order.
        first_seen = []
        for d in seen:
            if d not in first_seen:
                first_seen.append(d)
        assert first_seen == dates


@pytest.mark.integration
@pytest.mark.django_db
class TestFXListFxNullPairs:
    """list_fx must exclude legacy null/empty currency-pair shell rows."""

    def test_null_pair_rows_excluded_from_results(self, authenticated_client, user):
        """A null-pair shell on a date must not produce a 'null/null' entry."""
        d = date(2024, 2, 1)
        # Real pair row.
        FX.objects.create(date=d, from_currency="USD", to_currency="EUR", rate=Decimal("0.9")).investors.add(user)
        # Legacy shell row (the kind left by the wide->long migration).
        FX.objects.create(date=d, from_currency=None, to_currency=None, rate=None).investors.add(user)

        resp = authenticated_client.post(
            LIST_FX_URL, {"page": 1, "itemsPerPage": 100}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()["results"]
        # Only the real pair row should be present.
        assert len(results) == 1
        assert results[0]["from_currency"] == "USD"
        assert results[0]["to_currency"] == "EUR"
        # No row should carry a null/None pair.
        for r in results:
            assert r["from_currency"] is not None
            assert r["to_currency"] is not None

    def test_date_with_only_null_shell_is_not_counted(self, authenticated_client, user):
        """A date whose only record is a null shell must not appear at all."""
        # Date A: a real pair (should appear).
        FX.objects.create(date=date(2024, 1, 1), from_currency="USD", to_currency="EUR", rate=Decimal("0.9")).investors.add(user)
        # Date B: ONLY a null shell (must be excluded entirely).
        FX.objects.create(date=date(2024, 1, 2), from_currency=None, to_currency=None, rate=None).investors.add(user)

        resp = authenticated_client.post(
            LIST_FX_URL, {"page": 1, "itemsPerPage": 100}, format="json"
        )
        data = resp.json()
        assert resp.status_code == status.HTTP_200_OK
        # Only date A counts.
        assert data["count"] == 1
        dates = {r["date"] for r in data["results"]}
        assert dates == {"2024-01-01"}
