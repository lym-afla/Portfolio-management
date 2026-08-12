"""Management command: split an OKX broker's single account into Trading + Funding.

Usage:
    uv run python manage.py migrate_okx_two_account "OKX" [--dry-run]

Sub-project 5a / issue #29. Idempotent: renames the broker's existing account
to "OKX Trading" (native_id=trading) and get_or_creates an "OKX Funding"
account (native_id=funding). Touches NO transactions, so historical NAV is
unchanged. Run this so the funding-history CSV can be imported into the
Funding account.
"""
from django.core.management.base import BaseCommand

from common.models import Accounts, Brokers


class Command(BaseCommand):
    help = "Split an OKX broker's single account into Trading + Funding (#29)."

    def add_arguments(self, parser):
        parser.add_argument(
            "broker_name",
            type=str,
            help="Exact name of the OKX broker whose account should be split.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving.",
        )

    def handle(self, *args, **options):
        broker_name = options["broker_name"]
        dry_run = options["dry_run"]

        try:
            broker = Brokers.objects.get(name=broker_name)
        except Brokers.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Broker {broker_name!r} not found."))
            return

        # Already migrated?
        trading = Accounts.objects.filter(broker=broker, native_id="trading").first()
        funding = Accounts.objects.filter(broker=broker, native_id="funding").first()
        if trading and funding:
            self.stdout.write(self.style.WARNING(
                f"{broker_name} already has Trading (id={trading.id}) and Funding "
                f"(id={funding.id}) accounts. Nothing to do."
            ))
            return

        # Pick the legacy account to rename: the first non-funding account.
        legacy = Accounts.objects.filter(broker=broker).exclude(native_id="funding").first()
        if legacy is None:
            self.stdout.write(self.style.ERROR(
                f"{broker_name} has no account to rename into Trading. Create one first."
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN: would rename account {legacy.id} ({legacy.name!r}) -> "
                f"'OKX Trading' (native_id=trading) and create 'OKX Funding' (native_id=funding)."
            ))
            return

        legacy.name = "OKX Trading"
        legacy.native_id = "trading"
        legacy.save(update_fields=["name", "native_id"])
        funding, created = Accounts.objects.get_or_create(
            broker=broker, native_id="funding",
            defaults={"name": "OKX Funding"},
        )
        self.stdout.write(self.style.SUCCESS(
            f"Renamed account {legacy.id} -> 'OKX Trading' (native_id=trading). "
            + ("Created 'OKX Funding' (id=%d)." % funding.id if created else "'OKX Funding' already existed (id=%d)." % funding.id)
            + " No transactions were modified."
        ))
