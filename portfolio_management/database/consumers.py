import json
from channels.generic.http import AsyncHttpConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async

from django.utils.dateparse import parse_date
import asyncio
from common.models import Assets, BrokerAccounts, FX, Transactions
from core.import_utils import generate_dates_for_price_import, import_security_prices_from_ft, import_security_prices_from_yahoo, import_security_prices_from_micex

from constants import CURRENCY_CHOICES
from .forms import AccountPerformanceForm
from core.database_utils import get_years_count, save_or_update_annual_broker_performance
from django.conf import settings
from datetime import datetime
import logging
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.utils.formats import date_format
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

class UpdateAccountPerformanceConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        headers = [
            (b"Access-Control-Allow-Origin", b"http://localhost:8080"),  # Adjust this to match your frontend URL
            (b"Access-Control-Allow-Methods", b"POST, OPTIONS"),
            (b"Access-Control-Allow-Headers", b"Content-Type, Authorization"),
            (b"Access-Control-Allow-Credentials", b"true"),
            (b"Cache-Control", b"no-cache"),
            (b"Content-Type", b"text/event-stream"),
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
            form = await database_sync_to_async(AccountPerformanceForm)(data, investor=self.scope['user'])
            if not await database_sync_to_async(form.is_valid)():
                errors = form.errors.as_json()
                await self.send_response(400, json.dumps({'error': 'Invalid form data', 'errors': form.errors}).encode('utf-8'), headers=headers + [
                    (b'Content-Type', b'application/json'),
                ])
                return

            selection_account_type = form.cleaned_data['selection_account_type']
            selection_account_id = form.cleaned_data['selection_account_id']
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
            ]
            await self.send_headers(headers=sse_headers)

            currencies = [currency] if currency != 'All' else [choice[0] for choice in CURRENCY_CHOICES]
            total_operations = len(currencies) * len(is_restricted_list) * await database_sync_to_async(get_years_count)(user, effective_current_date, selection_account_type, selection_account_id)

            # Modify how you send SSE messages
            async def send_sse_message(self, data):
                try:
                    message = f"data: {json.dumps(data)}\n\n"
                    await self.send_body(message.encode('utf-8'), more_body=True)
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error sending SSE message: {str(e)}")
                    raise

            # Update the progress sending code
            try:
                # Send initial progress event
                await send_sse_message(self, {
                    'status': 'initializing',
                    'total': total_operations
                })

                current_operation = 0

                for curr in currencies:
                    for is_restricted in is_restricted_list:
                        async for progress_data in save_or_update_annual_broker_performance(
                            user, effective_current_date, selection_account_type,
                            selection_account_id, curr, is_restricted, skip_existing_years
                        ):
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
                                logger.info(f"Sending SSE message: {event} at: {progress_data['timestamp']}")
                                await send_sse_message(self, event)
                            elif progress_data['status'] == 'error':
                                await send_sse_message(self, progress_data)

                # Send complete event
                complete_event = {'status': 'complete'}
                await send_sse_message(self, complete_event)
                await self.send_body(b'', more_body=False)

            except Exception as e:
                logger.error(f"Error in consumer: {str(e)}", exc_info=True)
                await send_sse_message(self, {
                    'status': 'error',
                    'message': str(e)
                })
                await self.send_body(b'', more_body=False)

        else:
            # Method not allowed
            await self.send_response(405, json.dumps({'error': 'Method Not Allowed'}).encode('utf-8'), headers=headers + [
                (b'Content-Type', b'application/json'),
            ])

class PriceImportConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        headers = [
            (b"Access-Control-Allow-Origin", b"http://localhost:8080"),
            (b"Access-Control-Allow-Methods", b"POST, OPTIONS"),
            (b"Access-Control-Allow-Headers", b"Content-Type, Authorization"),
            (b"Access-Control-Allow-Credentials", b"true"),
        ]

        if self.scope['method'] == 'OPTIONS':
            await self.send_response(200, b'', headers=headers)
            return

        if isinstance(self.scope['user'], AnonymousUser):
            await self.send_response(401, json.dumps({'error': 'Authentication required'}).encode('utf-8'), headers=headers + [
                (b'Content-Type', b'application/json'),
            ])
            return

        if self.scope['method'] == 'POST':
            try:
                data = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError:
                await self.send_response(400, json.dumps({'error': 'Invalid JSON'}).encode('utf-8'), headers=headers + [
                    (b'Content-Type', b'application/json'),
                ])
                return

            sse_headers = headers + [
                (b"Cache-Control", b"no-cache"),
                (b"Content-Type", b"text/event-stream"),
                (b"Transfer-Encoding", b"chunked"),
            ]
            await self.send_headers(headers=sse_headers)

            user = self.scope['user']
            async for event in self.import_prices(data, user):
                await self.send_body(event.encode('utf-8'), more_body=True)

            await self.send_body(b'', more_body=False)
        else:
            await self.send_response(405, json.dumps({'error': 'Method Not Allowed'}).encode('utf-8'), headers=headers + [
                (b'Content-Type', b'application/json'),
            ])

    async def import_prices(self, data, user):
        try:
            security_ids = data.get('securities', [])
            broker_account_ids = data.get('accounts')
            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date() if data.get('start_date') else None
            end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date() if data.get('end_date') else None
            frequency = data.get('frequency')
            single_date = datetime.strptime(data.get('single_date'), '%Y-%m-%d').date() if data.get('single_date') else None
            effective_current_date = parse_date(data.get('effective_current_date'))

            if not effective_current_date:
                raise ValueError("Invalid or missing effective_current_date")

            if single_date:
                dates = [single_date]
                start_date = end_date = single_date
                frequency = 'single'
            else:
                dates = await sync_to_async(generate_dates_for_price_import)(start_date, end_date, frequency)
                
            if len(dates) == 0:
                yield self.format_progress('complete', 0, 0,
                                        message='No dates to import',
                                        start_date=start_date.strftime('%Y-%m-%d'),
                                        end_date=end_date.strftime('%Y-%m-%d'),
                                        frequency=frequency)
                return

            if broker_account_ids:
                @database_sync_to_async
                def get_securities_from_accounts():
                    broker_accounts = BrokerAccounts.objects.filter(
                        id__in=broker_account_ids, 
                        broker__investor=user
                    ).prefetch_related(
                        Prefetch('securities', queryset=Assets.objects.all(), to_attr='all_securities')
                    )
                    securities = []
                    for account in broker_accounts:
                        securities.extend(account.all_securities)
                    return list(set(securities))  # Remove duplicates

                securities = await get_securities_from_accounts()
                # Filter securities with positive positions
                securities = [
                    security for security in securities
                    if await database_sync_to_async(security.position)(
                        effective_current_date, 
                        user, 
                        broker_account_ids  # Added broker_account_ids parameter
                    ) > 0
                ]
            else:
                securities = await database_sync_to_async(list)(
                    Assets.objects.filter(
                        investors__id=user.id,
                        id__in=security_ids
                    )
                )

            print(f"Filtered securities: {[security.name for security in securities]}")  # For debugging

            total_securities = len(securities)
            total_dates = len(dates)
            total_operations = total_securities * total_dates
            current_operation = 0
            results = []

            for security in securities:
                try:
                    # If security is not an Asset object, fetch it
                    if not isinstance(security, Assets):
                        security = await database_sync_to_async(Assets.objects.get)(id=security.id, investors__id=user.id)
                    
                    if security.data_source == 'FT' and security.update_link:
                        price_generator = import_security_prices_from_ft(security, dates)
                    elif security.data_source == 'YAHOO' and security.yahoo_symbol:
                        price_generator = import_security_prices_from_yahoo(security, dates)
                    elif security.data_source == 'MICEX' and security.secid:
                        price_generator = import_security_prices_from_micex(security, dates)
                    else:
                        error_message = f"No valid data source or update information for {security.name}"
                        results.append({
                            "security_name": security.name,
                            "status": "skipped",
                            "message": error_message
                        })
                        
                        yield self.format_progress('error', current_operation, total_operations, security.name, message=error_message)
                        current_operation += len(dates)
                        continue

                    security_result = {
                        "security_name": security.name,
                        "updated_dates": [],
                        "skipped_dates": [],
                        "errors": []
                    }

                    async for result in price_generator:
                        current_operation += 1

                        if result["status"] == "updated":
                            security_result["updated_dates"].append(result["date"])
                        elif result["status"] == "skipped":
                            security_result["skipped_dates"].append(result["date"])
                        elif result["status"] == "error":
                            security_result["errors"].append(f"{result['date']}: {result['message']}")

                        yield self.format_progress('progress', current_operation, total_operations, security.name, date=result["date"], result=result["status"])

                    results.append(security_result)

                except Assets.DoesNotExist:
                    error_message = f"Security with ID {security.id} not found"
                    results.append(error_message)
                    yield self.format_progress('error', current_operation, total_operations, security.name, message=error_message)
                    current_operation += len(dates)
                except Exception as e:
                    error_message = f"Error updating prices for security {security.name}: {str(e)}"
                    results.append(error_message)
                    yield self.format_progress('error', current_operation, total_operations, security_name=security.name, message=error_message)
                    current_operation += len(dates)

            yield self.format_progress('complete', current_operation, total_operations,
                                    message='Price import process completed',
                                    details=results,
                                    start_date=start_date.strftime('%Y-%m-%d'),
                                    end_date=end_date.strftime('%Y-%m-%d'),
                                    frequency=frequency,
                                    total_dates=len(dates))

        except Exception as e:
            yield self.format_progress('error', 0, 0, message=f"Global error: {str(e)}")                                    

    def format_progress(self, status, current, total, security_name=None, date=None, result=None, message=None, **kwargs):
        progress_data = {
            'status': status,
            'current': current,
            'total': total,
            'progress': (current / total) * 100 if total > 0 else 0,
        }
        if security_name:
            progress_data['security_name'] = security_name
        if date:
            progress_data['date'] = date
        if result:
            progress_data['result'] = result
        if message:
            progress_data['message'] = message
        progress_data.update(kwargs)
        print(f"Progress data: {progress_data}")
        return json.dumps(progress_data) + '\n'

class FXImportConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        headers = [
            (b"Access-Control-Allow-Origin", b"http://localhost:8080"),
            (b"Access-Control-Allow-Methods", b"POST, OPTIONS"),
            (b"Access-Control-Allow-Headers", b"Content-Type, Authorization"),
            (b"Access-Control-Allow-Credentials", b"true"),
        ]

        if self.scope['method'] == 'OPTIONS':
            await self.send_response(200, b'', headers=headers)
            return
        
        if self.scope['method'] == 'POST':
            try:
                data = json.loads(body.decode('utf-8'))
                print("Data in FX importer: ", data)
            except json.JSONDecodeError:
                await self.send_response(400, json.dumps({'error': 'Invalid JSON'}).encode('utf-8'), headers=headers + [
                    (b'Content-Type', b'application/json'),
                ])
                return
            
            sse_headers = headers + [
                (b"Cache-Control", b"no-cache"),
                (b"Content-Type", b"text/event-stream"),
            ]
            await self.send_headers(headers=sse_headers)

            import_option = data.get('import_option')
            user = self.scope['user']
            
            if import_option == 'manual':
                dates = await self.generate_dates(data)
            else:
                await self.send_body(self.format_sse_message({'status': 'initializing', 'message': 'Checking database for existing FX rates'}), more_body=True)
                transaction_dates = await self.get_transaction_dates(user)
                dates = await self.filter_dates_to_update(transaction_dates, import_option, user)
            
            total_dates = len(dates)
            await self.send_body(self.format_sse_message({'status': 'initializing', 'message': 'Preparing for update', 'total': total_dates}), more_body=True)

            async for event in self.generate_events(user, import_option, dates):
                await self.send_body(self.format_sse_message(event), more_body=True)

            await self.send_body(b'', more_body=False)
        else:
            await self.send_response(405, json.dumps({'error': 'Method Not Allowed'}).encode('utf-8'), headers=headers + [
                (b'Content-Type', b'application/json'),
            ])

    def format_sse_message(self, data):
        return f"data: {json.dumps(data)}\n\n".encode('utf-8')

    async def generate_dates(self, data):
        date_type = data.get('date_type')
        if date_type == 'single':
            single_date = parse_date(data.get('single_date'))
            return [single_date] if single_date else []
        elif date_type == 'range':
            start_date = parse_date(data.get('start_date'))
            end_date = parse_date(data.get('end_date'))
            frequency = data.get('frequency')
            if start_date and end_date and frequency:
                return await sync_to_async(generate_dates_for_price_import)(start_date, end_date, frequency)
        return []

    async def generate_events(self, user, import_option, dates_to_update):
        import_id = f"fx_import_{user.id}"
        await sync_to_async(cache.set)(import_id, "running", timeout=3600)

        try:
            total_dates = len(dates_to_update)
            missing_filled = 0
            incomplete_updated = 0
            existing_linked = 0
            message = ""

            for i, date in enumerate(dates_to_update):
                if await sync_to_async(cache.get)(import_id) != "running":
                    yield {'status': 'cancelled'}
                    break
                progress = (i) / total_dates * 100
                formatted_date = await sync_to_async(date_format)(date, "F j, Y")
                    
                yield {
                    'status': 'updating',
                    'progress': progress,
                    'current': i,
                    'message': f"{message}Updating FX rates for {formatted_date}"
                }

                action, result = await self.process_fx_rate(date, user)
                if result == 'missing_filled':
                    missing_filled += 1
                elif result == 'incomplete_updated':
                    incomplete_updated += 1
                elif result == 'existing_linked':
                    existing_linked += 1

                message = f"{action} FX rates for {formatted_date}. "

            if await sync_to_async(cache.get)(import_id) == "running":
                stats = {
                    'totalImported': missing_filled + incomplete_updated + existing_linked,
                    'missingFilled': missing_filled,
                    'incompleteUpdated': incomplete_updated,
                    'existingLinked': existing_linked
                }
                yield {'status': 'completed', 'stats': stats}
        finally:
            await sync_to_async(cache.delete)(import_id)

    @database_sync_to_async
    def get_transaction_dates(self, user):
        return list(Transactions.objects.filter(investor=user).values_list('date', flat=True).distinct())

    @database_sync_to_async
    def filter_dates_to_update(self, transaction_dates, import_option, user):
        dates_to_update = []
        for date in transaction_dates:
            fx_instance = FX.objects.filter(date=date).first()
            if import_option in ['missing', 'both'] and (not fx_instance or user not in fx_instance.investors.all()):
                dates_to_update.append(date)
            elif import_option in ['incomplete', 'both'] and fx_instance and any(getattr(fx_instance, field) is None for field in ['USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']):
                dates_to_update.append(date)
        return dates_to_update

    @database_sync_to_async
    def process_fx_rate(self, date, user):
        fx_instance = FX.objects.filter(date=date).first()
        if not fx_instance:
            FX.update_fx_rate(date, user)
            return "Added", "missing_filled"
        elif user not in fx_instance.investors.all():
            fx_instance.investors.add(user)
            return "Linked existing", "existing_linked"
        elif any(getattr(fx_instance, field) is None for field in ['USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']):
            FX.update_fx_rate(date, user)
            return "Updated", "incomplete_updated"
        else:
            return "Skipped", "skipped"

