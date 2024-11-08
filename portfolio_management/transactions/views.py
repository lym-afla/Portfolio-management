import os
import logging
import re
import uuid

from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.conf import settings
import pandas as pd
from channels.db import database_sync_to_async
from fuzzywuzzy import fuzz

from common.models import Brokers, FXTransaction, Transactions
from core.transactions_utils import get_transactions_table_api
from core.import_utils import get_broker, parse_charles_stanley_transactions, parse_galaxy_broker_cash_flows, parse_galaxy_broker_security_transactions
from constants import BROKER_IDENTIFIERS, CHARLES_STANLEY_BROKER, CURRENCY_CHOICES
from .serializers import TransactionFormSerializer, FXTransactionFormSerializer

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import status, viewsets

logger = logging.getLogger(__name__)

class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionFormSerializer
    queryset = Transactions.objects.all()

    def get_queryset(self):
        return self.queryset.filter(investor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    def get_object(self):
        transaction_id = self.kwargs.get('pk')
        try:
            return Transactions.objects.get(id=transaction_id, investor=self.request.user)
        except Transactions.DoesNotExist:
            raise NotFound(f"Transaction with id {transaction_id} not found.")

    @action(detail=False, methods=['POST'])    
    def get_transactions_table(self, request):
        return Response(get_transactions_table_api(request))

    @action(detail=False, methods=['GET'])
    def form_structure(self, request):
        form_serializer = TransactionFormSerializer()
        return Response({
            'fields': [
                {
                    'name': 'id',
                    'label': 'ID',
                    'type': 'hidden',
                    'required': False,
                },
                {
                    'name': 'date',
                    'label': 'Date',
                    'type': 'datepicker',
                    'required': True,
                },
                {
                    'name': 'broker',
                    'label': 'Broker',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_broker_choices(request.user)
                },
                {
                    'name': 'security',
                    'label': 'Select Security',
                    'type': 'select',
                    'required': False,
                    'choices': form_serializer.get_security_choices(request.user)
                },
                {
                    'name': 'currency',
                    'label': 'Currency',
                    'type': 'select',
                    'required': True,
                    'choices': [{'value': currency[0], 'text': f"{currency[1]} ({currency[0]})"} for currency in CURRENCY_CHOICES]
                },
                {
                    'name': 'type',
                    'label': 'Type',
                    'type': 'select',
                    'required': True,
                    'choices': [{'value': type[0], 'text': type[0]} for type in Transactions._meta.get_field('type').choices if type[0]]
                },
                {
                    'name': 'quantity',
                    'label': 'Quantity',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'price',
                    'label': 'Price',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'cash_flow',
                    'label': 'Cash Flow',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'commission',
                    'label': 'Commission',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'comment',
                    'label': 'Comment',
                    'type': 'textarea',
                    'required': False,
                },
            ]
        })

    def search_keywords_in_excel(self, file_path):
        df = pd.read_excel(file_path)
        content = df.to_string().lower()
        return content

    def identify_broker(self, content, user):
        logger.info(f"Starting broker identification for user {user.id}")
        best_match = None
        best_score = 0
        perfect_match_threshold = 100
        # content_limit = 10000  # Limit content to first 10,000 characters

        # Limit the content size
        lower_content = content.lower()
        logger.debug(f"Content length: {len(lower_content)} characters")

        for broker_name, config in BROKER_IDENTIFIERS.items():
            logger.debug(f"Checking broker: {broker_name}")
            keywords = config['keywords']
            threshold = config['fuzzy_threshold']
            
            broker_scores = []
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
                
                broker_scores.append(keyword_best_score)
                if keyword_best_score < perfect_match_threshold:
                    all_keywords_perfect = False
                
                logger.debug(f"Best score for keyword '{keyword}': {keyword_best_score}")

            # Calculate the average score for this broker
            avg_score = sum(broker_scores) / len(broker_scores)
            logger.info(f"Average score for broker {broker_name}: {avg_score}")

            if all_keywords_perfect:
                logger.info(f"Perfect match found for all keywords of broker {broker_name}")
                try:
                    broker = Brokers.objects.get(investor=user, name__iexact=broker_name)
                    logger.info(f"Returning perfectly matched broker: {broker.name} (ID: {broker.id})")
                    return broker
                except Brokers.DoesNotExist:
                    logger.warning(f"Perfect match found for {broker_name}, but no corresponding Broker object exists for this user")
                    return None

            if avg_score > threshold and avg_score > best_score:
                best_score = avg_score
                best_match = broker_name
                logger.debug(f"New best match: {best_match} with average score {best_score}")

        if best_match:
            logger.info(f"Best match found: {best_match} with average score {best_score}")
            try:
                broker = Brokers.objects.get(investor=user, name__iexact=best_match)
                logger.info(f"Returning best matched broker: {broker.name} (ID: {broker.id})")
                return broker
            except Brokers.DoesNotExist:
                logger.warning(f"Best match {best_match} found, but no corresponding Broker object exists for this user")
                return None
        
        logger.info("No broker match found")
        return None

    @action(detail=False, methods=['POST'])
    def analyze_file(self, request):
        if 'file' not in request.FILES:
            return Response({'error': 'No file was uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['file']
        file_id = str(uuid.uuid4())
        file_name = f"temp_{file_id}_{file.name}"
        temp_storage = FileSystemStorage(location=settings.TEMP_FILE_DIR)
        saved_file_name = temp_storage.save(file_name, file)
        file_path = os.path.join(settings.TEMP_FILE_DIR, saved_file_name)
        logger.info(f"File saved at: {file_path}")

        try:
            logger.debug(f"Request data: {request.data}")
            if request.data.get('is_galaxy') == 'true':
                return Response({
                    'status': 'broker_not_identified',
                    'message': 'Galaxy file detected.',
                    'fileId': file_id
                }, status=status.HTTP_200_OK)
            
            content = self.search_keywords_in_excel(file_path)
            identified_broker = self.identify_broker(content, request.user)

            if identified_broker:
                return Response({
                    'status': 'broker_identified',
                    'message': 'Broker was automatically identified.',
                    'fileId': file_id,
                    'identifiedBroker': {'id': identified_broker.id, 'name': identified_broker.name}
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'status': 'broker_not_identified',
                    'message': 'The broker could not be automatically identified from the file.',
                    'fileId': file_id
                }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    async def import_transactions(self, user, file_id, broker_id, confirm_every, currency, is_galaxy, galaxy_type):
        logger.debug("Starting import_transactions")
        file_path = None
        try:
            file_path, broker_id = await self.validate_import_data(file_id, broker_id)
            broker = await get_broker(broker_id)

            if is_galaxy:
                if not currency:
                    raise ValueError("Currency is required for Galaxy imports")
                    
                if galaxy_type == 'cash':
                    async for update in parse_galaxy_broker_cash_flows(file_path, currency, broker, user, confirm_every):
                        yield update
                else:
                    async for update in parse_galaxy_broker_security_transactions(file_path, currency, broker, user, confirm_every):
                        yield update

            elif CHARLES_STANLEY_BROKER in broker.name:
                async for update in parse_charles_stanley_transactions(file_path, 'GBP', broker_id, user.id, confirm_every):
                    yield update
            else:
                yield {'status': 'critical_error', 'message': f'Unsupported broker for import: {broker.name}'}

        except Exception as e:
            logger.error(f"Error in import_transactions: {str(e)}", exc_info=True)
            yield {'status': 'critical_error', 'message': f'An error occurred during import: {str(e)}'}
        finally:
            logger.debug("Finishing import_transactions")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Temporary file deleted: {file_path}")

    @database_sync_to_async
    def validate_import_data(self, file_id, broker_id):
        if not file_id or not isinstance(file_id, str):
            raise ValidationError("Invalid file ID")

        try:
            broker_id = int(broker_id)
        except ValueError:
            raise ValidationError("Invalid broker ID")

        temp_storage = FileSystemStorage(location=settings.TEMP_FILE_DIR)
        matching_files = [f for f in temp_storage.listdir('')[1] if f.startswith(f"temp_{file_id}_")]

        if not matching_files:
            raise ValidationError("No matching file found for the given file ID")
        elif len(matching_files) > 1:
            raise ValidationError("Multiple matching files found. Please try again")

        file_path = os.path.join(settings.TEMP_FILE_DIR, matching_files[0])

        # Validate file extension
        allowed_extensions = ['xlsx', 'xls', 'csv']
        file_extension = os.path.splitext(file_path)[1][1:].lower()
        if file_extension not in allowed_extensions:
            raise ValidationError(f"Invalid file type. Allowed types are: {', '.join(allowed_extensions)}")

        return file_path, broker_id

    @database_sync_to_async
    def save_transactions(self, transactions_to_create):
        with transaction.atomic():
            Transactions.objects.bulk_create([Transactions(**data) for data in transactions_to_create])

    # @database_sync_to_async
    # def transaction_exists(self, transaction_data):
    #     query = Q()
    #     required_fields = ['investor', 'broker', 'date', 'currency', 'type']
    #     optional_fields = ['security', 'quantity', 'price', 'cash_flow', 'commission']

    #     # Add required fields to the query
    #     for field in required_fields:
    #         if field not in transaction_data:
    #             raise ValueError(f"Required field '{field}' is missing from transaction_data")
    #         query &= Q(**{field: transaction_data[field]})

    #     # Add optional fields to the query if they exist
    #     for field in optional_fields:
    #         if field in transaction_data and transaction_data[field] is not None:
    #             query &= Q(**{field: transaction_data[field]})

    #     return Transactions.objects.filter(query).exists()

class FXTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = FXTransactionFormSerializer
    queryset = FXTransaction.objects.all()

    def get_queryset(self):
        return self.queryset.filter(investor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=['POST'])
    def create_fx_transaction(self, request):
        print("Received data:", request.data)  # Debug print
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        print("Serializer errors:", serializer.errors)  # Debug print
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'])
    def form_structure(self, request):
        form_serializer = FXTransactionFormSerializer()
        
        return Response({
            'fields': [
                {
                    'name': 'date',
                    'label': 'Date',
                    'type': 'datepicker',
                    'required': True,
                },
                {
                    'name': 'broker',
                    'label': 'Broker',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_broker_choices(request.user)
                },
                {
                    'name': 'from_currency',
                    'label': 'From Currency',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_currency_choices()
                },
                {
                    'name': 'from_amount',
                    'label': 'From Amount',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'to_currency',
                    'label': 'To Currency',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_currency_choices()
                },
                {
                    'name': 'to_amount',
                    'label': 'To Amount',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'commission_currency',
                    'label': 'Commission Currency',
                    'type': 'select',
                    'required': False,
                    'choices': form_serializer.get_currency_choices()
                },
                {
                    'name': 'commission',
                    'label': 'Commission',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'comment',
                    'label': 'Comment',
                    'type': 'textarea',
                    'required': False,
                },
            ]
        })