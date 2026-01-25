"""
BalanceTracker: Helper class for tracking multi-currency balances in transaction lists.

This class provides a unified way to track and format balances across different currencies
as transactions are processed.
"""

from decimal import Decimal
from typing import Dict, List

from core.formatting_utils import currency_format


class BalanceTracker:
    """
    Tracks running balances in multiple currencies for transaction processing.

    Usage:
        tracker = BalanceTracker(number_of_digits=2)

        # Update balance for a transaction
        tracker.update(transaction)

        # Get formatted balances for a specific transaction
        balances = tracker.get_balances_for_transaction(transaction.id)

        # Initialize starting balances
        tracker.set_initial_balances({"USD": Decimal("1000"), "EUR": Decimal("500")})
    """

    def __init__(self, number_of_digits: int = 2):
        """
        Initialize the balance tracker.

        Args:
            number_of_digits: Number of decimal places for formatting
        """
        self.number_of_digits = number_of_digits
        self.balances: Dict[str, Decimal] = {}
        self.transaction_balances: Dict[int, Dict[str, str]] = {}
        self.currencies: set = set()

    def set_initial_balances(self, initial_balances: Dict[str, Decimal]) -> None:
        """
        Set initial balances for currencies.

        Args:
            initial_balances: Dictionary of currency -> balance
        """
        self.balances = initial_balances.copy()
        self.currencies.update(initial_balances.keys())

    def update(self, transaction) -> None:
        """
        Update balances based on a transaction.

        Args:
            transaction: Transaction or FXTransaction instance
        """
        from common.models import FXTransaction, Transactions

        if isinstance(transaction, Transactions):
            self._update_regular_transaction(transaction)
        elif isinstance(transaction, FXTransaction):
            self._update_fx_transaction(transaction)

    def _update_regular_transaction(self, transaction) -> None:
        """Update balances for a regular transaction."""
        currency = transaction.currency

        # Ensure currency exists in balance tracker
        if currency not in self.balances:
            self.balances[currency] = Decimal(0)

        self.currencies.add(currency)

        # Update balance using the centralized cash flow method
        cash_flow = transaction.get_calculated_cash_flow()
        self.balances[currency] += cash_flow

        # Store formatted balances for this transaction
        self._store_transaction_balances(transaction.id)

    def _update_fx_transaction(self, fx_transaction) -> None:
        """Update balances for an FX transaction using centralized method."""
        from_currency = fx_transaction.from_currency
        to_currency = fx_transaction.to_currency
        commission_currency = fx_transaction.commission_currency

        # Collect all currencies involved
        involved_currencies = {from_currency, to_currency}
        if commission_currency:
            involved_currencies.add(commission_currency)

        # Ensure currencies exist in balance tracker and update them
        for currency in involved_currencies:
            if currency not in self.balances:
                self.balances[currency] = Decimal(0)
            self.currencies.add(currency)

            # Use centralized cash flow calculation
            cash_flow = fx_transaction.get_cash_flow_by_currency(currency)
            self.balances[currency] += cash_flow

        # Store formatted balances for this transaction
        self._store_transaction_balances(fx_transaction.id)

    def _store_transaction_balances(self, transaction_id: int) -> None:
        """Store formatted balances for a transaction."""
        formatted_balances = {}
        for currency in self.currencies:
            formatted_balances[currency] = currency_format(
                self.balances.get(currency, Decimal(0)), currency, self.number_of_digits
            )
        self.transaction_balances[transaction_id] = formatted_balances

    def get_balances_for_transaction(self, transaction_id: int) -> Dict[str, str]:
        """
        Get formatted balances for a specific transaction.

        Args:
            transaction_id: ID of the transaction

        Returns:
            Dictionary of currency -> formatted balance string
        """
        return self.transaction_balances.get(transaction_id, {})

    def get_all_balances(self) -> Dict[int, Dict[str, str]]:
        """
        Get all stored transaction balances.

        Returns:
            Dictionary mapping transaction IDs to their balance dictionaries
        """
        return self.transaction_balances

    def get_currencies(self) -> List[str]:
        """
        Get list of all currencies being tracked.

        Returns:
            Sorted list of currency codes
        """
        return sorted(self.currencies)
