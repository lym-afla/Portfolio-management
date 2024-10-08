import json
from channels.generic.http import AsyncHttpConsumer
from channels.db import database_sync_to_async

from constants import CURRENCY_CHOICES
from .forms import BrokerPerformanceForm
from core.database_utils import get_years_count, save_or_update_annual_broker_performance
from django.conf import settings
from datetime import datetime
import logging
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

class UpdateBrokerPerformanceConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        headers = [
            (b"Access-Control-Allow-Origin", b"http://localhost:8080"),  # Adjust this to match your frontend URL
            (b"Access-Control-Allow-Methods", b"POST, OPTIONS"),
            (b"Access-Control-Allow-Headers", b"Content-Type, Authorization"),
            (b"Access-Control-Allow-Credentials", b"true"),
        ]

        if self.scope['method'] == 'OPTIONS':
            # Handle CORS preflight
            await self.send_response(200, b'', headers=headers)
            return

        if isinstance(self.scope['user'], AnonymousUser):
            await self.send_response(401, json.dumps({'error': 'Authentication required'}).encode('utf-8'), headers=headers + [
                (b'Content-Type', b'application/json'),
            ])
            return

        elif self.scope['method'] == 'POST':

            # Parse the request body
            try:
                data = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError:
                await self.send_response(400, json.dumps({'error': 'Invalid JSON'}).encode('utf-8'), headers=headers + [
                    (b'Content-Type', b'application/json'),
                ])
                return
            
            logger.debug(f"Received data: {data}")
            logger.debug(f"Scope: {self.scope}")

            # Extract effective_current_date from the request data
            effective_current_date_str = data.get('effective_current_date')
            if not effective_current_date_str:
                await self.send_response(400, json.dumps({'error': 'Missing effective_current_date'}).encode('utf-8'))
                return

            try:
                effective_current_date = datetime.strptime(effective_current_date_str, '%Y-%m-%d').date()
            except ValueError:
                await self.send_response(400, b'Invalid "effective_current_date" format')
                return

            # Validate the form data
            form = await database_sync_to_async(BrokerPerformanceForm)(data, investor=self.scope['user'])
            if not await database_sync_to_async(form.is_valid)():
                errors = form.errors.as_json()
                await self.send_response(400, json.dumps({'error': 'Invalid form data', 'errors': form.errors}).encode('utf-8'), headers=headers + [
                    (b'Content-Type', b'application/json'),
                ])
                return

            broker_or_group = form.cleaned_data['broker_or_group']
            currency = form.cleaned_data['currency']
            is_restricted_str = form.cleaned_data['is_restricted']
            skip_existing_years = form.cleaned_data['skip_existing_years']
            user = self.scope['user']

            # Determine is_restricted_list
            if is_restricted_str == 'None':
                is_restricted_list = [None]
            elif is_restricted_str == 'True':
                is_restricted_list = [True]
            elif is_restricted_str == 'False':
                is_restricted_list = [False]
            elif is_restricted_str == 'All':
                is_restricted_list = [None, True, False]
            else:
                await self.send_response(400, b'Invalid "is_restricted" value')
                return

            # Set headers for SSE
            sse_headers = headers + [
                (b"Cache-Control", b"no-cache"),
                (b"Content-Type", b"text/event-stream"),
                (b"Transfer-Encoding", b"chunked"),
            ]
            await self.send_headers(headers=sse_headers)

            currencies = [currency] if currency != 'All' else [choice[0] for choice in CURRENCY_CHOICES]
            total_operations = len(currencies) * len(is_restricted_list) * await database_sync_to_async(get_years_count)(user, effective_current_date, broker_or_group)

            # Send initial progress event
            initial_event = {
                'status': 'initializing',
                'total': total_operations
            }
            await self.send_body(json.dumps(initial_event).encode('utf-8') + b'\n', more_body=True)

            current_operation = 0

            try:
                for curr in currencies:
                    for is_restricted in is_restricted_list:
                        async for progress_data in save_or_update_annual_broker_performance(user, effective_current_date, broker_or_group, curr, is_restricted, skip_existing_years):
                            if progress_data['status'] == 'progress':
                                current_operation += 1
                                progress = (current_operation / total_operations) * 100
                                event = {
                                    'status': 'progress',
                                    'current': current_operation,
                                    'progress': progress,
                                    'year': progress_data.get('year'),
                                    'currency': curr,
                                    'is_restricted': str(is_restricted)
                                }
                                await self.send_body(json.dumps(event).encode('utf-8') + b'\n', more_body=True)
                            elif progress_data['status'] == 'error':
                                await self.send_body(json.dumps(progress_data).encode('utf-8') + b'\n', more_body=True)

                # Send complete event
                complete_event = {'status': 'complete'}
                await self.send_body(json.dumps(complete_event).encode('utf-8') + b'\n', more_body=False)

            except Exception as e:
                error_event = {'status': 'error', 'message': str(e)}
                await self.send_body(json.dumps(error_event).encode('utf-8') + b'\n', more_body=False)

        else:
            # Method not allowed
            await self.send_response(405, json.dumps({'error': 'Method Not Allowed'}).encode('utf-8'), headers=headers + [
                (b'Content-Type', b'application/json'),
            ])