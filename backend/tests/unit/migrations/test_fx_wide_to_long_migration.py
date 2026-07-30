"""Tests for the FX wide-to-long data migration (0091).

The migration copies each non-null named-pair column on an existing FX row into
a long-format row (from_currency / to_currency / rate) on the same date, and
copies the investors M2M linkage from the source row.

We test the migration's forward function directly. The forward function is only
exercisable while the FX model still has BOTH the old named columns and the new
long-format fields (i.e. between migration 0090 and 0092). Once Task 3 /
migration 0092 drops the named columns, the source rows cannot be created via
the ORM any more, so the forward-migration tests skip themselves; only the
"no-op on empty table" test continues to run.
"""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from common.models import FX


def _load_migration_module():
    """Import the 0091 migration module by file path.

    The module name starts with digits, so a normal ``import`` statement is
    not valid Python; load it via importlib using the file location.
    """
    migration_path = (
        Path(FX._meta.app_config.path)
        / "migrations"
        / "0091_fx_migrate_wide_to_long.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fx_migration_0091", migration_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
WIDE_COLUMNS = _MIGRATION.WIDE_COLUMNS
migrate_wide_to_long = _MIGRATION.migrate_wide_to_long


def _wide_columns_present():
    """Return True if the live FX model still has the wide named-pair columns.

    Forward-migration tests can only build old-style source rows while these
    columns exist on the live model (i.e. between migrations 0090 and 0092).
    """
    field_names = {f.name for f in FX._meta.get_fields()}
    return all(col in field_names for col, _, _ in WIDE_COLUMNS)


# Skip reason used by every forward-migration test that builds a wide source row.
_WIDE_ABSENT_REASON = (
    "Wide named-pair columns were dropped in migration 0092 (Task 3); the "
    "0091 forward migration is historical and cannot be exercised against "
    "the live model any more."
)
skip_if_wide_columns_dropped = pytest.mark.skipif(
    not _wide_columns_present(), reason=_WIDE_ABSENT_REASON
)

# A second investor used to exercise multi-investor M2M copy.
SECOND_USERNAME = "migration_test_other"


def _apps_shim():
    """Return an object whose ``get_model`` resolves against the live registry.

    The migration function calls ``apps.get_model("common", "FX")``. During a
    real migration ``apps`` is a historical AppState registry; in this test the
    current model already has both old and new fields, so the live registry is
    the right thing to use.
    """

    from django.apps import apps as django_apps

    class _Apps:
        def get_model(self, app_label, model_name):
            return django_apps.get_model(app_label, model_name)

    return _Apps()


@pytest.mark.django_db
@skip_if_wide_columns_dropped
def test_migration_creates_long_rows_for_each_non_null_wide_column(user):
    """Each non-null named-pair column becomes a long-format row with correct from/to/rate."""
    src_date = date(2024, 6, 3)
    src = FX.objects.create(
        date=src_date,
        USDEUR=Decimal("1.090000"),
        USDGBP=Decimal("0.790000"),
        CHFGBP=Decimal("0.880000"),
        RUBUSD=Decimal("0.0110"),
        PLNUSD=Decimal("0.25000"),
        CNYUSD=Decimal("0.1400"),
    )
    src.investors.add(user)

    migrate_wide_to_long(_apps_shim(), schema_editor=None)

    # One long-format row per non-null wide column.
    long_rows = FX.objects.exclude(from_currency__isnull=True).exclude(
        from_currency=""
    )
    assert long_rows.count() == len(WIDE_COLUMNS)

    by_pair = {(r.from_currency, r.to_currency): r for r in long_rows}
    assert by_pair[("USD", "EUR")].rate == Decimal("1.090000")
    assert by_pair[("USD", "GBP")].rate == Decimal("0.790000")
    assert by_pair[("CHF", "GBP")].rate == Decimal("0.880000")
    assert by_pair[("RUB", "USD")].rate == Decimal("0.0110")
    assert by_pair[("PLN", "USD")].rate == Decimal("0.25000")
    assert by_pair[("CNY", "USD")].rate == Decimal("0.1400")

    # Every long-format row sits on the source date.
    for row in long_rows:
        assert row.date == src_date

    # The investor M2M is copied to every new row.
    for row in long_rows:
        assert user in row.investors.all()


@pytest.mark.django_db
@skip_if_wide_columns_dropped
def test_migration_skips_null_columns(user):
    """Null named-pair columns do not produce long-format rows."""
    src = FX.objects.create(
        date=date(2024, 7, 1),
        USDEUR=Decimal("1.090000"),
        # USDGBP left NULL
        # CHFGBP left NULL
        RUBUSD=Decimal("0.0110"),
        # PLNUSD left NULL
        # CNYUSD left NULL
    )
    src.investors.add(user)

    migrate_wide_to_long(_apps_shim(), schema_editor=None)

    long_rows = list(
        FX.objects.exclude(from_currency__isnull=True).exclude(from_currency="")
    )
    pairs = {(r.from_currency, r.to_currency) for r in long_rows}
    assert pairs == {("USD", "EUR"), ("RUB", "USD")}


@pytest.mark.django_db
@skip_if_wide_columns_dropped
def test_migration_copies_multiple_investors(user, django_user_model):
    """All investors linked to the source row are copied to each new row."""
    other = django_user_model.objects.create_user(
        username=SECOND_USERNAME,
        email="other@example.com",
        password="otherpass123",
    )
    src = FX.objects.create(
        date=date(2024, 8, 15),
        USDEUR=Decimal("1.090000"),
    )
    src.investors.add(user, other)

    migrate_wide_to_long(_apps_shim(), schema_editor=None)

    long_rows = list(
        FX.objects.exclude(from_currency__isnull=True).exclude(from_currency="")
    )
    assert len(long_rows) == 1
    row = long_rows[0]
    investor_set = set(row.investors.values_list("id", flat=True))
    assert investor_set == {user.id, other.id}


@pytest.mark.django_db
@skip_if_wide_columns_dropped
def test_migration_is_idempotent(user):
    """Re-running the migration does not duplicate long-format rows."""
    src = FX.objects.create(
        date=date(2024, 9, 20),
        USDEUR=Decimal("1.090000"),
    )
    src.investors.add(user)

    apps = _apps_shim()
    migrate_wide_to_long(apps, schema_editor=None)
    migrate_wide_to_long(apps, schema_editor=None)

    long_rows = list(
        FX.objects.exclude(from_currency__isnull=True).exclude(from_currency="")
    )
    assert len(long_rows) == 1
    # get_or_create uses add() for M2M which is itself idempotent, so the
    # investor linkage should not duplicate either.
    assert list(long_rows[0].investors.values_list("id", flat=True)) == [user.id]


@pytest.mark.django_db
def test_migration_noop_on_empty_table():
    """The migration is a no-op when there are no wide-column FX rows.

    Note: migration 0093 (stablecoin peg) seeds 2 global FX rows on a fresh
    DB, so the table is not truly empty — but the wide→long migration only
    copies from named-pair columns (which no longer exist), so it's a no-op.
    """
    count_before = FX.objects.count()
    migrate_wide_to_long(_apps_shim(), schema_editor=None)
    assert FX.objects.count() == count_before
