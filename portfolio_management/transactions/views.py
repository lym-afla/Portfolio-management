import logging
import os
import re
import uuid
from datetime import datetime, timedelta

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

from common.models import Accounts, FXTransaction, Transactions
from constants import ACCOUNT_IDENTIFIERS, CHARLES_STANLEY_BROKER, CURRENCY_CHOICES
from core.broker_api_utils import TinkoffAPIException, get_broker_api
from core.import_utils import (
    get_account,
    parse_charles_stanley_transactions,
    parse_galaxy_account_cash_flows,
    parse_galaxy_account_security_transactions,
    transaction_exists,
)
from core.transactions_utils import get_transactions_table_api

from .serializers import FXTransactionFormSerializer, TransactionFormSerializer

logger = logging.getLogger(__name__)


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transactions.objects.filter(investor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    def get_object(self):
        transaction_id = self.kwargs.get("pk")
        try:
            return Transactions.objects.get(id=transaction_id, investor=self.request.user)
        except Transactions.DoesNotExist:
            raise NotFound(f"Transaction with id {transaction_id} not found.")

    @action(detail=False, methods=["POST"])
    def get_transactions_table(self, request):
        return Response(get_transactions_table_api(request))

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
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
                            {"value": currency[0], "text": f"{currency[1]} ({currency[0]})"}
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
                    },
                    {
                        "name": "cash_flow",
                        "label": "Cash Flow",
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
        df = pd.read_excel(file_path)
        content = df.to_string().lower()
        return content

    def identify_account(self, content, user):
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
                    # Get the surrounding context (50 characters before and after the match)
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
                    f"Perfect match found for all keywords of broker account {account_name}"
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
                    f"Returning best matched broker account: {account.name} (ID: {account.id})"
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

    async def import_transactions_from_file(
        self, user, file_id, account_id, confirm_every, currency, is_galaxy, galaxy_type
    ):
        logger.debug("Starting import_transactions")
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
        """Validate import data"""
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
    def save_transactions(self, transactions_to_create):
        """Save transactions in bulk"""
        with transaction.atomic():
            Transactions.objects.bulk_create(
                [Transactions(**data) for data in transactions_to_create]
            )

    async def import_transactions_from_api(
        self, user, broker_account_id, confirm_every, date_from=None, date_to=None
    ):
        """Import transactions from broker API"""
        logger.debug("Starting API import")
        broker_api = None

        try:
            # Get account and validate
            account = await get_account(broker_account_id)
            if not account:
                yield {"status": "critical_error", "message": "Invalid broker account ID"}
                return

            # Set default date range if not provided
            if not date_from:
                date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            if not date_to:
                date_to = datetime.now().strftime("%Y-%m-%d")

            # Initialize stats
            stats = {
                "totalTransactions": 0,
                "importedTransactions": 0,
                "skippedTransactions": 0,
                "duplicateTransactions": 0,
                "importErrors": 0,
            }

            # Get appropriate broker API handler
            broker_api = await get_broker_api(account.broker)
            if not broker_api:
                yield {
                    "status": "critical_error",
                    "message": f"Unsupported broker API: {account.broker.name}",
                }
                return

            # Initialize broker API connection
            yield {"status": "initialization", "message": "Connecting to broker API..."}

            # Connect to broker API
            try:
                connected = await broker_api.connect(user)
                if not connected:
                    yield {"status": "critical_error", "message": "Failed to connect to broker API"}
                    return
            except TinkoffAPIException as e:
                yield {
                    "status": "critical_error",
                    "message": f"Broker API connection error: {str(e)}",
                }
                return

            # Fetch transactions from broker API
            try:
                async for trans in broker_api.get_transactions(
                    account=account, date_from=date_from, date_to=date_to
                ):
                    stats["totalTransactions"] += 1

                    try:
                        # Format transaction data
                        transaction_data = {
                            "date": trans["date"],
                            "type": trans["type"],
                            "security": trans.get("security"),
                            "quantity": trans.get("quantity"),
                            "price": trans.get("price"),
                            "currency": trans.get("currency"),
                            "cash_flow": trans.get("cash_flow"),
                            "commission": trans.get("commission"),
                            "account": account,
                            "investor": user,
                        }

                        # Process transaction based on status
                        if trans.get("needs_security_mapping"):
                            yield {
                                "status": "security_mapping",
                                "mapping_data": {
                                    "stock_description": trans["security_description"],
                                    "isin": trans.get("isin"),
                                    "symbol": trans.get("symbol"),
                                },
                                "transaction_data": transaction_data,
                            }
                            continue

                        # Check for duplicates
                        existing_transaction = await transaction_exists(transaction_data)
                        if existing_transaction:
                            stats["duplicateTransactions"] += 1
                            continue

                        # Handle confirmation if needed
                        if confirm_every:
                            yield {"status": "transaction_confirmation", "data": transaction_data}
                            continue

                        # Add transaction
                        yield {"status": "add_transaction", "data": transaction_data}
                        stats["importedTransactions"] += 1

                    except Exception as e:
                        logger.error(f"Error processing transaction: {str(e)}")
                        stats["importErrors"] += 1
                        yield {
                            "status": "progress",
                            "message": f"Error processing transaction: {str(e)}",
                        }

            except TinkoffAPIException as e:
                yield {
                    "status": "critical_error",
                    "message": f"Error fetching transactions: {str(e)}",
                }
                return

            # Return final stats
            yield {"status": "complete", "data": stats}

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
    serializer_class = FXTransactionFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FXTransaction.objects.filter(investor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=["POST"])
    def create_fx_transaction(self, request):
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
