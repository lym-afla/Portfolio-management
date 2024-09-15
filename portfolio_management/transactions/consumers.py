from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .views import TransactionViewSet
# from asgiref.sync import sync_to_async
import json
import traceback
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class TransactionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.debug("Attempting to connect...")
        self.user = self.scope["user"]
        logger.debug(f"User in scope: {self.user}")
        logger.debug(f"Is user anonymous: {self.user.is_anonymous}")
        logger.debug(f"User ID: {getattr(self.user, 'id', None)}")

        if self.user.is_anonymous:
            logger.warning("Rejecting connection: User is anonymous")
            await self.close()
        else:
            logger.info(f"Accepting connection for user {self.user.id}")
            await self.accept()

    async def disconnect(self, close_code):
        logger.debug(f"WebSocket disconnected with code: {close_code}")
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        logger.debug(f"Received message: {text_data}")
        if self.user.is_anonymous:
            logger.warning("Rejecting message: User is anonymous")
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': 'User is not authenticated'}
            }))
            return

        logger.debug('Received by the ws data:', text_data, self.user.id)
        text_data_json = json.loads(text_data)
        message_type = text_data_json['type']

        if message_type == 'start_import':
            await self.start_import(text_data_json['file_id'], text_data_json['broker_id'])
        elif message_type == 'security_mapped':
            await self.security_mapped(text_data_json['security_id'])

    async def start_import(self, file_id, broker_id):
        try:
            view_set = TransactionViewSet()
            # generator = await sync_to_async(view_set.import_transactions)(self.scope['user'], file_id, broker_id)
            # generator = view_set.import_transactions(self.scope['user'], file_id, broker_id)
            generator = await database_sync_to_async(view_set.import_transactions)(self.user, file_id, broker_id)

            async for update in self.async_generator(generator):
            # for update in generator:
                if isinstance(update, dict) and 'error' in update:
                    await self.send(text_data=json.dumps({
                        'type': 'import_error',
                        'data': {'error': update['error']}
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'import_update',
                        'data': update
                    }))
        except Exception as e:
            error_message = f"An error occurred during import: {str(e)}"
            traceback.print_exc()  # This will print the full traceback to the console
            await self.send(text_data=json.dumps({
                'type': 'import_error',
                'data': {'error': error_message}
            }))

    async def async_generator(self, sync_generator):
        try:
            while True:
                yield await database_sync_to_async(next)(sync_generator)
        except StopIteration:
            pass

    async def security_mapped(self, security_id):
        # Implement logic to handle mapped security
        pass

    async def import_update(self, event):
        await self.send(text_data=json.dumps(event['message']))
