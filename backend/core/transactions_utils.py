"""Utility functions for retrieving and formatting transaction data.

This module provides functions to retrieve transactions, calculate running
balances, and format transaction data for display in tables.
"""

from datetime import date, datetime
from decimal import Decimal
from itertools import chain
from operator import attrgetter

from django.db.models import Q

from common.models import Accounts, FXTransaction, Transactions
from database.serializers import FXTransactionSerializer, TransactionSerializer

from .balance_tracker import BalanceTracker
from .pagination_utils import paginate_table
from .portfolio_utils import get_selected_account_ids
from .sorting_utils import sort_entries


def get_transactions_table_api(request):
    """Retrieve and format transactions table data for API response.

    Args:
        request: The HTTP request object containing user context and parameters.

    Returns:
        dict: Dictionary containing formatted transactions data, balances, and
            pagination information with keys: transactions, balances, total_items,
            current_page, total_pages.
    """
    data = request.data
    start_date = (
        datetime.strptime(data.get("dateFrom", None), "%Y-%m-%d").date()
        if data.get("dateFrom")
        else None
    )
    end_date = (
        datetime.strptime(data.get("dateTo", None), "%Y-%m-%d").date()
        if data.get("dateTo")
        else None
    )
    page = int(data.get("page", 1))
    items_per_page = int(data.get("itemsPerPage", 25))
    search = data.get("search", "")
    sort_by = data.get("sortBy", {})

    user = request.user
    # Use JWT middleware instead of session
    effective_current_date_str = getattr(
        request, "effective_current_date", date.today().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()

    number_of_digits = user.digits
    selected_account_ids = get_selected_account_ids(
        user, user.selected_account_type, user.selected_account_id
    )

    # Handle empty dates
    if not end_date:
        end_date = effective_current_date

    transactions = _filter_transactions(user, start_date, end_date, selected_account_ids, search)

    transactions_data, currencies = _calculate_transactions_table_output(
        user, transactions, selected_account_ids, number_of_digits, start_date
    )

    transactions_data = sort_entries(transactions_data, sort_by)
    paginated_page, pagination_data = paginate_table(transactions_data, page, items_per_page)
    # Convert Page object to list for JSON serialization
    paginated_transactions = list(paginated_page)

    # Note: format_table_data is NOT needed - serializers already format everything

    return {
        "transactions": paginated_transactions,  # Already formatted by serializers
        "currencies": currencies,
        "total_items": pagination_data["total_items"],
        "current_page": pagination_data["current_page"],
        "total_pages": pagination_data["total_pages"],
    }


def _filter_transactions(user, start_date, end_date, selected_account_ids, search):
    """Filter transactions based on user criteria."""
    transactions_query = Transactions.objects.filter(
        investor=user,
        date__date__gte=start_date if start_date else date.min,
        date__date__lte=end_date,
        account_id__in=selected_account_ids,
    ).select_related("account", "security")

    fx_transactions_query = FXTransaction.objects.filter(
        investor=user,
        date__date__gte=start_date if start_date else date.min,
        date__date__lte=end_date,
        account_id__in=selected_account_ids,
    ).select_related("account")

    if search:
        transactions_query = transactions_query.filter(
            Q(security__name__icontains=search) | Q(type__icontains=search)
        )
        fx_transactions_query = fx_transactions_query.filter(
            Q(from_currency__icontains=search) | Q(to_currency__icontains=search)
        )

    return sorted(chain(transactions_query, fx_transactions_query), key=attrgetter("date"))


def _calculate_transactions_table_output(
    user, transactions, selected_account_ids, number_of_digits, start_date=None
):
    """
    Calculate transaction table output with balances using unified serializers.

    This is the new DRY implementation that uses:
    - TransactionSerializer for regular transactions
    - FXTransactionSerializer for FX transactions
    - BalanceTracker for balance management
    """
    # Get all currencies used in the accounts
    currencies = set()
    for account in Accounts.objects.filter(broker__investor=user, id__in=selected_account_ids):
        currencies.update(account.get_currencies())

    # Initialize balance tracker
    balance_tracker = BalanceTracker(number_of_digits=number_of_digits)

    # Set initial balances if start_date is provided
    initial_balances = {currency: Decimal(0) for currency in currencies}
    if start_date:
        for account_id in selected_account_ids:
            account = Accounts.objects.get(id=account_id)
            account_balance = account.balance(start_date)
            for currency, amount in account_balance.items():
                initial_balances[currency] += amount

    balance_tracker.set_initial_balances(initial_balances)

    # Process transactions and build data
    transactions_data = []

    for transaction in transactions:
        # Update balance tracker
        balance_tracker.update(transaction)

        # Serialize the transaction
        if isinstance(transaction, Transactions):
            serializer = TransactionSerializer(
                transaction,
                context={
                    "digits": number_of_digits,
                    "include_balances": True,
                    "balance_tracker": balance_tracker.get_all_balances(),
                },
            )
        elif isinstance(transaction, FXTransaction):
            serializer = FXTransactionSerializer(
                transaction,
                context={
                    "digits": number_of_digits,
                    "include_balances": True,
                    "balance_tracker": balance_tracker.get_all_balances(),
                },
            )
        else:
            continue

        transactions_data.append(serializer.data)

    return transactions_data, balance_tracker.get_currencies()


# DEPRECATED: These functions are no longer used. Transaction processing now uses
# the unified TransactionSerializer and FXTransactionSerializer with BalanceTracker.
# Keeping for reference during migration period.
#
# def _process_regular_transaction(transaction, balance, number_of_digits):
#     """OLD: Process a regular transaction and update balances."""
#     ...
#
# def _process_fx_transaction(transaction, balance, number_of_digits):
#     """OLD: Process an FX transaction and update balances."""
#     ...
