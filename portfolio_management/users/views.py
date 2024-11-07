from django.shortcuts import get_object_or_404
from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES, TINKOFF_ACCOUNT_STATUSES, TINKOFF_ACCOUNT_TYPES
from core.user_utils import FREQUENCY_CHOICES, TIMELINE_CHOICES, get_broker_choices

from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import InteractiveBrokersApiToken, TinkoffApiToken
from users.serializers import TinkoffApiTokenSerializer, InteractiveBrokersApiTokenSerializer

from .serializers import DashboardSettingsChoicesSerializer, DashboardSettingsSerializer, UserProfileSerializer, UserSerializer, UserSettingsChoicesSerializer, UserSettingsSerializer
from django.contrib.auth import get_user_model

from tinkoff.invest import Client
from tinkoff.invest.exceptions import RequestError

import logging

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
        if request.method == 'GET':
            serializer = UserSettingsSerializer(request.user)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = UserSettingsSerializer(request.user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({'success': True, 'data': serializer.data})
            return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def user_settings_choices(self, request):
        choices = {
            'currency_choices': CURRENCY_CHOICES,
            'frequency_choices': FREQUENCY_CHOICES,
            'timeline_choices': TIMELINE_CHOICES,
            'nav_breakdown_choices': NAV_BARCHART_CHOICES,
            'broker_choices': get_broker_choices(request.user),
        }
        serializer = UserSettingsChoicesSerializer(choices)
        return Response(serializer.data)
    
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
    def get_broker_choices(self, request):
        user = request.user
        broker_choices = get_broker_choices(user)
        
        return Response({
            'options': broker_choices,
            'custom_brokers': user.custom_brokers
        })

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
    def update_data_for_new_broker(self, request):
        user = request.user
        broker_or_group_name = request.data.get('broker_or_group_name')
        
        if broker_or_group_name:
            user.custom_brokers = broker_or_group_name
            user.save()
            return Response({
                'success': True,
                'message': 'Broker or group updated successfully',
                'custom_brokers': user.custom_brokers
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': 'Broker or group name not provided'
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
        serializer.save(user=self.request.user)

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
        """Save read-only token after verification"""
        token = request.data.get('token')
        logger.info(f"Attempting to save read-only token for user {request.user.username}")

        # First verify the token
        verification = self.verify_token(request)
        logger.info(f"Token verification response status: {verification.status_code}")
        logger.debug(f"Verification response data: {verification.data}")
        
        if verification.status_code != 200:
            logger.warning("Token verification failed, returning verification response")
            return verification

        data = {
            'token': token,
            'token_type': 'read_only',
            'sandbox_mode': False  # Default to False since we're removing sandbox functionality
        }
        
        # Check for existing token
        existing_token = self.get_queryset().filter(
            token_type='read_only'
        ).first()
        
        if existing_token:
            logger.info("Updating existing token")
            serializer = self.get_serializer(existing_token, data=data, partial=True)
        else:
            logger.info("Creating new token")
            serializer = self.get_serializer(data=data)
            
        if serializer.is_valid():
            logger.info("Token data valid, saving")
            serializer.save(user=request.user)
            return Response({
                'message': 'Token saved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        
        logger.error(f"Serializer validation failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['POST'])
    def test_connection(self, request, pk=None):
        """Test connection with saved token"""
        token = self.get_object()
        # Create a mock request with the token
        mock_request = type('MockRequest', (), {
            'data': {'token': token.get_token()},
            'user': request.user
        })
        
        # Reuse verify_token method
        return self.verify_token(mock_request)

class InteractiveBrokersApiTokenViewSet(BaseApiTokenViewSet):
    queryset = InteractiveBrokersApiToken.objects.all()
    serializer_class = InteractiveBrokersApiTokenSerializer