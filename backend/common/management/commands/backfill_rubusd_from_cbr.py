"""Refetch ``FX.RUBUSD`` from the Central Bank of Russia and overwrite every row.

Yahoo Finance's RUB feed has been unreliable since 2022. This command walks the
full ``FX`` table and replaces each ``RUBUSD`` value with the official CBR rate
for the same date, so historical NAVs become consistent with the new source.

Usage:
    python manage.py backfill_rubusd_from_cbr [--dry-run] [--from YYYY-MM-DD]
        [--to YYYY-MM-DD] [--sleep SECONDS]

Exit code is 1 if any date failed to fetch (so the run can be re-driven from CI
or inspected manually).
"""

import logging
import time
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from common.models import FX, CBRRateLimitError, update_FX_from_CBR

logger = logging.getLogger(__name__)


def _parse_date(value, flag):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CommandError(f"Invalid {flag} date {value!r}: expected YYYY-MM-DD") from exc


class Command(BaseCommand):
    """Overwrite every FX.RUBUSD value with the CBR-published rate for that date."""

    help = "Replace FX.RUBUSD values across the history with CBR-sourced rates"

    def add_arguments(self, parser):
        """Register command-line flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show intended changes without writing to the database.",
        )
        parser.add_argument(
            "--from",
            dest="date_from",
            type=str,
            help="Only process FX rows on or after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            type=str,
            help="Only process FX rows on or before this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.5,
            help=(
                "Seconds to sleep between CBR calls (default: 0.5). "
                "Increase if you hit HTTP 429."
            ),
        )
        parser.add_argument(
            "--max-attempts",
            dest="max_attempts",
            type=int,
            default=10,
            help=(
                "Max CBR walk-back attempts per row (default: 10). "
                "Covers Russian Jan/May holiday runs of up to ~9 consecutive days."
            ),
        )
        parser.add_argument(
            "--keep-on-failure",
            action="store_true",
            help=(
                "If set, leave the existing RUBUSD value intact when CBR fails. "
                "Default is to CLEAR the value to NULL so stale Yahoo data is removed."
            ),
        )

    def handle(self, *args, **options):
        """Iterate FX rows, refetch RUBUSD from CBR, and overwrite when different."""
        dry_run = options["dry_run"]
        sleep_seconds = options["sleep"]
        max_attempts = options["max_attempts"]
        keep_on_failure = options["keep_on_failure"]

        queryset = FX.objects.all().order_by("date")
        if options.get("date_from"):
            queryset = queryset.filter(date__gte=_parse_date(options["date_from"], "--from"))
        if options.get("date_to"):
            queryset = queryset.filter(date__lte=_parse_date(options["date_to"], "--to"))

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No FX rows in the requested range."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN - inspecting {total} row(s)"))
        else:
            self.stdout.write(f"Backfilling RUBUSD from CBR across {total} row(s)")

        updated = 0
        unchanged = 0
        failed = 0
        cleared = 0
        skipped = 0

        for fx_row in queryset.iterator():
            if fx_row.date is None:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f"  pk={fx_row.pk}  date=None - skipped (inspect DB)")
                )
                continue
            try:
                rate_data = update_FX_from_CBR(
                    "RUB",
                    "USD",
                    fx_row.date,
                    max_attempts=max_attempts,
                    rate_limit_retries=6,
                )
            except CBRRateLimitError as exc:
                raise CommandError(
                    f"Aborting: CBR is rate-limiting us on {fx_row.date} ({exc}). "
                    "No data was cleared. Re-run later or widen --sleep."
                ) from exc
            if rate_data is None:
                old_rate = fx_row.RUBUSD
                if keep_on_failure:
                    failed += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  {fx_row.date}  CBR fetch failed - kept {old_rate}"
                        )
                    )
                else:
                    cleared += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {fx_row.date}  CBR fetch failed - clearing (was {old_rate})"
                        )
                    )
                    if not dry_run and old_rate is not None:
                        fx_row.RUBUSD = None
                        fx_row.save(update_fields=["RUBUSD"])
                if sleep_seconds:
                    time.sleep(sleep_seconds)
                continue

            new_rate = Decimal(rate_data["exchange_rate"]).quantize(Decimal("0.0001"))
            old_rate = fx_row.RUBUSD

            if old_rate is not None and Decimal(old_rate).quantize(Decimal("0.0001")) == new_rate:
                unchanged += 1
                self.stdout.write(
                    f"  {fx_row.date}  {old_rate}  ==  {new_rate}  (unchanged)"
                )
            else:
                old_display = old_rate if old_rate is not None else "None"
                self.stdout.write(
                    f"  {fx_row.date}  {old_display}  ->  {new_rate}"
                )
                if not dry_run:
                    fx_row.RUBUSD = new_rate
                    fx_row.save(update_fields=["RUBUSD"])
                updated += 1

            if sleep_seconds:
                time.sleep(sleep_seconds)

        summary = (
            f"Done. updated={updated} unchanged={unchanged} "
            f"cleared={cleared} skipped={skipped} failed={failed} total={total}"
        )
        if failed:
            raise CommandError(summary)
        if cleared or skipped:
            self.stdout.write(self.style.WARNING(summary))
            return
        self.stdout.write(self.style.SUCCESS(summary))
