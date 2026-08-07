"""One-time data backfill: set OptionMetadata.contract_size by underlying.

Existing option assets created by the old importer have contract_size=1.0
(the hardcoded default). This command parses each option's underlying from
its Assets.name (format ``{UNDERLYING}-{DDMMMYY}-{STRIKE}-{C|P}``) and sets
the correct size (BTC -> 0.01, ETH -> 0.1, ...).

This is a DATA fix, not a schema migration — it lives outside migrations/
per AGENTS.md (migrations are protected). Idempotent: only rows with
contract_size == 1 (or null) are updated; correctly-sized rows are skipped.
"""
from django.core.management.base import BaseCommand

from common.models import OptionMetadata
from services.crypto_exchange import parse_option_symbol
from services.options import contract_size_for_underlying


class Command(BaseCommand):
    help = "Backfill OptionMetadata.contract_size from the option's underlying."

    def handle(self, *args, **options):
        updated = 0
        skipped = 0
        for meta in OptionMetadata.objects.select_related("asset").all():
            # Only touch rows still on the old default (1.0) or null.
            if meta.contract_size is not None and meta.contract_size != 1:
                skipped += 1
                continue
            name = meta.asset.name if meta.asset else ""
            try:
                parsed = parse_option_symbol(name)
                underlying = parsed["underlying"]
            except (ValueError, KeyError, TypeError):
                # Fallback: try OptionMetadata.underlying_asset.ticker
                underlying = (
                    meta.underlying_asset.ticker if meta.underlying_asset_id else ""
                )
            if not underlying:
                self.stdout.write(self.style.WARNING(
                    f"Could not parse underlying for OptionMetadata {meta.id} "
                    f"(name={name!r}); skipping."
                ))
                skipped += 1
                continue
            new_size = contract_size_for_underlying(underlying)
            meta.contract_size = new_size
            meta.save(update_fields=["contract_size"])
            updated += 1
        self.stdout.write(self.style.SUCCESS(
            f"Backfill complete: {updated} updated, {skipped} skipped."
        ))
