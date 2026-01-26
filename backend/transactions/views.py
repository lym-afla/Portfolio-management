"""Transactions views."""

import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from fuzzywuzzy import fuzz
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.models import Accounts, Assets, FXTransaction, Transactions
from constants import (
    ACCOUNT_IDENTIFIERS,
    CHARLES_STANLEY_BROKER,
    CURRENCY_CHOICES,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
)
from core.broker_api_utils import TinkoffAPIException, get_broker_api
from core.import_utils import (
    fx_transaction_exists,
    get_account,
    get_broker,
    parse_charles_stanley_transactions,
    parse_galaxy_account_cash_flows,
    parse_galaxy_account_security_transactions,
    transaction_exists,
)
from core.transactions_utils import get_transactions_table_api

from .serializers import FXTransactionFormSerializer, TransactionFormSerializer

logger = logging.getLogger(__name__)


@database_sync_to_async
def ensure_account_native_ids(user, broker_api):
    """
    Ensure that all Tinkoff accounts have their native_id set properly.

    :param user: The user whose accounts should be synchronized
    :param broker_api: An instance of the TinkoffAPI class
    :return: A dictionary mapping Tinkoff account IDs to Accounts model instances
    """
    from tinkoff.invest import Client

    # Get the token
    try:
        with Client(broker_api.token) as client:
            # Get all Tinkoff accounts
            tinkoff_accounts = client.users.get_accounts()

            # Create a mapping of account names to their IDs
            tinkoff_account_map = {
                account.name: account.id for account in tinkoff_accounts.accounts
            }

            # Get all user's broker accounts for Tinkoff
            tinkoff_brokers = [
                broker for broker in user.brokers.all() if broker.tinkoff_tokens.exists()
            ]

            updated_accounts = {}

            # Update each account's native_id if needed
            for broker in tinkoff_brokers:
                for account in broker.accounts.all():
                    # Skip accounts that already have a native_id
                    if account.native_id and account.is_active:
                        updated_accounts[account.native_id] = account
                        continue

                    # Try to find a matching account by name
                    if account.name in tinkoff_account_map:
                        account.native_id = tinkoff_account_map[account.name]
                        account.save(update_fields=["native_id"])
                        logger.info(
                            "Updated native_id for account "
                            f"{account.name} to {account.native_id}"
                        )
                        updated_accounts[account.native_id] = account

            # Log accounts that weren't matched
            for tinkoff_name, tinkoff_id in tinkoff_account_map.items():
                if tinkoff_id not in updated_accounts.values():
                    logger.warning(
                        f"Tinkoff account '{tinkoff_name}' (ID: {tinkoff_id})"
                        " not matched to any database account"
                    )

            return updated_accounts

    except Exception as e:
        logger.error(f"Error synchronizing Tinkoff account IDs: {str(e)}")
        return {}


class TransactionViewSet(viewsets.ModelViewSet):
    """Transaction view set."""

    serializer_class = TransactionFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get the queryset for the transaction view set.

        :return: The queryset for the transaction view set
        """
        logger.info(f"Getting queryset for transaction view set for user {self.request.user.id}")
        return Transactions.objects.filter(investor=self.request.user)

    def perform_create(self, serializer):
        """Perform the create action for the transaction view set.

        :param serializer: The serializer object
        """
        logger.info(
            f"Performing create action for transaction view set for user " f"{self.request.user.id}"
        )
        serializer.save(investor=self.request.user)

    def get_object(self):
        """Get the transaction object.

        :param pk: The primary key of the transaction
        :return: The transaction object
        :raises NotFound: If the transaction is not found
        """
        transaction_id = self.kwargs.get("pk")
        logger.info(
            f"Getting transaction object for user {self.request.user.id} and "
            f"transaction {transaction_id}"
        )
        try:
            return Transactions.objects.get(id=transaction_id, investor=self.request.user)
        except Transactions.DoesNotExist:
            raise NotFound(f"Transaction with id {transaction_id} not found.")

    @action(detail=False, methods=["POST"])
    def get_transactions_table(self, request):
        """Get the transactions table API.

        :param request: The request object
        :return: A response object
        """
        return Response(get_transactions_table_api(request))

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        """Get the form structure for the transaction.

        :param request: The request object
        :return: A response object
        """
        logger.info(f"Getting form structure for transaction for user {request.user.id}")
        form_serializer = TransactionFormSerializer()
        return Response(
            {
                "fields": [
                    {
                        "name": "id",
                        "label": "ID",
                        "type": "hidden",
                        "required": False,
                    },
                    {
                        "name": "date",
                        "label": "Date",
                        "type": "datepicker",
                        "required": True,
                    },
                    {
                        "name": "account",
                        "label": "Broker Account",
                        "type": "select",
                        "required": True,
                        "choices": form_serializer.get_account_choices(request.user),
                    },
                    {
                        "name": "security",
                        "label": "Select Security",
                        "type": "select",
                        "required": False,
                        "choices": form_serializer.get_security_choices(request.user),
                    },
                    {
                        "name": "currency",
                        "label": "Currency",
                        "type": "select",
                        "required": True,
                        "choices": [
                            {
                                "value": currency[0],
                                "text": f"{currency[1]} ({currency[0]})",
                            }
                            for currency in CURRENCY_CHOICES
                        ],
                    },
                    {
                        "name": "type",
                        "label": "Type",
                        "type": "select",
                        "required": True,
                        "choices": [
                            {"value": type[0], "text": type[0]}
                            for type in Transactions._meta.get_field("type").choices
                            if type[0]
                        ],
                    },
                    {
                        "name": "quantity",
                        "label": "Quantity",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "price",
                        "label": "Price",
                        "type": "number",
                        "required": False,
                        "helper_text": (
                            "For bonds: enter as percentage of par " "(e.g., 98.5 for 98.5%)"
                        ),
                    },
                    {
                        "name": "notional",
                        "label": "Notional (for bonds)",
                        "type": "number",
                        "required": False,
                        "helper_text": "Par value per bond (e.g., 1000)",
                    },
                    {
                        "name": "cash_flow",
                        "label": "Cash Flow",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "aci",
                        "label": "ACI",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "commission",
                        "label": "Commission",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "comment",
                        "label": "Comment",
                        "type": "textarea",
                        "required": False,
                    },
                ]
            }
        )

    def search_keywords_in_excel(self, file_path):
        """Search keywords in an Excel file.

        :param file_path: The path to the Excel file
        :return: The content of the Excel file
        """
        df = pd.read_excel(file_path)
        content = df.to_string().lower()
        return content

    def identify_account(self, content, user):
        """Identify the broker account for a given content.

        :param content: The content to identify the broker account for
        :param user: The user to identify the broker account for
        :return: The broker account
        """
        logger.info(f"Starting broker account identification for user {user.id}")
        best_match = None
        best_score = 0
        perfect_match_threshold = 100
        # content_limit = 10000  # Limit content to first 10,000 characters

        # Limit the content size
        lower_content = content.lower()
        logger.debug(f"Content length: {len(lower_content)} characters")

        for account_name, config in ACCOUNT_IDENTIFIERS.items():
            logger.debug(f"Checking broker account: {account_name}")
            keywords = config["keywords"]
            threshold = config["fuzzy_threshold"]

            account_scores = []
            all_keywords_perfect = True

            for keyword in keywords:
                logger.debug(f"Searching for keyword: {keyword}")
                # Use regex to find potential matches quickly
                potential_matches = re.finditer(re.escape(keyword.lower()), lower_content)

                keyword_best_score = 0
                for match in potential_matches:
                    # Get the surrounding context
                    # (50 characters before and after the match)
                    start = max(0, match.start() - 50)
                    end = min(len(lower_content), match.end() + 50)
                    context = lower_content[start:end]

                    # Perform fuzzy matching on the context
                    score = fuzz.partial_ratio(keyword.lower(), context)
                    logger.debug(f"Fuzzy match score for '{keyword}': {score}")

                    if score == perfect_match_threshold:
                        keyword_best_score = score
                        break

                    keyword_best_score = max(keyword_best_score, score)

                account_scores.append(keyword_best_score)
                if keyword_best_score < perfect_match_threshold:
                    all_keywords_perfect = False

                logger.debug(f"Best score for keyword '{keyword}': {keyword_best_score}")

            # Calculate the average score for this account
            avg_score = sum(account_scores) / len(account_scores)
            logger.info(f"Average score for broker account {account_name}: {avg_score}")

            if all_keywords_perfect:
                logger.info(
                    "Perfect match found for all keywords of broker account " f"{account_name}"
                )
                try:
                    account = Accounts.objects.get(broker__investor=user, name__iexact=account_name)
                    logger.info(
                        f"Returning perfectly matched broker account: {account.name} "
                        f"(ID: {account.id})"
                    )
                    return account
                except Accounts.DoesNotExist:
                    logger.warning(
                        f"Perfect match found for {account_name}, "
                        "but no corresponding Accounts object exists for this user"
                    )
                    return None

            if avg_score > threshold and avg_score > best_score:
                best_score = avg_score
                best_match = account_name
                logger.debug(f"New best match: {best_match} with average score {best_score}")

        if best_match:
            logger.info(f"Best match found: {best_match} with average score {best_score}")
            try:
                account = Accounts.objects.get(broker__investor=user, name__iexact=best_match)
                logger.info(
                    f"Returning best matched broker account: {account.name} " f"(ID: {account.id})"
                )
                return account
            except Accounts.DoesNotExist:
                logger.warning(
                    f"Best match {best_match} found, "
                    "but no corresponding Broker object exists for this user"
                )
                return None

        logger.info("No broker account match found")
        return None

    @action(detail=False, methods=["POST"])
    def analyze_file(self, request):
        """Analyze a file for broker account identification.

        :param request: The request object
        :param request: The request object
        :return: A response object
        """
        if "file" not in request.FILES:
            return Response({"error": "No file was uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES["file"]
        file_id = str(uuid.uuid4())
        file_name = f"temp_{file_id}_{file.name}"
        temp_storage = FileSystemStorage(location=settings.TEMP_FILE_DIR)
        saved_file_name = temp_storage.save(file_name, file)
        file_path = os.path.join(settings.TEMP_FILE_DIR, saved_file_name)
        logger.info(f"File saved at: {file_path}")

        try:
            logger.debug(f"Request data: {request.data}")
            if request.data.get("is_galaxy") == "true":
                return Response(
                    {
                        "status": "account_not_identified",
                        "message": "Galaxy file detected.",
                        "fileId": file_id,
                    },
                    status=status.HTTP_200_OK,
                )

            content = self.search_keywords_in_excel(file_path)
            identified_account = self.identify_account(content, request.user)

            if identified_account:
                return Response(
                    {
                        "status": "account_identified",
                        "message": "Broker account was automatically identified.",
                        "fileId": file_id,
                        "identifiedAccount": {
                            "id": identified_account.id,
                            "name": identified_account.name,
                        },
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "status": "account_not_identified",
                        "message": (
                            "The broker account could not be automatically identified "
                            "from the file."
                        ),
                        "fileId": file_id,
                    },
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["POST"])
    def get_security_position(self, request):
        """
        Get the current position (quantity) for a security in a specific account.

        :param request: The request object
        :return: A response object
        """
        try:
            security_id = request.data.get("security_id")
            account_id = request.data.get("account_id")
            date_str = request.data.get("date")

            if not all([security_id, account_id]):
                return Response(
                    {"error": "Missing required fields: security_id, account_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Parse date or use today
            if date_str:
                from datetime import datetime as dt

                position_date = dt.strptime(date_str, "%Y-%m-%d").date()
            else:
                from datetime import date

                position_date = date.today()

            # Get the security
            try:
                security = Assets.objects.get(id=security_id, investors=request.user)
            except Assets.DoesNotExist:
                return Response(
                    {"error": f"Security with id {security_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get the account
            try:
                account = Accounts.objects.get(  # noqa: F841
                    id=account_id, broker__investor=request.user
                )
            except Accounts.DoesNotExist:
                return Response(
                    {"error": f"Account with id {account_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Calculate current position
            position = security.position(
                date=position_date, investor=request.user, account_ids=[account_id]
            )

            return Response(
                {
                    "security_id": security_id,
                    "account_id": account_id,
                    "position": float(position) if position else 0,
                    "date": position_date.isoformat(),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error in get_security_position: {str(e)}", exc_info=True)
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["POST"])
    def transfer_asset(self, request):
        """
        Transfer an asset from one broker account to another.

        Creates a sale from the source account and a purchase in the destination account
        at the average cost basis (zero realized gain).

        :param request: The request object
        :return: A response object
        """
        try:
            # Extract request data
            security_id = request.data.get("security")
            from_account_id = request.data.get("fromAccount")
            to_account_id = request.data.get("toAccount")
            quantity = request.data.get("quantity")
            transfer_date_str = request.data.get("date")

            # Validate required fields
            if not all(
                [
                    security_id,
                    from_account_id,
                    to_account_id,
                    quantity,
                    transfer_date_str,
                ]
            ):
                return Response(
                    {
                        "error": (
                            "Missing required fields: security, fromAccount, toAccount, quantity, date"  # noqa: E501
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Parse date
            transfer_date = datetime.strptime(transfer_date_str, "%Y-%m-%d").date()

            # Get the security
            try:
                security = Assets.objects.get(id=security_id, investors=request.user)
            except Assets.DoesNotExist:
                return Response(
                    {"error": f"Security with id {security_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get the accounts
            try:
                from_account = Accounts.objects.get(
                    id=from_account_id, broker__investor=request.user
                )
                to_account = Accounts.objects.get(id=to_account_id, broker__investor=request.user)
            except Accounts.DoesNotExist:
                return Response(
                    {"error": "One or both accounts not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Calculate the average buy-in price for the security in the from_account
            buy_in_price = security.calculate_buy_in_price(
                date=transfer_date,
                investor=request.user,
                account_ids=[from_account_id],
            )

            if buy_in_price is None:
                return Response(
                    {
                        "error": (
                            "Unable to calculate buy-in price. "
                            "No prior transactions found for this security in the "
                            "source account."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the currency from the security
            currency = security.currency

            # Create comments
            sale_comment = f"Transfer out to {to_account.name}"
            buy_comment = f"Transfer in from {from_account.name}"
            cash_comment = f"Phantom cash movement for asset transfer: {security.name}"

            # Calculate transfer value
            transfer_value = Decimal(quantity) * buy_in_price

            # Create all transactions atomically
            with transaction.atomic():
                # 1. Sell transaction (from_account) - negative quantity
                sale_transaction = Transactions.objects.create(
                    investor=request.user,
                    account=from_account,
                    security=security,
                    date=transfer_date,
                    type="Sell",
                    quantity=-Decimal(quantity),  # Negative for sell
                    price=buy_in_price,
                    currency=currency,
                    cash_flow=None,  # Empty cash flow
                    commission=None,  # Empty commission
                    comment=sale_comment,
                )

                # 2. Buy transaction (to_account) - positive quantity
                buy_transaction = Transactions.objects.create(
                    investor=request.user,
                    account=to_account,
                    security=security,
                    date=transfer_date,
                    type="Buy",
                    quantity=Decimal(quantity),  # Positive for buy
                    price=buy_in_price,
                    currency=currency,
                    cash_flow=None,  # Empty cash flow
                    commission=None,  # Empty commission
                    comment=buy_comment,
                )

                # 3. Phantom cash-out transaction (from_account) -
                # to balance the cash effect
                cash_in_transaction = Transactions.objects.create(
                    investor=request.user,
                    account=from_account,
                    security=None,
                    date=transfer_date,
                    type="Cash out",
                    quantity=None,
                    price=None,
                    currency=currency,
                    cash_flow=-transfer_value,  # Negative cash flow
                    commission=None,
                    comment=cash_comment,
                )

                # 4. Phantom cash-in transaction (to_account) -
                # to balance the cash effect
                cash_out_transaction = Transactions.objects.create(
                    investor=request.user,
                    account=to_account,
                    security=None,
                    date=transfer_date,
                    type="Cash in",
                    quantity=None,
                    price=None,
                    currency=currency,
                    cash_flow=transfer_value,  # Positive cash flow
                    commission=None,
                    comment=cash_comment,
                )

            logger.info(
                f"Asset transfer completed: {quantity} units of {security.name} "
                f"from {from_account.name} to {to_account.name} at "
                f"{buy_in_price} {currency}"
            )

            return Response(
                {
                    "message": "Asset transfer completed successfully",
                    "sale_transaction_id": sale_transaction.id,
                    "buy_transaction_id": buy_transaction.id,
                    "cash_in_transaction_id": cash_in_transaction.id,
                    "cash_out_transaction_id": cash_out_transaction.id,
                    "transfer_price": float(buy_in_price),
                    "transfer_value": float(transfer_value),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error in transfer_asset: {str(e)}", exc_info=True)
            return Response(
                {"error": f"An error occurred during asset transfer: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    async def import_transactions_from_file(
        self, user, file_id, account_id, confirm_every, currency, is_galaxy, galaxy_type
    ):
        """
        Import transactions from a file.

        :param user: The user to import transactions for
        :param file_id: The ID of the file to import transactions from
        :param account_id: The ID of the account to import transactions to
        :param confirm_every: The number of transactions to confirm after
        :param currency: The currency to import transactions in
        :param is_galaxy: Whether the account is a Galaxy account
        :param galaxy_type: The type of Galaxy account
        :return: A generator of updates
        """
        logger.debug("Starting import transactions from file")
        file_path = None
        try:
            file_path, account_id = await self.validate_import_data(file_id, account_id)
            account = await get_account(account_id)

            if is_galaxy:
                if not currency:
                    raise ValueError("Currency is required for Galaxy imports")

                if galaxy_type == "cash":
                    async for update in parse_galaxy_account_cash_flows(
                        file_path, currency, account, user, confirm_every
                    ):
                        yield update
                else:
                    async for update in parse_galaxy_account_security_transactions(
                        file_path, currency, account, user, confirm_every
                    ):
                        yield update

            elif CHARLES_STANLEY_BROKER in account.broker.name:
                async for update in parse_charles_stanley_transactions(
                    file_path, "GBP", account_id, user.id, confirm_every
                ):
                    yield update
            else:
                yield {
                    "status": "critical_error",
                    "message": f"Unsupported broker for import: {account.broker.name}",
                }

        except Exception as e:
            logger.error(f"Error in import_transactions: {str(e)}", exc_info=True)
            yield {
                "status": "critical_error",
                "message": f"An error occurred during import: {str(e)}",
            }
        finally:
            logger.debug("Finishing import_transactions")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Temporary file deleted: {file_path}")

    @database_sync_to_async
    def validate_import_data(self, file_id, account_id):
        """Validate import data."""
        if not file_id or not isinstance(file_id, str):
            raise ValidationError("Invalid file ID")

        try:
            account_id = int(account_id)
        except ValueError:
            raise ValidationError("Invalid broker account ID")

        temp_storage = FileSystemStorage(location=settings.TEMP_FILE_DIR)
        matching_files = [
            f for f in temp_storage.listdir("")[1] if f.startswith(f"temp_{file_id}_")
        ]

        if not matching_files:
            raise ValidationError("No matching file found for the given file ID")
        elif len(matching_files) > 1:
            raise ValidationError("Multiple matching files found. Please try again")

        file_path = os.path.join(settings.TEMP_FILE_DIR, matching_files[0])

        # Validate file extension
        allowed_extensions = ["xlsx", "xls", "csv"]
        file_extension = os.path.splitext(file_path)[1][1:].lower()
        if file_extension not in allowed_extensions:
            raise ValidationError(
                f"Invalid file type. Allowed types are: {', '.join(allowed_extensions)}"
            )

        return file_path, account_id

    @database_sync_to_async
    def save_single_transaction(self, transaction_data):
        """
        Save a single transaction to the database.

        Args:
            transaction_data: Dictionary containing transaction data

        Returns:
            dict: Result with 'success' boolean and optional 'error' message
        """
        from decimal import ROUND_HALF_UP
        from decimal import InvalidOperation as DecimalInvalidOperation

        def normalize_decimal_field(value, max_digits, decimal_places):
            """Normalize a Decimal value to fit database constraints."""
            try:
                original_value = Decimal(str(value))

                # Calculate how many integer digits we have
                abs_value = abs(original_value)
                if abs_value == 0:
                    int_digits = 1
                else:
                    int_digits = len(str(int(abs_value)))

                # Determine max decimal places we can use
                max_decimal_places = min(decimal_places, max_digits - int_digits)

                if max_decimal_places < 0:
                    logger.warning(
                        f"Value {original_value} too large for field "
                        f"(max_digits={max_digits}, needs {int_digits} integer digits)"
                    )
                    return Decimal("0")

                # Use quantize to properly set the decimal places
                quantizer = Decimal("0.1") ** max_decimal_places
                return original_value.quantize(quantizer, rounding=ROUND_HALF_UP)

            except (DecimalInvalidOperation, Exception) as e:
                logger.error(f"Error normalizing decimal: {e}")
                return Decimal("0")

        try:
            # Check if this is an FX transaction
            is_fx = transaction_data.pop("is_fx", False)

            # Check if this is an asset transfer
            is_asset_transfer = transaction_data.pop("is_asset_transfer", False)
            needs_price_calculation = transaction_data.pop("needs_price_calculation", False)

            if is_fx:
                # Normalize FX transaction decimal fields
                decimal_fields = [
                    "exchange_rate",
                    "from_amount",
                    "to_amount",
                    "commission",
                ]
                for field_name in decimal_fields:
                    if field_name in transaction_data and transaction_data[field_name] is not None:
                        field = FXTransaction._meta.get_field(field_name)
                        transaction_data[field_name] = normalize_decimal_field(
                            transaction_data[field_name],
                            field.max_digits,
                            field.decimal_places,
                        )

                fx_transaction = FXTransaction.objects.create(**transaction_data)
                logger.debug(f"Saved FX transaction with ID: {fx_transaction.id}")
                return {
                    "success": True,
                    "transaction_id": fx_transaction.id,
                    "type": "fx",
                }

            elif is_asset_transfer:
                # Handle asset transfer
                if needs_price_calculation and transaction_data.get("security"):
                    security = transaction_data["security"]
                    transfer_date = transaction_data["date"]
                    investor = transaction_data["investor"]
                    account = transaction_data["account"]

                    buy_in_price = security.calculate_buy_in_price(
                        date=transfer_date,
                        investor=investor,
                        account_ids=[account.id],
                    )

                    if buy_in_price:
                        transaction_data["price"] = buy_in_price
                    else:
                        try:
                            price_obj = (
                                security.prices.filter(date__lte=transfer_date)
                                .order_by("-date")
                                .first()
                            )
                            transaction_data["price"] = price_obj.price if price_obj else Decimal(0)
                        except Exception:
                            transaction_data["price"] = Decimal(0)

                transaction_data["cash_flow"] = None
                transaction_data["commission"] = None

                # Create main transaction
                created_transaction = Transactions.objects.create(**transaction_data)

                # Create phantom cash transaction
                if transaction_data.get("price") and transaction_data.get("quantity"):
                    transfer_value = abs(transaction_data["price"] * transaction_data["quantity"])
                    phantom_type = "Cash in" if transaction_data["type"] == "Buy" else "Cash out"
                    phantom_cash_flow = (
                        transfer_value if transaction_data["type"] == "Buy" else -transfer_value
                    )

                    Transactions.objects.create(
                        investor=transaction_data["investor"],
                        account=transaction_data["account"],
                        security=None,
                        date=transaction_data["date"],
                        type=phantom_type,
                        quantity=None,
                        price=None,
                        currency=transaction_data.get("currency"),
                        cash_flow=phantom_cash_flow,
                        commission=None,
                        comment=(
                            "Phantom cash movement for asset transfer: "
                            f"{transaction_data.get('security').name if transaction_data.get('security') else 'Unknown'}"  # noqa: E501
                        ),
                    )

                logger.debug(
                    "Saved asset transfer transaction with ID: " f"{created_transaction.id}"
                )
                return {
                    "success": True,
                    "transaction_id": created_transaction.id,
                    "type": "asset_transfer",
                }

            else:
                # Normalize regular transaction decimal fields
                decimal_fields = [
                    "quantity",
                    "price",
                    "notional",
                    "cash_flow",
                    "commission",
                    "aci",
                    "notional_change",
                ]
                for field_name in decimal_fields:
                    if field_name in transaction_data and transaction_data[field_name] is not None:
                        field = Transactions._meta.get_field(field_name)
                        transaction_data[field_name] = normalize_decimal_field(
                            transaction_data[field_name],
                            field.max_digits,
                            field.decimal_places,
                        )

                created_transaction = Transactions.objects.create(**transaction_data)

                # Create NotionalHistory for bond redemptions
                if created_transaction.type in [
                    TRANSACTION_TYPE_BOND_REDEMPTION,
                    TRANSACTION_TYPE_BOND_MATURITY,
                ]:
                    if (
                        created_transaction.security
                        and created_transaction.notional_change
                        and created_transaction.notional_change != 0
                    ):
                        try:
                            created_transaction._create_notional_history()
                            logger.debug(
                                "Created NotionalHistory for transaction "
                                f"{created_transaction.id}"
                            )
                        except Exception as e:
                            logger.error(
                                "Error creating NotionalHistory: " f"{e}",
                                exc_info=True,
                            )

                logger.debug(f"Saved regular transaction with ID: {created_transaction.id}")
                return {
                    "success": True,
                    "transaction_id": created_transaction.id,
                    "type": "regular",
                }

        except Exception as e:
            logger.error(f"Error saving single transaction: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    @database_sync_to_async
    def save_transactions(self, transactions_to_create):
        """
        Save transactions in bulk.

        Saves regular Transactions, FX Transactions, and Asset Transfers.

        :param transactions_to_create: List of transaction data to create
        """
        logger.debug(f"About to save {len(transactions_to_create)} transactions")

        # Log each transaction data for debugging
        for i, data in enumerate(transactions_to_create):
            logger.debug(f"Transaction {i + 1}: {data}")

            # Check for None values that might cause issues
            for key, value in data.items():
                if value is None and key in ["quantity", "price"]:
                    logger.warning(f"Transaction {i + 1} has None value for {key}")

        try:
            with transaction.atomic():
                regular_transactions = []
                fx_transactions = []
                phantom_cash_transactions = []

                for data in transactions_to_create:
                    logger.debug(f"Creating transaction with data: {data}")

                    # Check if this is an FX transaction
                    is_fx = data.pop("is_fx", False)

                    # Check if this is an asset transfer
                    is_asset_transfer = data.pop("is_asset_transfer", False)
                    needs_price_calculation = data.pop("needs_price_calculation", False)

                    if is_fx:
                        # Create FXTransaction - round exchange_rate to match DB precision  # noqa: E501
                        if "exchange_rate" in data and data["exchange_rate"] is not None:
                            # Get decimal_places from the model field dynamically
                            exchange_rate_field = FXTransaction._meta.get_field("exchange_rate")
                            decimal_places = exchange_rate_field.decimal_places
                            data["exchange_rate"] = round(
                                Decimal(str(data["exchange_rate"])), decimal_places
                            )
                        fx_transaction = FXTransaction(**data)
                        fx_transactions.append(fx_transaction)
                        logger.debug("Created FX transaction")
                    elif is_asset_transfer:
                        # Handle asset transfer
                        logger.debug(f"Processing asset transfer: {data['type']}")

                        # Calculate price if needed (use buy-in price or market price)
                        if needs_price_calculation and data.get("security"):
                            security = data["security"]
                            transfer_date = data["date"]
                            investor = data["investor"]
                            account = data["account"]

                            # Try to get buy-in price first
                            buy_in_price = security.calculate_buy_in_price(
                                date=transfer_date,
                                investor=investor,
                                account_ids=[account.id],
                            )

                            if buy_in_price:
                                data["price"] = buy_in_price
                                logger.debug(f"Using buy-in price: {buy_in_price}")
                            else:
                                # Fallback to current market price
                                try:
                                    price_obj = (
                                        security.prices.filter(date__lte=transfer_date)
                                        .order_by("-date")
                                        .first()
                                    )
                                    if price_obj:
                                        data["price"] = price_obj.price
                                        logger.debug(f"Using market price: {price_obj.price}")
                                    else:
                                        logger.warning("No price found for asset transfer, using 0")
                                        data["price"] = Decimal(0)
                                except Exception as e:
                                    logger.error(f"Error getting price for asset transfer: {e}")
                                    data["price"] = Decimal(0)

                        # Ensure cash_flow and commission are None for asset transfers
                        data["cash_flow"] = None
                        data["commission"] = None

                        # Create the main transaction
                        created_transaction = Transactions(**data)
                        regular_transactions.append(created_transaction)

                        # Create phantom cash transaction to balance the cash effect
                        if data.get("price") and data.get("quantity"):
                            transfer_value = abs(data["price"] * data["quantity"])

                            # For INPUT_SECURITIES (Buy): create Cash in (positive)
                            # For OUTPUT_SECURITIES (Sell): create Cash out (negative)
                            if data["type"] == "Buy":  # INPUT_SECURITIES
                                phantom_type = "Cash in"
                                phantom_cash_flow = transfer_value
                            else:  # Sell - OUTPUT_SECURITIES
                                phantom_type = "Cash out"
                                phantom_cash_flow = -transfer_value

                            phantom_transaction = Transactions(
                                investor=data["investor"],
                                account=data["account"],
                                security=None,
                                date=data["date"],
                                type=phantom_type,
                                quantity=None,
                                price=None,
                                currency=data.get("currency"),
                                cash_flow=phantom_cash_flow,
                                commission=None,
                                comment=(
                                    f"Phantom cash movement for asset transfer: "
                                    f"{data.get('security').name if data.get('security') else 'Unknown'}"  # noqa: E501
                                ),
                            )
                            phantom_cash_transactions.append(phantom_transaction)
                            logger.debug(
                                f"Created phantom {phantom_type} transaction with "
                                f"cash_flow: "
                                f"{phantom_cash_flow}"
                            )
                    else:
                        # Create regular Transaction
                        created_transaction = Transactions(**data)
                        regular_transactions.append(created_transaction)

                # Use bulk_create for efficiency
                if regular_transactions:
                    created_transactions = Transactions.objects.bulk_create(regular_transactions)
                    logger.debug(
                        f"Successfully saved {len(regular_transactions)} " "regular transactions"
                    )

                    # Manually create NotionalHistory for bond redemptions
                    # (bulk_create bypasses save())
                    for txn in created_transactions:
                        if txn.type in [
                            TRANSACTION_TYPE_BOND_REDEMPTION,
                            TRANSACTION_TYPE_BOND_MATURITY,
                        ]:
                            if txn.security and txn.notional_change and txn.notional_change != 0:
                                try:
                                    txn._create_notional_history()
                                    logger.debug(
                                        f"Created NotionalHistory for transaction "
                                        f"{txn.id}: "
                                        f"{txn.security.name}"
                                    )
                                except Exception as e:
                                    logger.error(
                                        "Error creating NotionalHistory "
                                        f"for transaction {txn.id}: {e}",
                                        exc_info=True,
                                    )

                if fx_transactions:
                    FXTransaction.objects.bulk_create(fx_transactions)
                    logger.debug(f"Successfully saved {len(fx_transactions)} FX transactions")

                if phantom_cash_transactions:
                    Transactions.objects.bulk_create(phantom_cash_transactions)
                    logger.debug(
                        f"Successfully saved {len(phantom_cash_transactions)} "
                        "phantom cash transactions"
                    )

                transactions_saved = (
                    len(regular_transactions)
                    + len(fx_transactions)
                    + len(phantom_cash_transactions)
                )
                logger.debug(f"Total transactions saved: " f"{transactions_saved}")

        except Exception as e:
            logger.error(f"Error saving transactions: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def import_transactions_from_api(
        self, user, broker_account_id, confirm_every, date_from=None, date_to=None
    ):
        """Import transactions from broker API."""
        logger.debug("Starting API import")
        broker_api = None

        try:
            # Get account and validate
            account = await get_account(broker_account_id)
            if not account:
                yield {
                    "status": "critical_error",
                    "message": "Invalid broker account ID",
                }
                return

            # Get broker asynchronously
            broker = await get_broker(account)
            if not broker:
                yield {"status": "critical_error", "message": "Invalid broker"}
                return

            # Set default date range if not provided
            if not date_from:
                date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            if not date_to:
                date_to = datetime.now().strftime("%Y-%m-%d")

            # Get appropriate broker API handler
            broker_api = await get_broker_api(broker)
            if not broker_api:
                yield {
                    "status": "critical_error",
                    "message": f"Unsupported broker API: {broker.name}",
                }
                return

            # Initialize broker API connection
            yield {
                "status": "initialization",
                "message": "Connecting to broker API...",
            }

            # Connect to broker API
            try:
                connected = await broker_api.connect(user)
                if not connected:
                    yield {
                        "status": "critical_error",
                        "message": "Failed to connect to broker API",
                    }
                    return

                # For T-Bank API, ensure account native IDs are synchronized
                if broker.name.lower() == "tinkoff" or "тинькофф" in broker.name.lower():
                    yield {
                        "status": "progress",
                        "message": "Fetching transactions from T-Bank...",
                    }
                    await ensure_account_native_ids(user, broker_api)

                    # Refetch account to get updated native_id
                    account = await get_account(broker_account_id)
                    if not account.native_id:
                        yield {
                            "status": "critical_error",
                            "message": (
                                f"Could not find matching T-Bank account ID for "
                                f"{account.name}. "
                                "Please check account names "
                                "match exactly with those in T-Bank."
                            ),
                        }
                        return

            except TinkoffAPIException as e:
                yield {
                    "status": "critical_error",
                    "message": f"Broker API connection error: {str(e)}",
                }
                return

            # First, get total count of transactions
            try:
                # Fetch all transactions to get accurate count
                all_transactions = []
                async for trans in broker_api.get_transactions(
                    account=account, date_from=date_from, date_to=date_to
                ):
                    all_transactions.append(trans)

                # Yield total count upfront
                total_count = len(all_transactions)
                yield {
                    "status": "total_count",
                    "total": total_count,
                    "message": f"Found {total_count} transactions to process",
                }

                # Now process each transaction
                current_index = 0
                for trans in all_transactions:
                    current_index += 1

                    # Yield progress update
                    yield {
                        "status": "progress",
                        "current": current_index,
                        "total": total_count,
                        "message": (f"Processing transaction {current_index} of " f"{total_count}"),
                    }

                    if trans.get("unrecognized_operation"):
                        yield {
                            "status": "unrecognized_operation",
                            "transaction_data": trans.get("data"),
                        }
                        continue

                    try:
                        # Check if this is an FX transaction
                        is_fx = trans.get("is_fx", False)

                        if is_fx:
                            logger.info(
                                "Processing FX transaction: "
                                f"{trans.get('from_currency')} -> "
                                f" -> {trans.get('to_currency')}"
                            )
                            # Format FX transaction data
                            transaction_data = {
                                "is_fx": True,
                                "date": trans["date"],
                                "from_currency": trans.get("from_currency"),
                                "to_currency": trans.get("to_currency"),
                                "from_amount": trans.get("from_amount"),
                                "to_amount": trans.get("to_amount"),
                                "exchange_rate": trans.get("exchange_rate"),
                                "commission": trans.get("commission"),
                                "commission_currency": trans.get("commission_currency"),
                                "comment": trans.get("comment", ""),
                                "account": account,
                                "investor": user,
                            }
                        else:
                            # Format regular transaction data
                            transaction_data = {
                                "date": trans["date"],
                                "type": trans["type"],
                                "security": trans.get("security"),
                                "quantity": trans.get("quantity"),
                                "price": trans.get("price"),
                                "notional": trans.get("notional"),
                                "currency": trans.get("currency"),
                                "cash_flow": trans.get("cash_flow"),
                                "commission": trans.get("commission"),
                                "aci": trans.get("aci"),
                                "notional_change": trans.get("notional_change"),
                                "comment": trans.get("comment", ""),
                                "account": account,
                                "investor": user,
                            }

                            # For bond redemptions, calculate per-bond notional_change
                            if trans["type"] in ["Bond redemption", "Bond maturity"]:
                                total_notional = trans.get("notional_change")
                                security = trans.get("security")

                                if total_notional and security:
                                    # Get position at redemption date to calculate per-bond notional  # noqa: E501
                                    try:
                                        # Get position BEFORE this transaction
                                        position = await database_sync_to_async(security.position)(
                                            trans["date"], user, [account.id]
                                        )

                                        if position and position != 0:
                                            # Calculate per-bond notional
                                            notional_per_bond = Decimal(total_notional) / abs(
                                                Decimal(position)
                                            )
                                            transaction_data["notional_change"] = notional_per_bond

                                            logger.debug(
                                                "Bond redemption: total="
                                                f"{total_notional}, "
                                                f"position={position}, per_bond="
                                                f"{notional_per_bond}"
                                            )
                                        else:
                                            logger.warning(
                                                f"Position is 0 for {security.name} on "
                                                f"{trans['date']}, "
                                                f"keeping total notional_change="
                                                f"{total_notional}"
                                            )
                                    except Exception as e:
                                        logger.error(
                                            f"Error calculating per-bond notional: {e}",
                                            exc_info=True,
                                        )

                        # Process transaction based on status
                        if not is_fx:
                            # Security mapping only applies to regular transactions
                            if trans.get("needs_security_mapping"):
                                yield {
                                    "status": "security_mapping",
                                    "mapping_data": {
                                        "security_description": trans["security_description"],
                                        "isin": trans.get("isin"),
                                        "symbol": trans.get("symbol"),
                                    },
                                    "transaction_data": transaction_data,
                                }
                                continue

                            # Check for duplicates for regular transactions
                            exists = await transaction_exists(transaction_data)
                            if exists:
                                logger.debug("Duplicate regular transaction found, skipping")
                                yield {
                                    "status": "duplicate_transaction",
                                    "data": transaction_data,
                                }
                                continue
                        else:
                            # Check for duplicates for FX transactionss
                            existing_fx = await fx_transaction_exists(transaction_data)
                            if existing_fx:
                                logger.debug("Duplicate FX transaction found, skipping")
                                yield {
                                    "status": "duplicate_transaction",
                                    "data": transaction_data,
                                }
                                continue

                        # Handle confirmation if needed
                        if confirm_every:
                            yield {
                                "status": "transaction_confirmation",
                                "data": transaction_data,
                            }
                            continue

                        # Save transaction immediately
                        # (instead of collecting for bulk save)
                        yield {"status": "save_transaction", "data": transaction_data}

                    except Exception as e:
                        logger.error(f"Error processing transaction: {str(e)}", exc_info=True)
                        yield {
                            "status": "transaction_error",
                            "message": f"Error processing transaction: {str(e)}",
                            "error_detail": str(e),
                        }

            except TinkoffAPIException as e:
                yield {
                    "status": "critical_error",
                    "message": f"Error fetching transactions: {str(e)}",
                }
                return

            # Signal completion (stats are tracked in consumers.py)
            yield {"status": "processing_complete"}

        except Exception as e:
            logger.error(f"Error in API import: {str(e)}", exc_info=True)
            yield {
                "status": "critical_error",
                "message": f"An error occurred during API import: {str(e)}",
            }
        finally:
            # Ensure broker API is disconnected
            if broker_api:
                await broker_api.disconnect()


class FXTransactionViewSet(viewsets.ModelViewSet):
    """FX transaction view set."""

    serializer_class = FXTransactionFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get the queryset for the FX transaction view set."""
        return FXTransaction.objects.filter(investor=self.request.user)

    def perform_create(self, serializer):
        """Perform create action."""
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=["POST"])
    def create_fx_transaction(self, request):
        """Create a new FX transaction."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
                headers=self.get_success_headers(serializer.data),
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        """Get the form structure for the FX transaction."""
        form_serializer = FXTransactionFormSerializer()

        return Response(
            {
                "fields": [
                    {
                        "name": "date",
                        "label": "Date",
                        "type": "datepicker",
                        "required": True,
                    },
                    {
                        "name": "account",
                        "label": "Broker Account",
                        "type": "select",
                        "required": True,
                        "choices": form_serializer.get_account_choices(request.user),
                    },
                    {
                        "name": "from_currency",
                        "label": "From Currency",
                        "type": "select",
                        "required": True,
                        "choices": form_serializer.get_currency_choices(),
                    },
                    {
                        "name": "from_amount",
                        "label": "From Amount",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "name": "to_currency",
                        "label": "To Currency",
                        "type": "select",
                        "required": True,
                        "choices": form_serializer.get_currency_choices(),
                    },
                    {
                        "name": "to_amount",
                        "label": "To Amount",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "name": "commission_currency",
                        "label": "Commission Currency",
                        "type": "select",
                        "required": False,
                        "choices": form_serializer.get_currency_choices(),
                    },
                    {
                        "name": "commission",
                        "label": "Commission",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "comment",
                        "label": "Comment",
                        "type": "textarea",
                        "required": False,
                    },
                ]
            }
        )
