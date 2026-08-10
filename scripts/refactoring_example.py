#!/usr/bin/env python3
"""
Example refactoring of create_security_from_micex function to reduce complexity.
This shows the before/after approach for breaking down a complex function.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional


@dataclass
class SecurityCreationData:
    """Data class to hold security creation parameters."""

    security_name: str
    isin: str
    user: Any  # User object
    instrument_type: Any  # InstrumentType enum
    ticker: Optional[str] = None
    date_to_save: Optional[date] = None


@dataclass
class ParsedSecurityData:
    """Parsed and validated security data from MICEX."""

    asset_type: str
    exposure: str
    security_data: Dict[str, Any]
    identifier_used: str


@dataclass
class BondMetadataData:
    """Bond-specific metadata."""

    issue_date: Optional[date] = None
    maturity_date: Optional[date] = None
    initial_notional: Optional[Decimal] = None
    coupon_rate: Optional[Decimal] = None
    coupon_frequency: Optional[int] = None
    nominal_currency: Optional[str] = None
    is_amortizing: bool = False
    bond_type: str = "FIXED_RATE"


class MicexSecurityCreator:
    """
    Refactored class for creating securities from MICEX data.
    Breaks down the complex function into smaller, focused methods.
    """

    def __init__(self):
        self.logger = None  # Would inject logger in real implementation

    async def create_security_from_micex(self, creation_data: SecurityCreationData):
        """
        Create a new security using targeted MICEX API request.

        This is the main entry point - much simpler than the original function.
        """
        try:
            # Step 1: Determine identifier and fetch data
            identifier = self._determine_identifier(creation_data)
            security_data = await self._fetch_security_data(identifier, creation_data)

            if not security_data:
                self.logger.warning(
                    f"Security not found in MICEX: {creation_data.security_name}"
                )
                return None

            # Step 2: Parse and validate the fetched data
            parsed_data = self._parse_security_data(security_data, creation_data)

            # Step 3: Create the asset and metadata
            asset = await self._create_asset_and_metadata(parsed_data, creation_data)

            return asset

        except Exception as e:
            self.logger.error(f"Error creating security from MICEX: {e}", exc_info=True)
            return None

    def _determine_identifier(self, creation_data: SecurityCreationData) -> str:
        """
        Determine the identifier to use for MICEX lookup.

        For bonds: use ISIN, for others: use ticker (more reliable for MICEX)
        """
        if creation_data.instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
            return creation_data.isin
        else:
            # For stocks/ETFs/futures/options: use ticker if available, fallback to ISIN
            return creation_data.ticker if creation_data.ticker else creation_data.isin

    async def _fetch_security_data(
        self, identifier: str, creation_data: SecurityCreationData
    ) -> Optional[Dict]:
        """Fetch security data from MICEX API."""
        return await fetch_security_from_micex_targeted(
            identifier, creation_data.instrument_type
        )

    def _parse_security_data(
        self, security_data: Dict, creation_data: SecurityCreationData
    ) -> ParsedSecurityData:
        """
        Parse and validate security data from MICEX.

        Extract asset type and exposure based on instrument type.
        """
        asset_type, exposure = self._map_instrument_to_asset_type(
            creation_data.instrument_type
        )

        return ParsedSecurityData(
            asset_type=asset_type,
            exposure=exposure,
            security_data=security_data,
            identifier_used=self._determine_identifier(creation_data),
        )

    def _map_instrument_to_asset_type(self, instrument_type) -> tuple[str, str]:
        """
        Map instrument type to asset type and exposure.

        This was previously complex conditional logic - now it's a clean mapping.
        """
        type_mapping = {
            InstrumentType.INSTRUMENT_TYPE_SHARE: (
                ASSET_TYPE_CHOICES[0][0],  # Stock
                EXPOSURE_CHOICES[0][0],  # Equity
            ),
            InstrumentType.INSTRUMENT_TYPE_ETF: (
                ASSET_TYPE_CHOICES[2][0],  # ETF
                EXPOSURE_CHOICES[0][0],  # Equity
            ),
            InstrumentType.INSTRUMENT_TYPE_BOND: (
                ASSET_TYPE_CHOICES[1][0],  # Bond
                EXPOSURE_CHOICES[1][0],  # Fixed Income
            ),
            InstrumentType.INSTRUMENT_TYPE_FUTURES: (
                ASSET_TYPE_CHOICES[4][0],  # Future
                EXPOSURE_CHOICES[4][0],  # Derivatives
            ),
            InstrumentType.INSTRUMENT_TYPE_OPTION: (
                ASSET_TYPE_CHOICES[5][0],  # Option
                EXPOSURE_CHOICES[4][0],  # Derivatives
            ),
        }

        if instrument_type not in type_mapping:
            raise ValueError(f"Unsupported instrument type: {instrument_type}")

        return type_mapping[instrument_type]

    async def _create_asset_and_metadata(
        self, parsed_data: ParsedSecurityData, creation_data: SecurityCreationData
    ):
        """
        Create the main asset and associated metadata.

        This method delegates metadata creation to specialized methods.
        """

        @database_sync_to_async
        def create_in_database():
            # Create main asset
            asset = Assets.objects.create(
                type=parsed_data.asset_type,
                ISIN=parsed_data.security_data.get("isin") or creation_data.isin,
                name=parsed_data.security_data["name"],
                ticker=creation_data.ticker,
                currency=parsed_data.security_data["currency"],
                exposure=parsed_data.exposure,
                restricted=False,
                data_source="MICEX",
                secid=parsed_data.security_data["secid"],
            )
            asset.investors.add(creation_data.user)

            # Create type-specific metadata
            if creation_data.instrument_type == InstrumentType.INSTRUMENT_TYPE_BOND:
                self._create_bond_metadata(asset, parsed_data, creation_data)
            elif (
                creation_data.instrument_type == InstrumentType.INSTRUMENT_TYPE_FUTURES
            ):
                self._create_futures_metadata(asset, parsed_data, creation_data)
            elif creation_data.instrument_type == InstrumentType.INSTRUMENT_TYPE_OPTION:
                self._create_options_metadata(asset, parsed_data, creation_data)

            return asset

        return await create_in_database()

    def _create_bond_metadata(
        self,
        asset: Assets,
        parsed_data: ParsedSecurityData,
        creation_data: SecurityCreationData,
    ):
        """
        Create bond-specific metadata.

        This was the most complex part of the original function - now it's focused and testable.
        """
        data = parsed_data.security_data["data"]
        bond_data = self._parse_bond_data(data)

        BondMetadata.objects.create(asset=asset, **bond_data.__dict__)

    def _parse_bond_data(self, data: Dict[str, Any]) -> BondMetadataData:
        """
        Parse bond data from MICEX response.

        This method handles all the complex date parsing and field validation.
        """
        bond_data = BondMetadataData()

        # Parse dates
        bond_data.issue_date = self._parse_date_field(data, "ISSUEDATE")
        bond_data.maturity_date = self._parse_date_field(data, "MATDATE")

        # Parse numeric fields
        bond_data.initial_notional = self._parse_decimal_field(data, "INITIALFACEVALUE")
        bond_data.coupon_rate = self._parse_decimal_field(data, "COUPONPERCENT")
        bond_data.coupon_frequency = self._parse_int_field(data, "COUPONFREQUENCY")

        # Handle nominal currency
        bond_data.nominal_currency = self._parse_nominal_currency(data)

        # Determine if bond is amortizing
        bond_data.is_amortizing = self._is_amortizing_bond(data)

        # Determine bond type
        bond_data.bond_type = self._determine_bond_type(data)

        return bond_data

    def _parse_date_field(self, data: Dict, field_name: str) -> Optional[date]:
        """Parse a date field from MICEX data."""
        if data.get(field_name):
            try:
                return datetime.strptime(data[field_name], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                self.logger.warning(
                    f"Invalid date format for {field_name}: {data[field_name]}"
                )
        return None

    def _parse_decimal_field(self, data: Dict, field_name: str) -> Optional[Decimal]:
        """Parse a decimal field from MICEX data."""
        if data.get(field_name) is not None:
            try:
                return Decimal(str(data[field_name]))
            except (ValueError, TypeError, InvalidOperation):
                self.logger.warning(
                    f"Invalid decimal format for {field_name}: {data[field_name]}"
                )
        return None

    def _parse_int_field(self, data: Dict, field_name: str) -> Optional[int]:
        """Parse an integer field from MICEX data."""
        if data.get(field_name) is not None:
            try:
                return int(data[field_name])
            except (ValueError, TypeError):
                self.logger.warning(
                    f"Invalid integer format for {field_name}: {data[field_name]}"
                )
        return None

    def _parse_nominal_currency(self, data: Dict) -> Optional[str]:
        """Parse nominal currency, handling MICEX's 'SUR' to 'RUB' conversion."""
        if data.get("FACEUNIT"):
            nominal_curr = data["FACEUNIT"]
            return "RUB" if nominal_curr == "SUR" else nominal_curr
        return None

    def _is_amortizing_bond(self, data: Dict) -> bool:
        """Determine if bond is amortizing by comparing current and initial face values."""
        if data.get("FACEVALUE") and data.get("INITIALFACEVALUE"):
            try:
                current_face = Decimal(str(data["FACEVALUE"]))
                initial_face = Decimal(str(data["INITIALFACEVALUE"]))
                return current_face < initial_face
            except (ValueError, TypeError, InvalidOperation):
                self.logger.warning("Could not determine amortization status")
        return False

    def _determine_bond_type(self, data: Dict) -> str:
        """Determine bond type from coupon data."""
        if data.get("COUPONPERCENT"):
            try:
                coupon_pct = Decimal(str(data["COUPONPERCENT"]))
                if coupon_pct == 0:
                    return "ZERO_COUPON"
                # Additional logic for floating vs fixed would go here
                return "FIXED_RATE"
            except (ValueError, TypeError, InvalidOperation):
                pass
        return "FIXED_RATE"  # Default assumption

    def _create_futures_metadata(
        self,
        asset: Assets,
        parsed_data: ParsedSecurityData,
        creation_data: SecurityCreationData,
    ):
        """Create futures-specific metadata."""
        # Implementation for futures metadata
        pass

    def _create_options_metadata(
        self,
        asset: Assets,
        parsed_data: ParsedSecurityData,
        creation_data: SecurityCreationData,
    ):
        """Create options-specific metadata."""
        # Implementation for options metadata
        pass


# Usage example - how to call the refactored code:
async def example_usage():
    """Example of how to use the refactored security creator."""
    creator = MicexSecurityCreator()

    creation_data = SecurityCreationData(
        security_name="Sample Bond",
        isin="RU1234567890",
        user=some_user,
        instrument_type=InstrumentType.INSTRUMENT_TYPE_BOND,
        ticker="SAMPLE",
    )

    asset = await creator.create_security_from_micex(creation_data)
    return asset


"""
COMPLEXITY ANALYSIS:

Original function: create_security_from_micex
- Complexity: 64 (CRITICAL)
- Issues:
  * Long function with multiple responsibilities
  * Complex nested conditionals
  * Repeated date/number parsing logic
  * Hard to test individual parts
  * Poor separation of concerns

Refactored class: MicexSecurityCreator
- Main method complexity: ~8 (LOW)
- Individual method complexities: 3-10 (LOW-MEDIUM)
- Benefits:
  * Single responsibility principle
  * Each method has one clear purpose
  * Easy to test individual methods
  * Reusable parsing methods
  * Clear data flow
  * Better error handling
  * Improved maintainability

REFACTORING PATTERNS USED:
1. Extract Method Pattern - Broke down large function
2. Data Class Pattern - Structured parameter passing
3. Strategy Pattern - Different metadata creation for different types
4. Template Method Pattern - Consistent creation workflow
5. Factory Pattern - Metadata creation delegated to specialized methods

TESTING STRATEGY:
1. Unit tests for each parsing method
2. Integration tests for the main workflow
3. Mock external API calls
4. Test error conditions individually
5. Verify metadata creation for each security type
"""
