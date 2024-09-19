from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .views import TransactionViewSet
import json
import structlog
import traceback
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

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            await self.accept()
            logger.debug("WebSocket connection opened")
        else:
            await self.close()

    async def disconnect(self, close_code):
        logger.debug("WebSocket connection closed")

    async def receive(self, text_data):
        logger.debug(f"Received WebSocket message: {text_data}")
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json['type']

            if message_type == 'test_message':
                content = text_data_json.get('content')
                logger.debug(f"Test message received: {content}")
                await self.send(text_data=json.dumps({
                    'type': 'test_message_response',
                    'data': {'message': 'Test message received successfully'}
                }))
            elif message_type == 'start_import':
                file_id = text_data_json.get('file_id')
                broker_id = text_data_json.get('broker_id')
                await self.start_import(file_id, broker_id)
            elif message_type == 'security_mapped':
                security_id = text_data_json.get('security_id')
                await self.mapping_events.put(security_id)
                logger.debug(f"Put mapping event: {security_id}")
            elif message_type == 'transaction_confirmed':
                confirmed = text_data_json.get('confirmed')
                await self.confirmation_events.put(confirmed)
                logger.debug(f"Put confirmation event: {confirmed}")
            elif message_type == 'stop_import':
                self.stop_event.set()
                await self.send(text_data=json.dumps({
                    'type': 'import_stopped',
                    'data': {'message': 'Import process stopped by user'}
                }))
                logger.debug("Stop event set")
            else:
                logger.warning(f"Unknown message type received: {message_type}")

        except json.JSONDecodeError:
            logger.error("Received invalid JSON data")
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
            logger.error(f"Unexpected error in receive: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'An unexpected error occurred'
            }))

    async def start_import(self, file_id, broker_id):
        logger.debug("Starting start_import")
        try:
            view_set = TransactionViewSet()
            self.import_generator = view_set.import_transactions(self.user, file_id, broker_id, self)
            await self.process_import()
        except Exception as e:
            logger.error(f"Error in start_import: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': f'An error occurred during import: {str(e)}'}
            }))
        finally:
            logger.debug("Finishing start_import")

    async def process_import(self):
        logger.debug("Starting process_import")
        try:
            async for update in self.import_generator:
                if self.stop_event.is_set():
                    break
                if isinstance(update, dict):
                    if 'error' in update:
                        await self.send(text_data=json.dumps({
                            'type': 'import_error',
                            'data': {'error': update['error']}
                        }))
                    elif update.get('status') == 'transaction_confirmation':
                        await self.send(text_data=json.dumps({
                            'type': 'transaction_confirmation',
                            'data': update
                        }))
                        # Wait for confirmation or stop event
                        done, _ = await asyncio.wait(
                            [asyncio.create_task(self.confirmation_events.get()), asyncio.create_task(self.stop_event.wait())],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        if self.stop_event.is_set():
                            break
                        confirmation = done.pop().result()
                        if not confirmation:
                            logger.debug(f"Skipping transaction: {update}")
                            continue  # Skip this transaction
                    elif update.get('status') == 'security_mapping':
                        await self.send(text_data=json.dumps({
                            'type': 'security_mapping',
                            'data': update
                        }))
                        security_id = await self.mapping_events.get()
                        await self.import_generator.asend(security_id)
                    elif update.get('status') == 'complete':
                        await self.send(text_data=json.dumps({
                            'type': 'import_complete',
                            'data': update['data']
                        }))
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'import_update',
                            'data': update
                        }))
        except StopAsyncIteration:
            await self.send(text_data=json.dumps({
                'type': 'import_complete',
                'data': {'message': 'Import process completed'}
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
            else:
                await self.send(text_data=json.dumps({
                    'type': 'import_complete',
                    'data': {'message': 'Import process completed'}
                }))

    async def security_mapped(self, security_id):
        try:
            # Put the security mapping into the queue for the generator to process
            await self.mapping_events.put(security_id)
            await self.process_import()
        except StopAsyncIteration:
            await self.send(text_data=json.dumps({
                'type': 'import_complete',
                'data': {'message': 'Import process completed'}
            }))
        except Exception as e:
            logger.error(f"Error in security_mapped: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': f'An error occurred during security mapping: {str(e)}'}
            }))

    async def transaction_confirmed(self, confirmed):
        try:
            # Put the confirmation into the queue for the generator to process
            await self.confirmation_events.put(confirmed)
            await self.process_import()
        except StopAsyncIteration:
            await self.send(text_data=json.dumps({
                'type': 'import_complete',
                'data': {'message': 'Import process completed'}
            }))
        except Exception as e:
            logger.error(f"Error in transaction_confirmed: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': f'An error occurred during transaction confirmation: {str(e)}'}
            }))

