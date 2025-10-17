"""
Django management command to fetch and cache coupon schedules for all bonds in the database.
"""

import asyncio
import logging

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from common.models import Assets
from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule
from users.models import CustomUser

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch and cache coupon schedules for all bonds in the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-refresh",
            action="store_true",
            help="Force refresh existing schedules (useful for floating-rate bonds)",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="User ID to use for T-Bank API access (defaults to first superuser)",
        )
        parser.add_argument(
            "--bond-id",
            type=int,
            help="Specific bond asset ID to update (optional, otherwise updates all bonds)",
        )

    def handle(self, *args, **options):
        force_refresh = options.get("force_refresh", False)
        user_id = options.get("user_id")
        bond_id = options.get("bond_id")

        # Get user for API access
        if user_id:
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
                return
        else:
            # Use first superuser
            user = CustomUser.objects.filter(is_superuser=True).first()
            if not user:
                self.stdout.write(
                    self.style.ERROR(
                        "No superuser found. Please create a superuser or specify --user-id"
                    )
                )
                return

        self.stdout.write(f"Using user: {user.username} (ID: {user.id})")

        # Get bonds to update
        if bond_id:
            bonds = Assets.objects.filter(id=bond_id, type="Bond")
            if not bonds.exists():
                self.stdout.write(
                    self.style.ERROR(
                        f"Bond with ID {bond_id} not found or has no T-Bank instrument UID"
                    )
                )
                return
        else:
            bonds = Assets.objects.filter(type="Bond")

        total_bonds = bonds.count()
        self.stdout.write(f"Found {total_bonds} bond(s) with T-Bank instrument UID")

        if force_refresh:
            self.stdout.write(
                self.style.WARNING("Force refresh enabled - will update existing schedules")
            )

        # Fetch schedules
        success_count = 0
        failed_count = 0

        async def fetch_all():
            nonlocal success_count, failed_count

            from channels.db import database_sync_to_async

            # Convert QuerySet to list to avoid sync DB calls in async context
            bonds_list = await database_sync_to_async(list)(bonds)

            for idx, bond in enumerate(bonds_list, 1):
                self.stdout.write(
                    f"\n[{idx}/{total_bonds}] Processing: {bond.name} ({bond.ISIN})",
                    ending="",
                )

                try:
                    success = await fetch_and_cache_bond_coupon_schedule(
                        bond, user, force_refresh=force_refresh
                    )

                    if success:
                        self.stdout.write(self.style.SUCCESS(" [OK] Success"))
                        success_count += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(" [WARN] Failed (no data or API error)")
                        )
                        failed_count += 1

                    # Small delay to avoid API rate limits
                    if idx < total_bonds:
                        await asyncio.sleep(0.3)

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f" [ERROR] Error: {str(e)}"))
                    failed_count += 1

        # Run async function
        async_to_sync(fetch_all)()

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"[OK] Successful: {success_count}"))
        if failed_count > 0:
            self.stdout.write(self.style.WARNING(f"[WARN] Failed: {failed_count}"))
        self.stdout.write(self.style.SUCCESS(f"\nTotal processed: {total_bonds}"))
        self.stdout.write("=" * 60)
