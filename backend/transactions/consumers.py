"""Transactions consumers."""

import asyncio
import datetime
import json
import logging
from collections import defaultdict
from decimal import Decimal

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.forms import model_to_dict

from common.models import Accounts, Assets, Brokers
from core.formatting_utils import format_table_data
from core.import_utils import (
    fx_transaction_exists,
    get_security,
    match_tinkoff_broker_account,
    transaction_exists,
)
from users.models import CustomUser

from .views import TransactionViewSet

logger = logging.getLogger(__name__)

User = get_user_model()


class TransactionConsumer(AsyncWebsocketConsumer):
    """Transaction consumer."""

    def __init__(self, *args, **kwargs):
        """Initialize the transaction consumer."""
        super().__init__(*args, **kwargs)
        # Initialize queues to handle confirmations and mappings
        self.confirmation_events = asyncio.Queue()
        self.mapping_events = asyncio.Queue()
        self.security_events = asyncio.Queue()
        self.stop_event = asyncio.Event()
        self.import_task = None  # Track the import task
        self.view_set = TransactionViewSet()  # Initialize your view set
        self.confirm_every = False
        self.transactions_to_create = []
        self.transactions_skipped = 0
        self.duplicate_count = 0

    async def connect(self):
        """Connect to the WebSocket."""
        # Get the authenticated user from the scope
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            # Reject the connection if user is not authenticated
            await self.close()
            return

        await self.accept()
        logger.info(f"WebSocket connected for user: {self.user}")

    async def disconnect(self, close_code):
        """Disconnect from the WebSocket."""
        logger.info(f"WebSocket disconnected with code: {close_code}")
        self.stop_event.set()
        logger.debug("WebSocket connection closed")
        if self.import_task and not self.import_task.done():
            self.import_task.cancel()
            try:
                await self.import_task
            except asyncio.CancelledError:
                logger.debug("Import task cancelled upon disconnect")

    async def receive(self, text_data):
        """Receive a message from the WebSocket."""
        logger.debug(f"Raw WebSocket message received: {text_data}")
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json["type"]
            logger.debug(
                f"Processing message type: {message_type} with data: {text_data_json}"
            )

            if message_type == "start_file_import":  # Renamed from 'start_import'
                file_id = text_data_json.get("file_id")
                account_id = text_data_json.get("account_id")
                confirm_every = text_data_json.get("confirm_every", False)
                is_galaxy = text_data_json.get("is_galaxy", False)
                galaxy_type = text_data_json.get("galaxy_type", None)
                currency = text_data_json.get("currency", None)

                if not self.import_task or self.import_task.done():
                    self.import_task = asyncio.create_task(
                        self.start_file_import(  # Renamed method
                            file_id,
                            account_id,
                            confirm_every,
                            currency,
                            is_galaxy,
                            galaxy_type,
                        )
                    )
                    logger.debug("Started file import task")
                else:
                    logger.warning("Import task already running")
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_warning",
                                "data": {"message": "Import already in progress"},
                            }
                        )
                    )

            elif message_type == "start_api_import":
                data = text_data_json.get("data", {})
                broker_id = data.get("broker_id")

                if not broker_id:
                    await self.send_error("Broker ID is required")
                    return

                if not self.import_task or self.import_task.done():
                    self.import_task = asyncio.create_task(
                        self.start_api_import(
                            broker_id=broker_id,
                            confirm_every=data.get("confirm_every_transaction", False),
                            date_from=data.get("date_from"),
                            date_to=data.get("date_to"),
                        )
                    )
                    logger.debug("Started API import task")
                else:
                    logger.warning("Import task already running")
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_warning",
                                "data": {"message": "Import already in progress"},
                            }
                        )
                    )

            elif message_type == "security_mapped":
                action = text_data_json.get("action")
                security_id = text_data_json.get("security_id", None)
                mapping_response = {"action": action, "security_id": security_id}
                await self.mapping_events.put(mapping_response)
                logger.debug(f"Put mapping event: {mapping_response}")
            elif message_type == "transaction_confirmed":
                confirmed = text_data_json.get("confirmed", False)
                await self.confirmation_events.put(confirmed)
                logger.debug(
                    f"Put confirmation event: {confirmed}. "
                    f"Queue size: {self.confirmation_events.qsize()}"
                )
            elif message_type == "security_confirmation":
                # Clear any pending security events before adding new one
                while not self.security_events.empty():
                    try:
                        self.security_events.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                security_id = text_data_json.get("security_id")
                logger.debug(
                    f"Security confirmation received. ID: {security_id}, "
                    f"Queue size before: {self.security_events.qsize()}"
                )
                await self.security_events.put(security_id)
                logger.debug(
                    "Security confirmation queued. Queue size after: "
                    f"{self.security_events.qsize()}"
                )
            elif message_type == "stop_import":
                self.stop_event.set()
                logger.debug("Stop event set for import")
                self.transactions_to_create = []
                self.transactions_skipped = 0
                self.duplicate_count = 0

                # Send stop confirmation to frontend
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "import_stopped",
                            "data": {
                                "message": "Import process was stopped by user",
                                "stats": {
                                    "totalTransactions": 0,
                                    "importedTransactions": 0,
                                    "skippedTransactions": self.transactions_skipped,
                                    "duplicateTransactions": self.duplicate_count,
                                    "importErrors": 0,
                                },
                            },
                        }
                    )
                )

                # Close the WebSocket connection
                await self.close()

            elif message_type == "accounts_matched":
                # Handle the account matching response from frontend
                data = text_data_json.get("data", {})
                pairs = data.get("pairs", [])

                if not pairs:
                    await self.send_error("No account pairs provided")
                    return

                # Get broker_id from the stored task or data
                broker_id = getattr(self, "current_broker_id", None)
                if not broker_id:
                    await self.send_error(
                        "Broker ID not found. Please restart the import process."
                    )
                    return

                # Process the matched accounts and start importing transactions
                logger.debug(f"Starting API import with {len(pairs)} account pairs")

                # Create a new task for importing transactions
                if not self.import_task or self.import_task.done():
                    self.import_task = asyncio.create_task(
                        self.process_account_matches(broker_id, pairs)
                    )
                else:
                    logger.warning("Import task already running")
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_warning",
                                "data": {"message": "Import already in progress"},
                            }
                        )
                    )

            elif message_type == "use_existing_matches":
                # Handle the request to use existing matches from frontend
                data = text_data_json.get("data", {})
                pairs = data.get("pairs", [])

                logger.debug(f"Received use_existing_matches with pairs: {pairs}")

                if not pairs:
                    logger.error("No existing pairs provided in use_existing_matches")
                    await self.send_error("No existing pairs provided")
                    return

                # Get broker_id from the stored task or data
                broker_id = getattr(self, "current_broker_id", None)
                if not broker_id:
                    logger.error("Broker ID not found in use_existing_matches")
                    await self.send_error(
                        "Broker ID not found. Please restart the import process."
                    )
                    return

                # Process the matched accounts and start importing transactions
                logger.debug(f"Using existing matches with {len(pairs)} account pairs")

                # Create a new task for importing transactions with existing matches
                if not self.import_task or self.import_task.done():
                    logger.debug(f"Starting import task with pairs: {pairs}")
                    self.import_task = asyncio.create_task(
                        self.process_account_matches(broker_id, pairs)
                    )
                else:
                    logger.warning("Import task already running")
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_warning",
                                "data": {"message": "Import already in progress"},
                            }
                        )
                    )

            elif message_type == "create_account":
                # Handle the create account request from frontend
                data = text_data_json.get("data", {})
                tinkoff_account = data.get("tinkoff_account")
                name = data.get("name")
                comment = data.get("comment", "")

                if not tinkoff_account or not name:
                    await self.send_error("Tinkoff account and name are required")
                    return

                # Get broker_id from the stored task or data
                broker_id = getattr(self, "current_broker_id", None)
                if not broker_id:
                    await self.send_error(
                        "Broker ID not found. Please restart the import process."
                    )
                    return

                # Create a new task for creating account and importing transactions
                if not self.import_task or self.import_task.done():
                    self.import_task = asyncio.create_task(
                        self.create_account_and_import(
                            broker_id=broker_id,
                            tinkoff_account=tinkoff_account,
                            name=name,
                            comment=comment,
                        )
                    )
                else:
                    logger.warning("Import task already running")
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_warning",
                                "data": {"message": "Import already in progress"},
                            }
                        )
                    )

            else:
                logger.warning(f"Unhandled message type: {message_type}")

        except json.JSONDecodeError:
            logger.error("Failed to decode JSON message")
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "Invalid JSON data received"}
                )
            )
        except KeyError as e:
            logger.error(f"Missing required key in message: {str(e)}")
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": f"Missing required data: {str(e)}"}
                )
            )
        except Exception as e:
            logger.error(f"Error handling receive: {str(e)}", exc_info=True)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "data": {"message": f"An error occurred: {str(e)}"},
                    }
                )
            )

    async def start_file_import(
        self,
        file_id,
        account_id,
        confirm_every,
        currency,
        is_galaxy,
        galaxy_type,
    ):
        """Start the file import."""
        logger.debug("Starting file import")
        try:
            self.confirm_every = confirm_every
            self.import_generator = self.view_set.import_transactions_from_file(
                self.user,
                file_id,
                account_id,
                confirm_every,
                currency,
                is_galaxy,
                galaxy_type,
            )
            await self.process_import()
        except Exception as e:
            logger.error(f"Error in file import: {str(e)}")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "import_error",
                        "data": {
                            "error": f"An error occurred during file import: {str(e)}"
                        },
                    }
                )
            )

    async def send_error(self, message: str, error_type: str = "critical_error"):
        """
        Send error message to client.

        Args:
            message: Error message
            error_type: Type of error ('critical_error', 'import_error', 'save_error')
        """
        await self.send(
            text_data=json.dumps({"type": error_type, "data": {"error": message}})
        )

    async def send_message(self, message_type: str, data: dict):
        """
        Send formatted message to client.

        Args:
            message_type: Type of message
            data: Message data
        """
        await self.send(text_data=json.dumps({"type": message_type, "data": data}))

    async def start_api_import(
        self,
        broker_id: int,
        confirm_every: bool = False,
        date_from: str = None,
        date_to: str = None,
    ):
        """Handle API import process."""
        try:
            # Store broker_id for later use in accounts_matched handler
            self.current_broker_id = broker_id
            self.confirm_every = confirm_every
            self.date_from = date_from
            self.date_to = date_to

            # Get broker instance
            broker = await database_sync_to_async(Brokers.objects.get)(id=broker_id)

            # Get matched and unmatched accounts
            matched_pairs, unmatched_tinkoff, unmatched_db = (
                await match_tinkoff_broker_account(broker, self.user)
            )

            # Send account matching data to frontend
            await self.send_message(
                "account_matching_required",
                {
                    "broker_id": broker_id,
                    "broker_name": broker.name,
                    "matched_pairs": matched_pairs,
                    "unmatched_tinkoff": unmatched_tinkoff,
                    "unmatched_db": unmatched_db,
                    "message": (
                        "Please confirm account matches and match remaining accounts"
                    ),
                },
            )

        except Brokers.DoesNotExist:
            await self.send_error("Invalid broker ID")
        except Exception as e:
            logger.error(f"Error in start_api_import: {str(e)}")
            await self.send_error(f"Failed to start API import: {str(e)}")

    async def process_account_matches(self, broker_id: int, pairs: list):
        """
        Process the account matches and start importing transactions.

        :param broker_id: ID of the broker
        :param pairs: List of dicts with tinkoff_account_id and db_account_id
        """
        try:
            logger.debug(
                f"Processing {len(pairs)} account matches for broker ID {broker_id}"
            )

            # Send progress update
            await self.send_message(
                "import_update",
                {
                    "status": "progress",
                    "message": f"Starting import for {len(pairs)} account pairs",
                    "progress": 0,
                },
            )

            # Initialize statistics
            total_imported = 0
            total_skipped = 0
            total_duplicates = 0
            total_errors = 0

            # Process each account pair
            for i, pair in enumerate(pairs):
                tinkoff_account_id = pair.get("tinkoff_account_id")
                db_account_id = pair.get("db_account_id")

                if not tinkoff_account_id or not db_account_id:
                    logger.warning(f"Skipping invalid pair: {pair}")
                    continue

                # Update native_id in the database account
                try:

                    @database_sync_to_async
                    def update_account_native_id(db_account_id, tinkoff_account_id):
                        try:
                            account = Accounts.objects.get(id=db_account_id)
                            account.native_id = tinkoff_account_id
                            account.save(update_fields=["native_id"])
                            logger.info(
                                f"Updated native_id for account {account.name} "
                                f"(ID: {account.id})"
                                f" to {tinkoff_account_id}"
                            )
                            return account
                        except Accounts.DoesNotExist:
                            logger.error(f"Account with ID {db_account_id} not found")
                            return None

                    # Update native_id
                    account = await update_account_native_id(
                        db_account_id, tinkoff_account_id
                    )
                    if not account:
                        logger.error(
                            f"Failed to update native_id for account ID {db_account_id}"
                        )
                        continue
                except Exception as e:
                    logger.error(
                        f"Error updating native_id for account ID {db_account_id}: "
                        f"{str(e)}"
                    )
                    continue

                # Update progress
                await self.send_message(
                    "import_update",
                    {
                        "status": "progress",
                        "message": (
                            f"Processing pair {i + 1}/{len(pairs)}: "
                            f"Tinkoff account {tinkoff_account_id} "
                            f"to DB account {db_account_id}"
                        ),
                        "progress": int((i / len(pairs)) * 100),
                    },
                )

                # Start import for this pair
                try:
                    # Call the import method from view_set
                    # Pass db_account_id instead of multiple parameters
                    self.import_generator = self.view_set.import_transactions_from_api(
                        self.user,
                        db_account_id,
                        confirm_every=self.confirm_every,
                        date_from=self.date_from,
                        date_to=self.date_to,
                    )

                    # Process the import
                    pair_results = await self.process_import()

                    # Update statistics
                    total_imported += pair_results.get("importedTransactions", 0)
                    total_skipped += pair_results.get("skippedTransactions", 0)
                    total_duplicates += pair_results.get("duplicateTransactions", 0)
                    total_errors += pair_results.get("importErrors", 0)

                except Exception as e:
                    logger.error(
                        f"Error importing transactions for pair {pair}: " f"{str(e)}"
                    )
                    total_errors += 1

            # Send final results
            await self.send_message(
                "import_complete",
                {
                    "message": "API import process completed",
                    "totalTransactions": total_imported
                    + total_skipped
                    + total_duplicates,
                    "importedTransactions": total_imported,
                    "skippedTransactions": total_skipped,
                    "duplicateTransactions": total_duplicates,
                    "importErrors": total_errors,
                },
            )

        except Exception as e:
            logger.error(f"Error in process_account_matches: {str(e)}")
            await self.send_error(f"Failed to process account matches: {str(e)}")

        finally:
            # Reset the stored data
            self.current_broker_id = None
            self.date_from = None
            self.date_to = None

    async def process_import(self):
        """Process the import."""
        logger.debug("[process_import] Starting process_import")
        import_results = {
            "totalTransactions": 0,
            "importedTransactions": 0,
            "skippedTransactions": 0,
            "duplicateTransactions": 0,
            "importErrors": 0,
        }
        security_cache = defaultdict(lambda: None)
        total_to_process = 0
        try:
            async for update in self.import_generator:
                logger.debug(f"[process_import] Processing update: {update}")

                if self.stop_event.is_set():
                    break

                # Handle total count
                if update.get("status") == "total_count":
                    total_to_process = update.get("total", 0)
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_update",
                                "data": {
                                    "status": "total_count",
                                    "total": total_to_process,
                                    "message": update.get(
                                        "message",
                                        f"Found {total_to_process} transactions",
                                    ),
                                },
                            }
                        )
                    )
                    continue

                # Handle duplicate transactions
                if update.get("status") == "duplicate_transaction":
                    import_results["duplicateTransactions"] += 1
                    logger.debug("Duplicate transaction detected")
                    continue

                # Handle transaction errors
                if update.get("status") == "transaction_error":
                    import_results["importErrors"] += 1
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "import_update",
                                "data": {
                                    "status": "transaction_error",
                                    "message": update.get(
                                        "message", "Error processing transaction"
                                    ),
                                    "error_detail": update.get("error_detail"),
                                },
                            }
                        )
                    )
                    continue

                # Handle save transaction
                if update.get("status") == "save_transaction":
                    transaction_data = update.get("data")
                    logger.debug(
                        "[process_import] Saving transaction immediately: "
                        f"{transaction_data}"
                    )

                    try:
                        # Save transaction immediately
                        save_result = await self.view_set.save_single_transaction(
                            transaction_data
                        )

                        if save_result.get("success"):
                            import_results["importedTransactions"] += 1
                            logger.debug(
                                f"Successfully saved transaction {save_result.get('transaction_id')}"  # noqa: E501
                            )

                            # Send progress update
                            await self.send(
                                text_data=json.dumps(
                                    {
                                        "type": "import_update",
                                        "data": {
                                            "status": "transaction_saved",
                                            "current": import_results[
                                                "importedTransactions"
                                            ],
                                            "total": total_to_process,
                                            "message": (
                                                f"Saved transaction {import_results['importedTransactions']} "  # noqa: E501
                                                f"of {total_to_process}"
                                            ),
                                        },
                                    }
                                )
                            )
                        else:
                            import_results["importErrors"] += 1
                            error_msg = save_result.get("error", "Unknown error")
                            logger.error(f"Failed to save transaction: {error_msg}")

                            # Send error to frontend
                            await self.send(
                                text_data=json.dumps(
                                    {
                                        "type": "import_update",
                                        "data": {
                                            "status": "save_error",
                                            "message": (
                                                f"Error saving transaction: {error_msg}"
                                            ),
                                            "error_detail": error_msg,
                                        },
                                    }
                                )
                            )
                    except Exception as e:
                        import_results["importErrors"] += 1
                        logger.error(
                            f"Exception while saving transaction: {str(e)}",
                            exc_info=True,
                        )
                        await self.send(
                            text_data=json.dumps(
                                {
                                    "type": "import_update",
                                    "data": {
                                        "status": "save_error",
                                        "message": (
                                            f"Error saving transaction: {str(e)}"
                                        ),
                                        "error_detail": str(e),
                                    },
                                }
                            )
                        )
                    continue

                if "error" in update:
                    logger.debug(f"[process_import] Error in update: {update['error']}")
                    import_results["importErrors"] += 1
                    await self.send(
                        text_data=json.dumps(
                            {"type": "import_error", "data": {"error": update["error"]}}
                        )
                    )
                elif update["status"] == "critical_error":
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "critical_error",
                                "data": {"error": update["message"]},
                            }
                        )
                    )
                elif update["status"] == "transaction_confirmation":
                    logger.debug(
                        f"[process_import] Handling transaction confirmation: "
                        f"{update['data']}"
                    )
                    try:
                        await self.handle_transaction_confirmation(update["data"])
                        logger.debug(
                            "[process_import] "
                            "Transaction confirmation handled successfully"
                        )
                    except Exception as e:
                        logger.error(f"Error in transaction confirmation: {str(e)}")
                        logger.error(f"Error type: {type(e)}")
                        import traceback

                        logger.error(f"Full traceback: {traceback.format_exc()}")
                        raise
                elif update.get("status") == "unrecognized_operation":
                    import_results["skippedTransactions"] += 1
                    if "комиссия" in update.get("transaction_data").description.lower():
                        logger.debug(
                            "Transaction skipped due to separatly logged commission"
                        )
                    else:
                        logger.debug(
                            "Transaction skipped due to unrecognized operation"
                        )
                        await self.send(
                            text_data=json.dumps(
                                {
                                    "type": "import_update",
                                    "data": {
                                        "status": "unrecognized_operation",
                                        "transaction_data": update["transaction_data"],
                                    },
                                }
                            )
                        )
                    continue
                elif update.get("status") == "security_mapping":
                    logger.debug(
                        f"Security mapping required for "
                        f"{update.get('mapping_data').get('security_description')}"
                    )

                    transaction_to_create = update["transaction_data"]
                    logger.debug(f"Transaction to create: {transaction_to_create}")

                    security_id = None  # Initialize security_id to None
                    if (
                        security_cache[update["mapping_data"]["security_description"]]
                        is not None
                    ):
                        security_id = security_cache[
                            update["mapping_data"]["security_description"]
                        ]
                        logger.debug(f"Security found in cache {security_id}")

                        # If confirm_every is True, ask for transaction confirmation
                        if self.confirm_every:
                            security = await get_security(security_id)
                            if security:
                                # Update the transaction data with the mapped security
                                transaction_to_create["security"] = security
                                try:
                                    logger.debug(
                                        "Handling transaction confirmation for: "
                                        f"{transaction_to_create}"
                                    )
                                    await self.handle_transaction_confirmation(
                                        transaction_to_create
                                    )
                                    continue  # Skip the rest of the loop iteration
                                except Exception as e:
                                    logger.error(
                                        f"Error in handle_transaction_confirmation: "
                                        f"{str(e)}"
                                    )
                                    logger.error(f"Error type: {type(e)}")
                                    import traceback

                                    logger.error(
                                        f"Full traceback: {traceback.format_exc()}"
                                    )
                                    raise
                    else:
                        await self.send(
                            text_data=json.dumps(
                                {
                                    "type": "import_update",
                                    "data": {
                                        "status": "security_mapping",
                                        "mapping_data": update["mapping_data"],
                                        "transaction_data": self._serialize_transaction_data(  # noqa: E501
                                            update["transaction_data"]
                                        ),
                                    },
                                }
                            )
                        )

                        mapping_response = await self.mapping_events.get()
                        logger.debug(
                            f"Received security mapping response: {mapping_response}"
                        )

                        if mapping_response.get("action") == "skip":
                            self.transactions_skipped += 1
                            logger.debug("Transaction skipped due to security mapping")
                            continue  # Skip to the next iteration
                        elif mapping_response.get("action") == "map":
                            security_id = mapping_response.get("security_id")
                            security_cache[
                                update["mapping_data"]["security_description"]
                            ] = security_id
                        else:
                            logger.error(
                                f"Unknown mapping action: "
                                f"{mapping_response.get('action')}"
                            )
                            self.transactions_skipped += 1
                            continue  # Skip to the next iteration

                    if security_id:
                        # Fetch the security object
                        security = await get_security(security_id)
                        if security:
                            # Update the transaction data with the mapped security
                            transaction_to_create["security"] = security

                            # Check if transaction already exists
                            existing_transaction = await transaction_exists(
                                transaction_to_create
                            )

                            if not existing_transaction:
                                self.transactions_to_create.append(
                                    transaction_to_create
                                )
                                logger.debug(
                                    "Transaction updated with mapped security and "
                                    "added to create list: "
                                    f"{transaction_to_create}"
                                )
                            else:
                                self.duplicate_count += 1
                                logger.debug(
                                    f"Transaction already exists: "
                                    f"{transaction_to_create}"
                                )
                        else:
                            logger.error(
                                f"Failed to fetch security with id: {security_id}"
                            )
                            self.transactions_skipped += 1
                    else:
                        logger.error("No security_id provided in mapping response")
                        self.transactions_skipped += 1

                elif update.get("status") == "progress":
                    await self.send(
                        text_data=json.dumps({"type": "import_update", "data": update})
                    )
                elif update.get("status") == "initialization":
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "initialization",
                                "message": update.get("message"),
                                "total_to_update": update.get("total_to_update"),
                            }
                        )
                    )
                elif update.get("status") == "add_transaction":
                    self.transactions_to_create.append(update.get("data"))
                    logger.debug(
                        f"Transaction added to create list: {update.get('data')}"
                    )
                elif update.get("status") == "processing_complete":
                    # Backend finished processing
                    # stats are tracked here, not from backend
                    logger.debug("[process_import] Backend processing complete")
                elif update.get("status") == "complete":
                    # Legacy handling - kept for file imports
                    logger.debug(f"[process_import] Received complete status: {update}")
                    import_results = update.get("data")
                else:
                    logger.debug(
                        f"[process_import] Unhandled update status: "
                        f"{update.get('status')}"
                    )

            logger.debug(
                "[process_import] Finished processing all updates from import generator"
            )

            # Calculate final stats
            # For API imports, totalTransactions is the sum of all outcomes
            # For file imports, it may come from the backend
            if import_results["totalTransactions"] == 0:
                import_results["totalTransactions"] = (
                    import_results["importedTransactions"]
                    + import_results["skippedTransactions"]
                    + import_results["duplicateTransactions"]
                    + import_results["importErrors"]
                )

            logger.debug(f"Final import results: {import_results}")

            await self.send(
                text_data=json.dumps(
                    {
                        "type": "import_complete",
                        "data": import_results,
                        "message": "Import process completed",
                    }
                )
            )

        except StopAsyncIteration:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "import_complete",
                        "data": {"message": "Import process completed"},
                    }
                )
            )
        except asyncio.CancelledError:
            logger.info("Import task was cancelled")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "import_cancelled",
                        "data": {"message": "Import process was cancelled"},
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error in process_import: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            logger.error("Error occurred at process_import level")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")

            # Log current state
            logger.error(
                f"transactions_to_create count: {len(self.transactions_to_create)}"
            )
            if self.transactions_to_create:
                logger.error(f"transactions_to_create: {self.transactions_to_create}")

            await self.send(
                text_data=json.dumps(
                    {
                        "type": "import_error",
                        "data": {
                            "error": (
                                "An error occurred during import processing: "
                                f"{str(e)}"
                            )
                        },
                    }
                )
            )
        finally:
            # Cleanup operations
            if self.stop_event.is_set():
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "import_stopped",
                            "data": {"message": "Import process stopped"},
                        }
                    )
                )
            self.stop_event.clear()
            self.transactions_to_create = []
            self.transactions_skipped = 0
            self.duplicate_count = 0

        # For API imports, use import_results; for file imports, use legacy counters
        if (
            import_results["importedTransactions"] > 0
            or import_results["duplicateTransactions"] > 0
        ):
            # API import - use tracked results
            results = import_results
        else:
            # File import - use legacy counters
            results = {
                "importedTransactions": len(self.transactions_to_create),
                "skippedTransactions": self.transactions_skipped,
                "duplicateTransactions": self.duplicate_count,
                "importErrors": import_results.get("importErrors", 0),
                "totalTransactions": len(self.transactions_to_create)
                + self.transactions_skipped
                + self.duplicate_count,
            }

        return results

    async def handle_transaction_confirmation(self, transaction_data):
        """Handle the transaction confirmation."""
        # Check if transaction already exists
        if transaction_data.get("is_fx"):
            existing_transaction = await fx_transaction_exists(transaction_data)
        else:
            existing_transaction = await transaction_exists(transaction_data)

        if not existing_transaction:
            serialized_data = self._serialize_transaction_data(transaction_data)
            logger.debug(f"Sending transaction_confirmation: {serialized_data}")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "import_update",
                        "data": {
                            "status": "transaction_confirmation",
                            "data": serialized_data,
                        },
                    }
                )
            )
            # Await confirmation from frontend
            confirmation = await self.confirmation_events.get()
            logger.debug(f"Received confirmation: {confirmation}")

            if confirmation:
                self.transactions_to_create.append(transaction_data)
                logger.debug(
                    "Transaction confirmed and added "
                    f"to create list: {transaction_data}"
                )
            else:
                self.transactions_skipped += 1
                logger.debug("Transaction skipped based on user confirmation")
        else:
            self.duplicate_count += 1
            logger.debug(
                f"Duplicate count in handle_transaction_confirmation: "
                f"{self.duplicate_count}."
            )
            logger.debug(f"Transaction already exists: {transaction_data}")

    def _serialize_transaction_data(self, data):
        if isinstance(data, dict):
            serialized = data.copy()  # Create a copy

            # Check if this is an FX transaction
            is_fx = serialized.get("is_fx", False)

            if is_fx:
                # For FX transactions, set type to 'FX' for frontend display
                serialized["type"] = "FX"

                # Serialize nested objects recursively
                for key, value in list(serialized.items()):
                    if isinstance(value, (CustomUser, Brokers, Assets, Accounts)):
                        serialized[key] = model_to_dict(value, fields=["id", "name"])
                    elif isinstance(value, (datetime.date, datetime.datetime)):
                        serialized[key] = value.isoformat()
                    elif isinstance(value, Decimal):
                        serialized[key] = float(value)

                # Format FX transaction data - use from_currency for formatting
                currency_for_format = serialized.get("from_currency", "USD")
                return format_table_data(
                    serialized, currency_for_format, number_of_digits=2
                )
            else:
                # Regular transaction handling
                # Add total value to show to the user for confirmation
                if (
                    "price" in serialized
                    and "quantity" in serialized
                    and serialized["price"] is not None
                    and serialized["quantity"] is not None
                ):
                    serialized["total"] = round(
                        serialized["quantity"] * serialized["price"], 2
                    )

                for key, value in serialized.items():
                    serialized[key] = self._serialize_transaction_data(
                        value
                    )  # Recursive call for dicts

                # Use currency field for regular transactions
                currency = serialized.get("currency", "USD")
                return format_table_data(serialized, currency, number_of_digits=2)
        elif isinstance(data, (CustomUser, Brokers, Assets, Accounts)):
            return model_to_dict(data, fields=["id", "name"])
        elif isinstance(data, (datetime.date, datetime.datetime)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data

    async def create_account_and_import(
        self, broker_id, tinkoff_account, name, comment=""
    ):
        """
        Create a new account in the database and import transactions.

        :param broker_id: ID of the broker
        :param tinkoff_account: Dict with tinkoff account details
        :param name: Name for the new account
        :param comment: Optional comment for the new account
        """
        try:
            logger.debug(
                f"Creating new account '{name}' for tinkoff account {tinkoff_account}"
            )

            # Get Tinkoff account ID
            tinkoff_account_id = tinkoff_account.get("id")
            if not tinkoff_account_id:
                await self.send_error("Invalid Tinkoff account data")
                return

            # Send progress update
            await self.send_message(
                "import_update",
                {
                    "status": "progress",
                    "message": f"Creating new account '{name}'",
                    "progress": 10,
                },
            )

            # Create new account
            @database_sync_to_async
            def create_account():
                broker = Brokers.objects.get(id=broker_id)
                # Set native_id when creating the account
                account = Accounts.objects.create(
                    name=name,
                    broker=broker,
                    investor=self.user,
                    comment=comment,
                    native_id=tinkoff_account_id,
                )
                return account

            new_account = await create_account()
            logger.debug(
                f"Created new account with ID {new_account.id} "
                f"and native ID {new_account.native_id}"
            )

            # Update progress
            await self.send_message(
                "import_update",
                {
                    "status": "progress",
                    "message": f"Starting import for new account '{name}'",
                    "progress": 20,
                },
            )

            # Start the import for this account
            self.import_generator = self.view_set.import_transactions_from_api(
                self.user,
                new_account.id,  # Just pass the account ID directly
                confirm_every=self.confirm_every,
                date_from=self.date_from,
                date_to=self.date_to,
            )

            # Process the import
            import_results = await self.process_import()

            # Send final results
            await self.send_message(
                "import_complete",
                {
                    "message": f"Import completed for new account '{name}'",
                    "account_created": True,
                    "account_id": new_account.id,
                    "account_name": new_account.name,
                    **import_results,
                },
            )

        except Exception as e:
            logger.error(f"Error in create_account_and_import: {str(e)}")
            await self.send_error(f"Failed to create account and import: {str(e)}")

        finally:
            # Reset the stored data
            self.current_broker_id = None
            self.date_from = None
            self.date_to = None
