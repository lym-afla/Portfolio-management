from datetime import date, datetime
from decimal import Decimal
from itertools import chain
from operator import attrgetter

from django.db.models import Q

from common.models import Accounts, FXTransaction, Transactions

from .formatting_utils import currency_format, format_table_data
from .pagination_utils import paginate_table
from .portfolio_utils import get_selected_account_ids
from .sorting_utils import sort_entries


def get_transactions_table_api(request):
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
    effective_current_date = datetime.strptime(
        request.session["effective_current_date"], "%Y-%m-%d"
    ).date()

    currency_target = user.default_currency
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
    paginated_transactions, pagination_data = paginate_table(
        transactions_data, page, items_per_page
    )
    formatted_transactions = format_table_data(
        paginated_transactions, currency_target, number_of_digits
    )

    return {
        "transactions": formatted_transactions,
        "currencies": currencies,
        "total_items": pagination_data["total_items"],
        "current_page": pagination_data["current_page"],
        "total_pages": pagination_data["total_pages"],
    }


def _filter_transactions(user, start_date, end_date, selected_account_ids, search):
    """Filter transactions based on user criteria."""
    transactions_query = Transactions.objects.filter(
        investor=user,
        date__gte=start_date if start_date else date.min,
        date__lte=end_date,
        account_id__in=selected_account_ids,
    ).select_related("account", "security")

    fx_transactions_query = FXTransaction.objects.filter(
        investor=user,
        date__gte=start_date if start_date else date.min,
        date__lte=end_date,
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
    """Calculate transaction table output with balances."""
    currencies = set()
    for account in Accounts.objects.filter(broker__investor=user, id__in=selected_account_ids):
        currencies.update(account.get_currencies())

    # Initialize balance with the starting balance for each currency and account
    balance = {currency: Decimal(0) for currency in currencies}
    if start_date:
        for account_id in selected_account_ids:
            account = Accounts.objects.get(id=account_id)
            account_balance = account.balance(start_date)
            for currency, amount in account_balance.items():
                balance[currency] += amount

    transactions_data = []

    for transaction in transactions:
        transaction_data = {
            "date": transaction.date,
            "balances": {},
            "account": {"name": transaction.account.name, "id": transaction.account.id},
        }

        if isinstance(transaction, Transactions):
            transaction_data.update(
                _process_regular_transaction(transaction, balance, number_of_digits)
            )
        elif isinstance(transaction, FXTransaction):
            transaction_data.update(_process_fx_transaction(transaction, balance, number_of_digits))

        for currency in currencies:
            transaction_data["balances"][currency] = currency_format(
                balance[currency], currency, number_of_digits
            )

        transactions_data.append(transaction_data)

    return transactions_data, currencies


def _process_regular_transaction(transaction, balance, number_of_digits):
    """Process a regular transaction and update balances."""
    transaction_data = {
        "id": transaction.id,
        "transaction_type": "regular",
        "type": transaction.type,
        "security": {
            "name": transaction.security.name if transaction.security else None,
            "id": transaction.security.id if transaction.security else None,
        },
        "cur": transaction.currency,
    }

    balance[transaction.currency] = round(
        balance.get(transaction.currency, Decimal(0))
        - Decimal(
            (transaction.price or Decimal(0)) * Decimal(transaction.quantity or Decimal(0))
            - Decimal(transaction.cash_flow or Decimal(0))
            - Decimal(transaction.commission or Decimal(0))
        ),
        2,
    )

    if transaction.quantity:
        transaction_data["value"] = currency_format(
            -round(Decimal(transaction.quantity * transaction.price), 2)
            + (transaction.commission or 0),
            transaction.currency,
            number_of_digits,
        )
        transaction_data["price"] = currency_format(
            transaction.price, transaction.currency, number_of_digits
        )
        transaction_data["quantity"] = abs(round(transaction.quantity, 0))
    if transaction.cash_flow:
        transaction_data["cash_flow"] = currency_format(
            transaction.cash_flow, transaction.currency, number_of_digits
        )
    if transaction.commission:
        transaction_data["commission"] = currency_format(
            -transaction.commission, transaction.currency, number_of_digits
        )

    return transaction_data


def _process_fx_transaction(transaction, balance, number_of_digits):
    """Process an FX transaction and update balances."""
    transaction_data = {
        "id": transaction.id,
        "transaction_type": "fx",
        "type": "FX",
        "from_cur": transaction.from_currency,
        "to_cur": transaction.to_currency,
        "exchange_rate": transaction.exchange_rate,
    }

    balance[transaction.from_currency] -= transaction.from_amount
    balance[transaction.to_currency] += transaction.to_amount
    if transaction.commission:
        balance[transaction.commission_currency] += transaction.commission

    transaction_data["from_amount"] = 0
    transaction_data["to_amount"] = 0
    if transaction.commission:
        transaction_data["commission"] = currency_format(
            -transaction.commission, transaction.commission_currency, number_of_digits
        )
        if transaction.commission_currency == transaction.from_currency:
            transaction_data["from_amount"] += transaction.commission
        elif transaction.commission_currency == transaction.to_currency:
            transaction_data["to_amount"] += transaction.commission
    transaction_data["from_amount"] = currency_format(
        transaction_data["from_amount"] - transaction.from_amount,
        transaction.from_currency,
        number_of_digits,
    )
    transaction_data["to_amount"] = currency_format(
        transaction_data["to_amount"] + transaction.to_amount,
        transaction.to_currency,
        number_of_digits,
    )

    return transaction_data
