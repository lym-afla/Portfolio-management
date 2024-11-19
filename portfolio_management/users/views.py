from django.shortcuts import get_object_or_404
from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES, TINKOFF_ACCOUNT_STATUSES, TINKOFF_ACCOUNT_TYPES
from core.user_utils import FREQUENCY_CHOICES, TIMELINE_CHOICES, prepare_account_choices

from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from common.models import Accounts, Brokers
from users.models import AccountGroup, CustomUser, InteractiveBrokersApiToken, TinkoffApiToken
from users.serializers import (
    TinkoffApiTokenSerializer, InteractiveBrokersApiTokenSerializer,
    AccountGroupSerializer, UserSettingsSerializer, UserSettingsChoicesSerializer
)

from .serializers import AccountGroupSerializer, DashboardSettingsChoicesSerializer, DashboardSettingsSerializer, UserProfileSerializer, UserSerializer, UserSettingsChoicesSerializer, UserSettingsSerializer
from django.contrib.auth import get_user_model

from tinkoff.invest import Client
from tinkoff.invest.exceptions import RequestError

import logging
import cryptography.fernet

User = get_user_model()

logger = logging.getLogger(__name__)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['POST'])
    def create_user(self, request):
        logger.info(f"Create user action called with data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED, headers=headers)
        logger.error(f"Serializer errors: {serializer.errors}")
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout the user by blacklisting the provided refresh token.
        """
        try:
            refresh_token = request.data.get('refresh_token')
            if not refresh_token:
                return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
            
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            logger.info(f"User {request.user.username} has been logged out.")
            return Response({"success": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return Response({"error": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['PUT', 'PATCH'], permission_classes=[IsAuthenticated])
    def edit_profile(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET', 'POST'], permission_classes=[IsAuthenticated])
    def user_settings(self, request):
        """
        GET: Retrieve user settings
        POST: Update user settings
        """
        if request.method == 'GET':
            serializer = UserSettingsSerializer(request.user)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = UserSettingsSerializer(
                request.user,
                data=request.data,
                partial=True,
                context={'request': request}
            )
            if serializer.is_valid():
                serializer.save()
                return Response({
                    'success': True,
                    'data': serializer.data
                })
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def user_settings_choices(self, request):
        choices = {
            'currency_choices': CURRENCY_CHOICES,
            'frequency_choices': FREQUENCY_CHOICES,
            'timeline_choices': TIMELINE_CHOICES,
            'nav_breakdown_choices': NAV_BARCHART_CHOICES,
            'account_choices': prepare_account_choices(request.user)['options'],  # Just get the options
        }
        return Response(choices)
    
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password1 = request.data.get('new_password1')
        new_password2 = request.data.get('new_password2')

        if not user.check_password(old_password):
            return Response({'error': 'Incorrect old password'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password1 != new_password2:
            return Response({'error': 'New passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password1)
        user.save()
        return Response({'success': True, 'message': 'Password changed successfully'})

    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def get_account_choices(self, request):
        """
        Get account choices for the current user.
        Returns structured data with options and current selection.
        """
        user = request.user
        choices_data = prepare_account_choices(user)
        
        return Response(choices_data)

    @action(detail=False, methods=['DELETE'], permission_classes=[IsAuthenticated])
    def delete_account(self, request):
        """
        Delete the authenticated user's account after blacklisting the refresh token.
        """
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            else:
                logger.warning("No refresh token provided for account deletion.")

            user = request.user
            user.delete()
            logger.info(f"User {user.username} has been deleted.")
            return Response({"detail": "User account has been deleted."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error deleting account: {e}")
            return Response({"error": "Failed to delete account."}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def dashboard_settings(self, request):
        user = request.user
        serializer = DashboardSettingsSerializer(user)
        
        # Override table_date with session value if it exists
        data = serializer.data
        session_date = request.session.get('effective_current_date')
        if session_date:
            data['table_date'] = session_date

        choices = {
            'default_currency': CURRENCY_CHOICES,
        }
        choices_serializer = DashboardSettingsChoicesSerializer(choices)

        return Response({
            'settings': data,
            'choices': choices_serializer.data
        })

    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def update_dashboard_settings(self, request):
        user = request.user
        serializer = DashboardSettingsSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def update_user_data_for_new_account(self, request):
        user = request.user
        account_type = request.data.get('type')
        account_id = request.data.get('id')
        
        if account_type not in dict(CustomUser.ACCOUNT_TYPE_CHOICES):
            return Response({
                'success': False,
                'error': f'Invalid account type: {account_type}'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            if account_type == 'all':
                user.selected_account_type = 'all'
                user.selected_account_id = None
            else:
                # Validate that the ID exists for the given type
                if account_type == 'account':
                    exists = Accounts.objects.filter(
                        id=account_id, 
                        broker__investor=user
                    ).exists()
                elif account_type == 'group':
                    exists = AccountGroup.objects.filter(
                        id=account_id, 
                        user=user
                    ).exists()
                elif account_type == 'broker':
                    exists = Brokers.objects.filter(
                        id=account_id, 
                        investor=user
                    ).exists()
                else:
                    exists = False

                if not exists:
                    return Response({
                        'success': False,
                        'error': f'Invalid {account_type} ID: {account_id}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                user.selected_account_type = account_type
                user.selected_account_id = account_id

            user.save()
            
            return Response({
                'success': True,
                'message': 'Account selection updated successfully',
                'selected': {
                    'type': user.selected_account_type,
                    'id': user.selected_account_id
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def broker_tokens(self, request):
        """Get all broker tokens for the user"""
        tinkoff_tokens = TinkoffApiToken.objects.filter(user=request.user)
        ib_tokens = InteractiveBrokersApiToken.objects.filter(user=request.user)
        
        return Response({
            'tinkoff_tokens': TinkoffApiTokenSerializer(tinkoff_tokens, many=True).data,
            'ib_tokens': InteractiveBrokersApiTokenSerializer(ib_tokens, many=True).data
        })

    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def revoke_token(self, request):
        """Revoke (deactivate) a specific broker token"""
        token_type = request.data.get('token_type')
        token_id = request.data.get('token_id')
        
        if token_type == 'tinkoff':
            token = get_object_or_404(TinkoffApiToken, id=token_id, user=request.user)
        elif token_type == 'ib':
            token = get_object_or_404(InteractiveBrokersApiToken, id=token_id, user=request.user)
        else:
            return Response(
                {'error': 'Invalid token type'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        token.is_active = False
        token.save()
        return Response({'message': 'Token revoked successfully'})

class BaseApiTokenViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        # Use set_token method to properly encrypt the token
        instance.set_token(serializer.validated_data['token'], self.request.user)
        instance.save()

    def perform_update(self, serializer):
        instance = serializer.save(user=self.request.user)
        if 'token' in serializer.validated_data:
            # Only update token if it was provided
            instance.set_token(serializer.validated_data['token'], self.request.user)
            instance.save()

    @action(detail=True, methods=['POST'])
    def test_connection(self, request, pk=None):
        """Test connection with saved token"""
        token_instance = self.get_object()
        try:
            # Get decrypted token
            decrypted_token = token_instance.get_token(request.user)
            logger.debug(f"Testing connection for token ID {pk}")
            
            # Create a mock request with the token
            mock_request = type('MockRequest', (), {
                'data': {'token': decrypted_token},
                'user': request.user
            })
            
            # Reuse verify_token method
            response = self.verify_token(mock_request)
            
            # Update token status based on verification result
            token_instance.is_active = response.status_code == 200
            token_instance.save()
            
            # Add token data to response
            response.data['token'] = self.get_serializer(token_instance).data
            
            return response
            
        except ValueError as e:
            logger.error(f"Value error testing connection: {str(e)}")
            token_instance.is_active = False
            token_instance.save()
            return Response({
                'error': str(e),
                'token': self.get_serializer(token_instance).data
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except cryptography.fernet.InvalidToken:
            logger.error(f"Invalid token for user {request.user.id}, token ID {pk}")
            token_instance.is_active = False
            token_instance.save()
            return Response({
                'error': 'Unable to decrypt token. Please try saving the token again.',
                'token': self.get_serializer(token_instance).data
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            token_instance.is_active = False
            token_instance.save()
            return Response({
                'error': 'An error occurred while testing the connection',
                'token': self.get_serializer(token_instance).data
            }, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, *args, **kwargs):
        """Only allow deletion of inactive tokens"""
        instance = self.get_object()
        if instance.is_active:
            return Response(
                {'error': 'Cannot delete active token. Deactivate it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

class TinkoffApiTokenViewSet(BaseApiTokenViewSet):
    queryset = TinkoffApiToken.objects.all()
    serializer_class = TinkoffApiTokenSerializer

    @action(detail=False, methods=['POST'])
    def verify_token(self, request):
        """Verify Tinkoff API token by making a test API call"""
        token = request.data.get('token')
        logger.info(f"Verifying Tinkoff token for user {request.user.username}")
        
        if not token:
            logger.warning("Token verification failed: No token provided")
            return Response(
                {'error': 'Token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with Client(token) as client:
                logger.debug("Attempting to connect to Tinkoff API")
                accounts = client.users.get_accounts()
                logger.info(f"Token verification successful. Found {len(accounts.accounts)} accounts")
                
                formatted_accounts = []
                for account in accounts.accounts:
                    formatted_account = {
                        'id': account.id,
                        'name': account.name,
                        'type': TINKOFF_ACCOUNT_TYPES.get(account.type.value, 'UNKNOWN'),
                        'status': TINKOFF_ACCOUNT_STATUSES.get(account.status.value, 'UNKNOWN'),
                        'access_level': account.access_level.name,
                        'opened_date': account.opened_date.isoformat() if account.opened_date else None,
                        'closed_date': account.closed_date.isoformat() if account.closed_date else None
                    }
                    formatted_accounts.append(formatted_account)
                
                return Response({
                    'valid': True,
                    'message': 'Token is valid',
                    'accounts': formatted_accounts
                })

        except RequestError as e:
            logger.error(f"Tinkoff API RequestError: {str(e)}")
            error_code = e.args[1] if len(e.args) > 1 else 'unknown'
            metadata = e.args[2] if len(e.args) > 2 else None
            error_message = metadata.message if metadata and hasattr(metadata, 'message') else 'Unknown error'
            
            return Response({
                'valid': False,
                'error': error_message,
                'error_code': error_code
            }, status=status.HTTP_401_UNAUTHORIZED if error_code == '40003' else status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.exception("Unexpected error during token verification")
            return Response({
                'valid': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['POST'])
    def save_read_only_token(self, request):
        """Save read-only token after validation"""
        try:
            new_token = request.data.get('token')
            token_type = request.data.get('token_type')
            sandbox_mode = request.data.get('sandbox_mode')
            broker_id = request.data.get('broker')  # Get broker ID from request
            
            # Verify broker exists and belongs to user
            try:
                broker = Brokers.objects.get(id=broker_id, investor=request.user)
            except Brokers.DoesNotExist:
                return Response(
                    {'error': 'Invalid broker selection'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify the new token first
            response = self.verify_token(request)
            if response.status_code != 200:
                return response

            # Check for existing identical token
            existing_tokens = TinkoffApiToken.objects.filter(
                user=request.user,
                broker=broker,  # Add broker to filter
                token_type=token_type,
                sandbox_mode=sandbox_mode
            )
            
            # Check if the exact same token already exists
            for token in existing_tokens:
                try:
                    if token.get_token(request.user) == new_token:
                        if not token.is_active:
                            # Reactivate the token
                            token.is_active = True
                            token.save()  # Model's save method will handle deactivating other tokens
                            return Response({
                                'message': 'Existing token has been reactivated',
                                'data': self.get_serializer(token).data,
                                'id': token.id
                            }, status=status.HTTP_200_OK)
                        else:
                            return Response({
                                'message': 'This exact token is already active',
                                'data': self.get_serializer(token).data
                            }, status=status.HTTP_400_BAD_REQUEST)
                except Exception:
                    continue  # Skip tokens that can't be decrypted

            # Create new token if no existing token found
            token_data = {
                'broker': broker.id,  # Add broker ID
                'token': new_token,
                'token_type': token_type,
                'sandbox_mode': sandbox_mode
            }

            serializer = self.get_serializer(data=token_data)
            
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response({
                    'message': 'Token saved successfully',
                    'data': serializer.data,
                    'id': serializer.instance.id
                }, status=status.HTTP_200_OK)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error saving read-only token: {str(e)}")
            return Response({
                'error': 'An error occurred while saving the token'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class InteractiveBrokersApiTokenViewSet(BaseApiTokenViewSet):
    queryset = InteractiveBrokersApiToken.objects.all()
    serializer_class = InteractiveBrokersApiTokenSerializer

class AccountGroupViewSet(viewsets.ModelViewSet):
    serializer_class = AccountGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AccountGroup.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        groups_data = self.get_serializer(queryset, many=True).data
        
        # Get available broker accounts for the user
        available_accounts = Accounts.objects.filter(broker__investor=request.user)
        account_choices = [
            {
                'value': account.id, 
                'title': account.name,
            }
            for account in available_accounts
        ]

        return Response({
            'groups': {
                str(group['id']): {
                    'name': group['name'],
                    'accounts': group['accounts']
                }
                for group in groups_data
            },
            'available_accounts': account_choices
        })

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['POST'])
    def add_accounts(self, request, pk=None):
        group = self.get_object()
        account_ids = request.data.get('account_ids', [])
        
        try:
            accounts = Accounts.objects.filter(
                id__in=account_ids,
                broker__investor=request.user
            )
            group.accounts.add(*accounts)
            return Response({'status': 'accounts added'})
        except Exception as e:
            return Response(
                {'error': f'Failed to add accounts: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['POST'])
    def remove_accounts(self, request, pk=None):
        group = self.get_object()
        account_ids = request.data.get('account_ids', [])
        
        try:
            accounts = Accounts.objects.filter(
                id__in=account_ids,
                broker__investor=request.user
            )
            group.accounts.remove(*accounts)
            return Response({'status': 'accounts removed'})
        except Exception as e:
            return Response(
                {'error': f'Failed to remove accounts: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
