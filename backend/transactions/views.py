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
)
from services.broker_api import BrokerAPIException, TinkoffAPIException, get_broker_api
from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
from services.importer import (
    fx_transaction_exists,
    get_account,
    get_broker,
    parse_charles_stanley_transactions,
    parse_galaxy_account_cash_flows,
    parse_galaxy_account_security_transactions,
    transaction_exists,
)
from core.transactions_utils import get_transactions_table_api
from services.corporate_actions import (
    CorporateActionError,
    execute_transfer,
)
from services.positions import position as _positions_position
from services.transactions import (
    save_single_transaction as services_transactions_save_single,
    save_transactions as services_transactions_save_bulk,
)

from .serializers import FXTransactionFormSerializer, TransactionFormSerializer

logger = logging.getLogger(__name__)


def _format_partial_failures(broker_api):
    """Return a list of ``{endpoint, error}`` dicts for the frontend.

    ``BybitAPI`` / ``OKXAPI`` collect per-endpoint failures in
    ``self.partial_failures`` (a list of ``(endpoint_name, error_message)``
    tuples) as their ``_safe`` wrapper catches ``CryptoExchangeAPIError``
    around each per-endpoint iterator. Without this, an endpoint error (e.g.
    OKX ``bills-archive`` rejecting a 4-year window) is indistinguishable from
    a genuine "no data" result, so the user sees identical empty UX whether
    the endpoint failed or simply had nothing.

    Returns ``[]`` for brokers without partial-failure tracking (e.g.
    Tinkoff) so the consumer can unconditionally forward this list.
    """
    failures = getattr(broker_api, "partial_failures", None) or []
    return [{"endpoint": name, "error": message} for name, message in failures]


@database_sync_to_async
def ensure_account_native_ids(user, broker_api):
    """
    Ensure that all Tinkoff accounts have their native_id set properly.

    :param user: The user whose accounts should be synchronized
    :param broker_api: An instance of the TinkoffAPI class
    :return: A dictionary mapping Tinkoff account IDs to Accounts model instances
    """
    from t_tech.invest import Client

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
                        "name": "split_from",
                        "label": "Split From",
                        "type": "number",
                        "required": False,
                        "helper_text": "Shares before split (e.g., 1 for a 2:1 split)",
                        "show_for_types": ["Stock split"],
                    },
                    {
                        "name": "split_to",
                        "label": "Split To",
                        "type": "number",
                        "required": False,
                        "helper_text": "Shares after split (e.g., 2 for a 2:1 split)",
                        "show_for_types": ["Stock split"],
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
                account = self._find_account_by_name(user, account_name)
                if account:
                    logger.info(
                        f"Returning perfectly matched account: {account.name} "
                        f"(ID: {account.id})"
                    )
                    return account
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
            logger.info(
                f"Best match found: {best_match} with average score {best_score}"
            )
            account = self._find_account_by_name(user, best_match)
            if account:
                logger.info(
                    f"Returning best matched account: {account.name} "
                    f"(ID: {account.id})"
                )
                return account
            logger.warning(
                f"Best match {best_match} found, "
                "but no corresponding Account object exists for this user"
            )
            return None

        logger.info("No broker account match found")
        return None

    def _find_account_by_name(self, user, account_name):
        """Find an account for a user by name, trying exact then fuzzy match.

        Args:
            user: The user instance.
            account_name: The account name to search for.

        Returns:
            Accounts instance or None.
        """
        # Try exact case-insensitive match first
        try:
            return Accounts.objects.get(
                broker__investor=user, name__iexact=account_name
            )
        except Accounts.DoesNotExist:
            pass

        # Fuzzy match: score each account and pick the best one
        accounts = Accounts.objects.filter(broker__investor=user)
        best_account = None
        best_score = 0

        for account in accounts:
            score = fuzz.partial_ratio(
                account.name.lower(), account_name.lower()
            )
            logger.debug(
                f"Account name match: '{account.name}' vs '{account_name}' "
                f"= {score}"
            )
            # Prefer longer (more specific) names when scores tie
            if score > best_score or (
                score == best_score
                and best_account
                and len(account.name) > len(best_account.name)
            ):
                best_score = score
                best_account = account

        if best_account and best_score >= 70:
            return best_account

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
            position = _positions_position(
                security, date=position_date, investor=request.user, account_ids=[account_id]
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

        The business logic lives in
        :func:`services.corporate_actions.execute_transfer`; this action is a
        thin orchestrator that parses the request and shapes the response.

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

            result = execute_transfer(
                investor=request.user,
                security_id=security_id,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                quantity=quantity,
                transfer_date=transfer_date,
            )
            return Response(result, status=status.HTTP_201_CREATED)

        except CorporateActionError as exc:
            return Response({"error": exc.message}, status=exc.status_code)
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

        Thin wrapper that delegates the 3-way branch (FX / asset-transfer /
        regular), Decimal normalization, object creation, phantom cash flow,
        and NotionalHistory creation to
        :func:`services.transactions.save_single_transaction`.

        Args:
            transaction_data: Dictionary containing transaction data

        Returns:
            dict: Result with 'success' boolean and optional 'error' message
        """
        return services_transactions_save_single(transaction_data)

    @database_sync_to_async
    def save_transactions(self, transactions_to_create):
        """
        Save transactions in bulk.

        Thin wrapper that delegates the bulk partition (regular / FX /
        phantom-cash), buy-in/market price recomputation, ``bulk_create``, and
        bond-redemption NotionalHistory creation to
        :func:`services.transactions.save_transactions`.

        :param transactions_to_create: List of transaction data to create
        """
        services_transactions_save_bulk(transactions_to_create)

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

            except (TinkoffAPIException, BrokerAPIException) as e:
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

                    if isinstance(trans, CryptoExchangeEvent):
                        # Crypto exchange events produce multiple canonical legs and handle
                        # idempotency internally, so they persist immediately regardless of
                        # confirm_every.
                        try:
                            created = await database_sync_to_async(
                                persist_crypto_exchange_event
                            )(
                                trans,
                                user,
                                account,
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing crypto exchange event: {str(e)}",
                                exc_info=True,
                            )
                            yield {
                                "status": "transaction_error",
                                "message": (
                                    "Error processing crypto exchange event: "
                                    f"{str(e)}"
                                ),
                                "error_detail": str(e),
                            }
                            continue
                        yield {
                            "status": "transaction_saved",
                            "message": f"Saved {len(created)} crypto transaction legs",
                            "transaction": {
                                "import_group_id": trans.group_id,
                                "count": len(created),
                            },
                        }
                        continue

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
                                            notional_per_bond = Decimal(
                                                total_notional
                                            ) / abs(Decimal(position))
                                            transaction_data["notional_change"] = (
                                                notional_per_bond
                                            )

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

            except (TinkoffAPIException, BrokerAPIException) as e:
                yield {
                    "status": "critical_error",
                    "message": f"Error fetching transactions: {str(e)}",
                }
                return

            # Signal completion (stats are tracked in consumers.py)
            yield {
                "status": "processing_complete",
                "partial_failures": _format_partial_failures(broker_api),
            }

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
