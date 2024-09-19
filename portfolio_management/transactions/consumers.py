import datetime
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.forms import model_to_dict

from common.models import Assets, Brokers
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
                if not self.import_task or self.import_task.done():
                    self.import_task = asyncio.create_task(self.start_import(file_id, broker_id))
                    logger.debug("Started import_task")
                else:
                    logger.warning("Import task already running")
                    await self.send(text_data=json.dumps({
                        'type': 'import_warning',
                        'data': {'message': 'Import already in progress'}
                    }))
            elif message_type == 'security_mapped':
                security_id = text_data_json.get('security_id')
                await self.mapping_events.put(security_id)
                logger.debug(f"Put mapping event: {security_id}")
            elif message_type == 'transaction_confirmed':
                confirmed = text_data_json.get('confirmed', False)
                await self.confirmation_events.put(confirmed)
                logger.debug(f"Put confirmation event: {confirmed}. Queue size: {self.confirmation_events.qsize()}")

            elif message_type == 'stop_import':
                self.stop_event.set()
                logger.debug("Stop event set for import")

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

    async def start_import(self, file_id, broker_id):
        logger.debug("Starting start_import")
        try:
            view_set = TransactionViewSet()
            self.import_generator = view_set.import_transactions(self.user, file_id, broker_id, self)
            # asyncio.create_task(self.process_import())  # Ensure it's a background task
            await self.process_import()
        except Exception as e:
            logger.error(f"Error in start_import: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': f'An error occurred during import: {str(e)}'}
            }))

    async def process_import(self):
        logger.debug("Starting process_import")
        transactions_to_create = []
        try:
            async for update in self.import_generator:
                # await self.send(text_data=json.dumps(update))
                # logger.debug(f"Sent update to frontend: {update}")

                if 'error' in update:
                        await self.send(text_data=json.dumps({
                            'type': 'import_error',
                            'data': {'error': update['error']}
                        }))
                elif update['status'] == 'transaction_confirmation':
                    logger.debug(f"Sending transaction_confirmation: {self.serialize_transaction_data(update)}")
                    await self.send(text_data=json.dumps({
                            'type': 'transaction_confirmation',
                            'data': self.serialize_transaction_data(update)
                        }))
                    # Await confirmation from frontend
                    confirmation = await self.confirmation_events.get()
                    logger.debug(f"Received confirmation: {confirmation}")

                    if confirmation:
                        # Prepare the transaction data to create
                        transaction_data = update['data']
                        transactions_to_create.append(transaction_data)
                        logger.debug(f"Transaction confirmed and added to create list: {transaction_data}")
                    else:
                        logger.debug("Transaction skipped based on user confirmation")

                elif update.get('status') == 'security_mapping':
                    logger.debug(f"Security mapping required for {update.get('security')}")
                    await self.send(text_data=json.dumps({
                        'type': 'security_mapping',
                        'data': update
                    }))
                    done, _ = await asyncio.wait(
                        [
                            asyncio.create_task(self.mapping_events.get()),
                            asyncio.create_task(self.stop_event.wait())
                        ],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    if self.stop_event.is_set():
                        logger.debug("Stop event detected during security mapping")
                        break
                    security_id = done.pop().result()
                    logger.debug(f"Received security mapping: {security_id}")
                elif update.get('status') == 'complete':
                    await self.send(text_data=json.dumps({
                        'type': 'import_complete',
                        'data': update
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'import_update',
                        'data': update
                    }))
        

            # After processing all transactions, save confirmed transactions
            if transactions_to_create:
                try:
                    await self.save_transactions(transactions_to_create)
                    await self.send(text_data=json.dumps({
                        'type': 'save_success',
                        'data': {'message': 'Confirmed transactions saved successfully'}
                    }))
                except Exception as e:
                    logger.error(f"Error saving transactions: {str(e)}")
                    await self.send(text_data=json.dumps({
                        'type': 'save_error',
                        'data': {'message': f'Error saving transactions: {str(e)}'}
                    }))
            else:
                logger.debug("No transactions to save")

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
            self.stop_event.clear()
            if self.stop_event.is_set():
                await self.send(text_data=json.dumps({
                    'type': 'import_stopped',
                    'data': {'message': 'Import process stopped'}
                }))
            else:
                await self.send(text_data=json.dumps({
                    'type': 'import_complete',
                    'data': {'message': 'Import process completed'}
                }))
        

    async def save_transactions(self, transactions):
        """
        Save the confirmed transactions to the database.
        """
        try:
            await self.view_set.save_transactions(transactions)
            logger.debug(f"Transactions saved {len(transactions)} successfully")
        except Exception as e:
            logger.error(f"Error saving transactions: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'save_error',
                'data': {'message': f'Error saving transactions: {str(e)}'}
            }))

    def serialize_transaction_data(self, data):
        if isinstance(data, dict):
            serialized = {}
            for key, value in data.items():
                serialized[key] = self.serialize_transaction_data(value)  # Recursive call for dicts
            return serialized
        elif isinstance(data, (CustomUser, Brokers, Assets)):
            return model_to_dict(data, fields=['id', 'name'])
        elif isinstance(data, (datetime.date, datetime.datetime)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data