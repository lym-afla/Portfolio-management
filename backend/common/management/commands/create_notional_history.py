"""
Retroactively create NotionalHistory entries for existing bond redemptions.

Management command to retroactively create NotionalHistory entries
for existing bond redemptions.

This command is needed because:
1. bulk_create bypasses the save() method
2. Transactions imported before NotionalHistory was implemented
    don't have history entries
3. Users need to populate history for existing data after adding BondMetadata

Usage:
    python manage.py create_notional_history [--security-id ID] [--dry-run]
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from common.models import Transactions
from constants import TRANSACTION_TYPE_BOND_MATURITY, TRANSACTION_TYPE_BOND_REDEMPTION

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Create NotionalHistory entries for existing bond redemption transactions."""

    help = "Create NotionalHistory entries for existing bond redemption transactions"

    def add_arguments(self, parser):
        """Add arguments to the command."""
        parser.add_argument(
            "--security-id",
            type=int,
            help="Only process transactions for this specific security ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without actually creating history entries",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        security_id = options.get("security_id")
        dry_run = options.get("dry_run")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Build query for bond redemption transactions
        query = Transactions.objects.filter(
            type__in=[TRANSACTION_TYPE_BOND_REDEMPTION, TRANSACTION_TYPE_BOND_MATURITY]
        ).select_related("security")

        if security_id:
            query = query.filter(security_id=security_id)

        transactions = query.order_by("security", "date")

        if not transactions.exists():
            self.stdout.write(
                self.style.WARNING("No bond redemption transactions found")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {transactions.count()} bond redemption transactions"
            )
        )

        # Group transactions by security
        securities_processed = set()
        total_created = 0
        total_skipped = 0
        total_errors = 0

        for txn in transactions:
            if not txn.security:
                self.stdout.write(
                    self.style.WARNING(
                        f"Transaction {txn.id} has no security, skipping"
                    )
                )
                total_skipped += 1
                continue

            if not txn.notional_change or txn.notional_change == 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"Transaction {txn.id} has no notional_change, skipping"
                    )
                )
                total_skipped += 1
                continue

            # Check if bond has metadata
            try:
                bond_meta = txn.security.bond_metadata
                if not bond_meta:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Security {txn.security.name} (ID: {txn.security.id}) "
                            "has no BondMetadata, skipping transaction {txn.id}"
                        )
                    )
                    total_skipped += 1
                    continue
            except Exception:
                self.stdout.write(
                    self.style.WARNING(
                        f"Security {txn.security.name} (ID: {txn.security.id}) "
                        f"has no BondMetadata, skipping transaction {txn.id}"
                    )
                )
                total_skipped += 1
                continue

            # Log first transaction for each security
            if txn.security.id not in securities_processed:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nProcessing security: {txn.security.name} "
                        f"(ID: {txn.security.id})"
                    )
                )
                securities_processed.add(txn.security.id)

            try:
                if not dry_run:
                    with transaction.atomic():
                        txn._create_notional_history()
                        total_created += 1
                        self.stdout.write(
                            f"  ✓ Created NotionalHistory for transaction {txn.id} "
                            f"({txn.date}): notional_change={txn.notional_change}"
                        )
                else:
                    self.stdout.write(
                        f"  [DRY RUN] Would create NotionalHistory for transaction "
                        f"{txn.id} "
                        f"({txn.date}): notional_change={txn.notional_change}"
                    )
                    total_created += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ Error creating NotionalHistory for transaction "
                        f"{txn.id}: {e}"
                    )
                )
                total_errors += 1
                logger.error(
                    f"Error creating NotionalHistory for transaction {txn.id}: {e}",
                    exc_info=True,
                )

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("SUMMARY:"))
        self.stdout.write(f"  Securities processed: {len(securities_processed)}")
        self.stdout.write(f"  NotionalHistory entries created: {total_created}")
        self.stdout.write(f"  Transactions skipped: {total_skipped}")
        self.stdout.write(f"  Errors: {total_errors}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY RUN MODE - Run without --dry-run to apply changes"
                )
            )
