from collections import defaultdict
import datetime
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.forms import model_to_dict

from common.models import Assets, Brokers
from core.formatting_utils import format_table_data
from core.import_utils import get_security, transaction_exists
from users.models import CustomUser
from .views import TransactionViewSet
import json
import structlog
import asyncio
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class TransactionConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize queues to handle confirmations and mappings
        self.confirmation_events = asyncio.Queue()
        self.mapping_events = asyncio.Queue()
        self.stop_event = asyncio.Event()
        self.import_task = None  # Track the import task
        self.view_set = TransactionViewSet()  # Initialize your view set
        self.confirm_every = False
        self.transactions_to_create = []
        self.transactions_skipped = 0
        self.duplicate_count = 0

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            await self.accept()
            logger.debug("WebSocket connection opened")
        else:
            await self.close()

    async def disconnect(self, close_code):
        logger.debug("WebSocket connection closed")
        if self.import_task and not self.import_task.done():
            self.import_task.cancel()
            try:
                await self.import_task
            except asyncio.CancelledError:
                logger.debug("Import task cancelled upon disconnect")

    async def receive(self, text_data):
        logger.debug(f"Received WebSocket message: {text_data}")
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json['type']

            if message_type == 'start_import':
                file_id = text_data_json.get('file_id')
                broker_id = text_data_json.get('broker_id')
                confirm_every = text_data_json.get('confirm_every', False)
                if not self.import_task or self.import_task.done():
                    self.import_task = asyncio.create_task(self.start_import(file_id, broker_id, confirm_every))  # Update this line
                    logger.debug("Started import_task")
                else:
                    logger.warning("Import task already running")
                    await self.send(text_data=json.dumps({
                        'type': 'import_warning',
                        'data': {'message': 'Import already in progress'}
                    }))
            elif message_type == 'security_mapped':
                action = text_data_json.get('action')
                security_id = text_data_json.get('security_id', None)
                mapping_response = {
                    'action': action,
                    'security_id': security_id
                }
                await self.mapping_events.put(mapping_response)
                logger.debug(f"Put mapping event: {mapping_response}")
            elif message_type == 'transaction_confirmed':
                confirmed = text_data_json.get('confirmed', False)
                await self.confirmation_events.put(confirmed)
                logger.debug(f"Put confirmation event: {confirmed}. Queue size: {self.confirmation_events.qsize()}")

            elif message_type == 'stop_import':
                self.stop_event.set()
                logger.debug("Stop event set for import")
                self.transactions_to_create = []
                self.transactions_skipped = 0
                self.duplicate_count = 0

            else:
                logger.warning(f"Unhandled message type: {message_type}")

        except json.JSONDecodeError:
            logger.error("Failed to decode JSON message")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data received'
            }))
        except KeyError as e:
            logger.error(f"Missing required key in message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Missing required data: {str(e)}'
            }))
        except Exception as e:
            logger.error(f"Error handling receive: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': {'message': f'An error occurred: {str(e)}'}
            }))

    async def start_import(self, file_id, broker_id, confirm_every):
        logger.debug("Starting start_import")
        try:
            self.confirm_every = confirm_every
            self.import_generator = self.view_set.import_transactions(self.user, file_id, broker_id, self, confirm_every)
            await self.process_import()
        except Exception as e:
            logger.error(f"Error in start_import: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': f'An error occurred during import: {str(e)}'}
            }))

    async def process_import(self):
        logger.debug("Starting process_import")
        import_results = {}
        security_cache = defaultdict(lambda: None)
        try:
            async for update in self.import_generator:
                if 'error' in update:
                    await self.send(text_data=json.dumps({
                        'type': 'import_error',
                        'data': {'error': update['error']}
                    }))
                elif update['status'] == 'transaction_confirmation':
                    await self.handle_transaction_confirmation(update['data'])
                elif update.get('status') == 'security_mapping':
                    logger.debug(f"Security mapping required for {update.get('mapping_data').get('stock_description')}")
                    
                    transaction_to_create = update['transaction_data']
                    logger.debug(f"Transaction to create: {transaction_to_create}")

                    security_id = None  # Initialize security_id to None
                    if security_cache[update['mapping_data']['stock_description']] is not None:
                        security_id = security_cache[update['mapping_data']['stock_description']]
                        logger.debug(f"Security found in cache {security_id}")
                        
                        # If confirm_every is True, ask for transaction confirmation
                        if self.confirm_every:
                            security = await get_security(security_id)
                            if security:
                                # Update the transaction data with the mapped security
                                transaction_to_create['security'] = security
                                await self.handle_transaction_confirmation(transaction_to_create)
                                continue  # Skip the rest of the loop iteration
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'import_update',
                            'data': {
                                'status': 'security_mapping',
                                'mapping_data': update['mapping_data'],
                                'transaction_data': self._serialize_transaction_data(update['transaction_data'])
                            }
                        }))
                        
                        mapping_response = await self.mapping_events.get()
                        logger.debug(f"Received security mapping response: {mapping_response}")
                        
                        if mapping_response.get('action') == 'skip':
                            self.transactions_skipped += 1
                            logger.debug("Transaction skipped due to security mapping")
                            continue  # Skip to the next iteration
                        elif mapping_response.get('action') == 'map':
                            security_id = mapping_response.get('security_id')
                            security_cache[update['mapping_data']['stock_description']] = security_id
                        else:
                            logger.error(f"Unknown mapping action: {mapping_response.get('action')}")
                            self.transactions_skipped += 1
                            continue  # Skip to the next iteration

                    if security_id:
                        # Fetch the security object
                        security = await get_security(security_id)
                        if security:
                            # Update the transaction data with the mapped security
                            transaction_to_create['security'] = security
                            
                            # Check if transaction already exists
                            existing_transaction = await transaction_exists(transaction_to_create)
                            
                            if not existing_transaction:
                                self.transactions_to_create.append(transaction_to_create)
                                logger.debug(f"Transaction updated with mapped security and added to create list: {transaction_to_create}")
                            else:
                                self.duplicate_count += 1
                                logger.debug(f"Transaction already exists: {transaction_to_create}")
                        else:
                            logger.error(f"Failed to fetch security with id: {security_id}")
                            self.transactions_skipped += 1
                    else:
                        logger.error("No security_id provided in mapping response")
                        self.transactions_skipped += 1
                        
                elif update.get('status') == 'progress':
                    await self.send(text_data=json.dumps({
                        'type': 'import_update',
                        'data': update
                    }))  
                elif update.get('status') == 'initialization':
                    await self.send(text_data=json.dumps({
                        'type': 'initialization',
                        'message': update.get('message'),
                        'total_to_update': update.get('total_to_update')
                    }))
                elif update.get('status') == 'add_transaction':
                    self.transactions_to_create.append(update.get('data'))
                    logger.debug(f"Transaction added to create list: {update.get('data')}")
                elif update.get('status') == 'complete':
                    import_results = update.get('data')
                    # logger.debug(f"[process_import] Import results: {update}")

            # After processing all transactions, save confirmed transactions
            if self.transactions_to_create:
                try:
                    await self.view_set.save_transactions(self.transactions_to_create)
                    # Sending final confirmation message after the update
                    logger.debug(f"Stats before finalising import. Imported: {import_results['importedTransactions']} || {len(self.transactions_to_create)}. Skipped: {import_results['skippedTransactions']} || {self.transactions_skipped}. Duplicate:. {import_results['duplicateTransactions']} || {self.duplicate_count}")
                    import_results['importedTransactions'] = len(self.transactions_to_create)
                    import_results['skippedTransactions'] += self.transactions_skipped
                    import_results['duplicateTransactions'] += self.duplicate_count
                    logger.debug(f"Import results: {import_results}")
                    await self.send(text_data=json.dumps({
                        'type': 'import_complete',
                        'data': import_results,
                        'message': 'End of process_import method. Import process completed'
                    }))
                except Exception as e:
                    logger.error(f"Error saving transactions: {str(e)}")
                    await self.send(text_data=json.dumps({
                        'type': 'save_error',
                        'data': {'error': f'Error saving transactions: {str(e)}'}
                    }))
            else:
                logger.debug("No transactions to save")
                logger.debug(f"Stats before finalising import. Imported: {import_results['importedTransactions']} || {len(self.transactions_to_create)}. Skipped: {import_results['skippedTransactions']} || {self.transactions_skipped}. Duplicate:. {import_results['duplicateTransactions']} || {self.duplicate_count}")
                import_results['skippedTransactions'] += self.transactions_skipped
                import_results['duplicateTransactions'] += self.duplicate_count
                logger.debug(f"Import results: {import_results}")
                await self.send(text_data=json.dumps({
                    'type': 'import_complete',
                    'data': import_results,
                    'message': 'End of process_import method. Import process completed'
                }))

        except StopAsyncIteration:
            await self.send(text_data=json.dumps({
                'type': 'import_complete',
                'data': {'message': 'Import process completed'}
            }))
        except asyncio.CancelledError:
            logger.info("Import task was cancelled")
            await self.send(text_data=json.dumps({
                'type': 'import_cancelled',
                'data': {'message': 'Import process was cancelled'}
            }))
        except Exception as e:
            logger.error(f"Error in process_import: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': f'An error occurred during import processing: {str(e)}'}
            }))
        finally:
            if self.stop_event.is_set():
                await self.send(text_data=json.dumps({
                    'type': 'import_stopped',
                    'data': {'message': 'Import process stopped'}
                }))
            self.stop_event.clear()
            self.transactions_to_create = []
            self.transactions_skipped = 0
            self.duplicate_count = 0

    async def handle_transaction_confirmation(self, transaction_data):
        # Check if transaction already exists
        existing_transaction = await transaction_exists(transaction_data)
        
        if not existing_transaction:        
            serialized_data = self._serialize_transaction_data(transaction_data)
            logger.debug(f"Sending transaction_confirmation: {serialized_data}")
            await self.send(text_data=json.dumps({
                'type': 'import_update',
                'data': {
                    'status': 'transaction_confirmation',
                    'data': serialized_data
                }
            }))
            # Await confirmation from frontend
            confirmation = await self.confirmation_events.get()
            logger.debug(f"Received confirmation: {confirmation}")

            if confirmation:
                self.transactions_to_create.append(transaction_data)
                logger.debug(f"Transaction confirmed and added to create list: {transaction_data}")
            else:
                self.transactions_skipped += 1
                logger.debug("Transaction skipped based on user confirmation")
        else:
            self.duplicate_count += 1
            logger.debug(f"Duplicate count in handle_transaction_confirmation: {self.duplicate_count}.")
            logger.debug(f"Transaction already exists: {transaction_data}")

    def _serialize_transaction_data(self, data):
        if isinstance(data, dict):
            serialized = data.copy()  # Create a copy

            # Add total value to show to the user for confirmation
            if 'price' in serialized and 'quantity' in serialized:
                serialized['total'] = round(serialized['quantity'] * serialized['price'], 2)
            
            for key, value in serialized.items():
                serialized[key] = self._serialize_transaction_data(value)  # Recursive call for dicts
            return format_table_data(serialized, self.user.default_currency, number_of_digits=2)
        elif isinstance(data, (CustomUser, Brokers, Assets)):
            return model_to_dict(data, fields=['id', 'name'])
        elif isinstance(data, (datetime.date, datetime.datetime)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data