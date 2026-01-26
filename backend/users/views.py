"""Users views."""

import logging
from datetime import date

import cryptography.fernet
import structlog
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from t_tech.invest import Client
from t_tech.invest.exceptions import RequestError

from common.models import Accounts, Brokers
from constants import (
    ACCOUNT_TYPE_CHOICES,
    CURRENCY_CHOICES,
    FREQUENCY_CHOICES,
    NAV_BARCHART_CHOICES,
    TIMELINE_CHOICES,
    TINKOFF_ACCOUNT_STATUSES,
    TINKOFF_ACCOUNT_TYPES,
)
from core.user_utils import prepare_account_choices
from users.models import AccountGroup, InteractiveBrokersApiToken, TinkoffApiToken
from users.serializers import (
    AccountGroupSerializer,
    CustomTokenObtainPairSerializer,
    DashboardSettingsChoicesSerializer,
    DashboardSettingsSerializer,
    InteractiveBrokersApiTokenSerializer,
    TinkoffApiTokenSerializer,
    UserProfileSerializer,
    UserSerializer,
    UserSettingsSerializer,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    """User viewset."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=["POST"])
    def create_user(self, request):
        """Create user."""
        logger.info(f"Create user action called with data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                {"message": "User registered successfully"},
                status=status.HTTP_201_CREATED,
                headers=headers,
            )
        logger.error(f"Serializer errors: {serializer.errors}")
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=["POST"], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout the user by blacklisting the provided refresh token.

        Clear session data including effective_current_date.
        """
        try:
            refresh_token = request.data.get("refresh_token")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token = RefreshToken(refresh_token)
            token.blacklist()

            # Clear session data (including effective_current_date)
            request.session.flush()

            logger.info(f"User {request.user.username} has been logged out.")
            return Response(
                {"success": "Logged out successfully."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return Response(
                {"error": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["GET"], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get user profile."""
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    @action(
        detail=False, methods=["PUT", "PATCH"], permission_classes=[IsAuthenticated]
    )
    def edit_profile(self, request):
        """Edit user profile."""
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["GET", "POST"], permission_classes=[IsAuthenticated])
    def user_settings(self, request):
        """
        User settings view.

        GET: Retrieve user settings
        POST: Update user settings
        """
        if request.method == "GET":
            serializer = UserSettingsSerializer(request.user)
            return Response(serializer.data)
        elif request.method == "POST":
            serializer = UserSettingsSerializer(
                request.user,
                data=request.data,
                partial=True,
                context={"request": request},
            )
            if serializer.is_valid():
                serializer.save()
                return Response({"success": True, "data": serializer.data})
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["GET"], permission_classes=[IsAuthenticated])
    def user_settings_choices(self, request):
        """Get user settings choices."""
        choices = {
            "currency_choices": CURRENCY_CHOICES,
            "frequency_choices": FREQUENCY_CHOICES,
            "timeline_choices": TIMELINE_CHOICES,
            "nav_breakdown_choices": NAV_BARCHART_CHOICES,
            "account_choices": prepare_account_choices(request.user)[
                "options"
            ],  # Just get the options
        }
        return Response(choices)

    @action(detail=False, methods=["POST"], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Change user password."""
        user = request.user
        old_password = request.data.get("old_password")
        new_password1 = request.data.get("new_password1")
        new_password2 = request.data.get("new_password2")

        if not user.check_password(old_password):
            return Response(
                {"error": "Incorrect old password"}, status=status.HTTP_400_BAD_REQUEST
            )

        if new_password1 != new_password2:
            return Response(
                {"error": "New passwords do not match"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password1)
        user.save()
        return Response({"success": True, "message": "Password changed successfully"})

    @action(detail=False, methods=["GET"], permission_classes=[IsAuthenticated])
    def get_account_choices(self, request):
        """
        Get account choices for the current user.

        Returns structured data with options and current selection.
        """
        user = request.user
        choices_data = prepare_account_choices(user)

        return Response(choices_data)

    @action(detail=False, methods=["DELETE"], permission_classes=[IsAuthenticated])
    def delete_account(self, request):
        """
        Delete account view.

        Delete the authenticated user's account after blacklisting the refresh token.
        """
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            else:
                logger.warning("No refresh token provided for account deletion.")

            user = request.user
            user.delete()
            logger.info(f"User {user.username} has been deleted.")
            return Response(
                {"detail": "User account has been deleted."}, status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error deleting account: {e}")
            return Response(
                {"error": "Failed to delete account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["GET"], permission_classes=[IsAuthenticated])
    def dashboard_settings(self, request):
        """Get dashboard settings."""
        user = request.user
        serializer = DashboardSettingsSerializer(user)

        # Override table_date with JWT middleware value if it exists
        data = serializer.data
        effective_date = getattr(request, "effective_current_date", None)
        if effective_date:
            data["table_date"] = effective_date
            logger.info(
                "[JWT_DEBUG] Using effective_date from JWT middleware: %s",
                effective_date,
            )
        else:
            logger.info(
                "[JWT_DEBUG] No effective_date in request, using serializer default"
            )

        choices = {
            "default_currency": CURRENCY_CHOICES,
        }
        choices_serializer = DashboardSettingsChoicesSerializer(choices)

        return Response({"settings": data, "choices": choices_serializer.data})

    @action(detail=False, methods=["POST"], permission_classes=[IsAuthenticated])
    def update_dashboard_settings(self, request):
        """Update dashboard settings."""
        logger = logging.getLogger("users.views")
        logger.info(
            "[JWT_DEBUG] update_dashboard_settings called with data: %s", request.data
        )
        logger.info(
            "[JWT_DEBUG] Effective date from request: %s",
            getattr(request, "effective_current_date", "NOT_SET"),
        )

        user = request.user
        serializer = DashboardSettingsSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            # Save user model fields (currency, digits)
            serializer.save()

            # Get table_date from request data
            table_date = request.data.get("table_date")
            if table_date:
                logger.info(
                    "[JWT_DEBUG] Setting effective_current_date to: %s", table_date
                )

                # Check if effective_date is changing
                current_effective_date = getattr(
                    request, "effective_current_date", None
                )
                effective_date_changed = current_effective_date != table_date

                # Store it in response - JWT middleware will handle adding it to
                # new tokens
                response_data = serializer.data
                response_data["table_date"] = table_date
                response_data["effective_current_date"] = table_date

                # Signal that token refresh is needed if effective_date changed
                if effective_date_changed:
                    response_data["requires_token_refresh"] = True
                    response_data["new_effective_date"] = table_date
                    logger.info(
                        "[JWT_DEBUG] Effective date changed,"
                        "requesting token refresh: %s",
                        table_date,
                    )

                logger.info("[JWT_DEBUG] Response data: %s", response_data)

                return Response(response_data)
            else:
                # No table_date provided, return current effective_date from request
                response_data = serializer.data
                response_data["table_date"] = getattr(
                    request, "effective_current_date", date.today().isoformat()
                )
                logger.info(
                    "[JWT_DEBUG] No table_date provided, using current: %s",
                    response_data["table_date"],
                )
                return Response(response_data)
        else:
            logger.error("[JWT_DEBUG] Serializer errors: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"], permission_classes=[IsAuthenticated])
    def update_user_data_for_new_account(self, request):
        """Update user data for a new account."""
        user = request.user
        account_type = request.data.get("type")
        account_id = request.data.get("id")

        if account_type not in dict(ACCOUNT_TYPE_CHOICES):
            return Response(
                {"success": False, "error": f"Invalid account type: {account_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if account_type == "all":
                user.selected_account_type = "all"
                user.selected_account_id = None
            else:
                # Validate that the ID exists for the given type
                if account_type == "account":
                    exists = Accounts.objects.filter(
                        id=account_id, broker__investor=user
                    ).exists()
                elif account_type == "group":
                    exists = AccountGroup.objects.filter(
                        id=account_id, user=user
                    ).exists()
                elif account_type == "broker":
                    exists = Brokers.objects.filter(
                        id=account_id, investor=user
                    ).exists()
                else:
                    exists = False

                if not exists:
                    return Response(
                        {
                            "success": False,
                            "error": f"Invalid {account_type} ID: {account_id}",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                user.selected_account_type = account_type
                user.selected_account_id = account_id

            user.save()

            return Response(
                {
                    "success": True,
                    "message": "Account selection updated successfully",
                    "selected": {
                        "type": user.selected_account_type,
                        "id": user.selected_account_id,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["GET"], permission_classes=[IsAuthenticated])
    def broker_tokens(self, request):
        """Get all broker tokens for the user."""
        tinkoff_tokens = TinkoffApiToken.objects.filter(user=request.user)
        ib_tokens = InteractiveBrokersApiToken.objects.filter(user=request.user)

        return Response(
            {
                "tinkoff_tokens": TinkoffApiTokenSerializer(
                    tinkoff_tokens, many=True
                ).data,
                "ib_tokens": InteractiveBrokersApiTokenSerializer(
                    ib_tokens, many=True
                ).data,
            }
        )

    @action(detail=False, methods=["POST"], permission_classes=[IsAuthenticated])
    def revoke_token(self, request):
        """Revoke (deactivate) a specific broker token."""
        token_type = request.data.get("token_type")
        token_id = request.data.get("token_id")

        if token_type == "tinkoff":
            token = get_object_or_404(TinkoffApiToken, id=token_id, user=request.user)
        elif token_type == "ib":
            token = get_object_or_404(
                InteractiveBrokersApiToken, id=token_id, user=request.user
            )
        else:
            return Response(
                {"error": "Invalid token type"}, status=status.HTTP_400_BAD_REQUEST
            )

        token.is_active = False
        token.save()
        return Response({"message": "Token revoked successfully"})


class BaseApiTokenViewSet(viewsets.ModelViewSet):
    """Base viewset for API tokens."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get queryset for API tokens."""
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        """Perform create action."""
        instance = serializer.save(user=self.request.user)
        # Use set_token method to properly encrypt the token
        instance.set_token(serializer.validated_data["token"], self.request.user)
        instance.save()

    def perform_update(self, serializer):
        """Perform update action."""
        instance = serializer.save(user=self.request.user)
        if "token" in serializer.validated_data:
            # Only update token if it was provided
            instance.set_token(serializer.validated_data["token"], self.request.user)
            instance.save()

    @action(detail=True, methods=["POST"])
    def test_connection(self, request, pk=None):
        """Test connection with saved token."""
        token_instance = self.get_object()
        try:
            # Get decrypted token
            decrypted_token = token_instance.get_token(request.user)
            logger.debug(f"Testing connection for token ID {pk}")

            # Create a mock request with the token
            mock_request = type(
                "MockRequest",
                (),
                {"data": {"token": decrypted_token}, "user": request.user},
            )

            # Reuse verify_token method
            response = self.verify_token(mock_request)

            # Update token status based on verification result
            token_instance.is_active = response.status_code == 200
            token_instance.save()

            # Add token data to response
            response.data["token"] = self.get_serializer(token_instance).data

            return response

        except ValueError as e:
            logger.error(f"Value error testing connection: {str(e)}")
            token_instance.is_active = False
            token_instance.save()
            return Response(
                {"error": str(e), "token": self.get_serializer(token_instance).data},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except cryptography.fernet.InvalidToken:
            logger.error(f"Invalid token for user {request.user.id}, token ID {pk}")
            token_instance.is_active = False
            token_instance.save()
            return Response(
                {
                    "error": (
                        "Unable to decrypt token. Please try saving the token again.",
                    ),
                    "token": self.get_serializer(token_instance).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            token_instance.is_active = False
            token_instance.save()
            return Response(
                {
                    "error": ("An error occurred while testing the connection",),
                    "token": self.get_serializer(token_instance).data,
                },
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request, *args, **kwargs):
        """Allow only deletion of inactive tokens."""
        instance = self.get_object()
        if instance.is_active:
            return Response(
                {"error": ("Cannot delete active token. Deactivate it first.",)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TinkoffApiTokenViewSet(BaseApiTokenViewSet):
    """Viewset for Tinkoff API tokens."""

    queryset = TinkoffApiToken.objects.all()
    serializer_class = TinkoffApiTokenSerializer

    @action(detail=False, methods=["POST"])
    def verify_token(self, request):
        """Verify Tinkoff API token by making a test API call."""
        token = request.data.get("token")
        logger.info(f"Verifying Tinkoff token for user {request.user.username}")

        if not token:
            logger.warning("Token verification failed: No token provided")
            return Response(
                {"error": ("Token is required",)}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with Client(token) as client:
                logger.debug("Attempting to connect to Tinkoff API")
                accounts = client.users.get_accounts()
                logger.info(
                    "Token verification successful. "
                    f"Found {len(accounts.accounts)} accounts"
                )

                formatted_accounts = []
                for account in accounts.accounts:
                    formatted_account = {
                        "id": account.id,
                        "name": account.name,
                        "type": TINKOFF_ACCOUNT_TYPES.get(
                            account.type.value, "UNKNOWN"
                        ),
                        "status": TINKOFF_ACCOUNT_STATUSES.get(
                            account.status.value, "UNKNOWN"
                        ),
                        "access_level": account.access_level.name,
                        "opened_date": (
                            account.opened_date.isoformat()
                            if account.opened_date
                            else None
                        ),
                        "closed_date": (
                            account.closed_date.isoformat()
                            if account.closed_date
                            else None
                        ),
                    }
                    formatted_accounts.append(formatted_account)

                return Response(
                    {
                        "valid": True,
                        "message": "Token is valid",
                        "accounts": formatted_accounts,
                    }
                )

        except RequestError as e:
            logger.error(f"Tinkoff API RequestError: {str(e)}")
            error_code = e.args[1] if len(e.args) > 1 else "unknown"
            metadata = e.args[2] if len(e.args) > 2 else None
            error_message = (
                metadata.message
                if metadata and hasattr(metadata, "message")
                else "Unknown error"
            )

            return Response(
                {"valid": False, "error": error_message, "error_code": error_code},
                status=(
                    status.HTTP_401_UNAUTHORIZED
                    if error_code == "40003"
                    else status.HTTP_400_BAD_REQUEST
                ),
            )

        except Exception as e:
            logger.exception("Unexpected error during token verification")
            return Response(
                {"valid": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["POST"])
    def save_read_only_token(self, request):
        """Save read-only token after validation."""
        try:
            new_token = request.data.get("token")
            token_type = request.data.get("token_type")
            sandbox_mode = request.data.get("sandbox_mode")
            broker_id = request.data.get("broker")  # Get broker ID from request

            # Verify broker exists and belongs to user
            try:
                broker = Brokers.objects.get(id=broker_id, investor=request.user)
            except Brokers.DoesNotExist:
                return Response(
                    {"error": ("Invalid broker selection",)},
                    status=status.HTTP_400_BAD_REQUEST,
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
                sandbox_mode=sandbox_mode,
            )

            # Check if the exact same token already exists
            for token in existing_tokens:
                try:
                    if token.get_token(request.user) == new_token:
                        if not token.is_active:
                            # Reactivate the token
                            token.is_active = True
                            # Model's save method will handle deactivating other tokens
                            token.save()
                            return Response(
                                {
                                    "message": "Existing token has been reactivated",
                                    "data": self.get_serializer(token).data,
                                    "id": token.id,
                                },
                                status=status.HTTP_200_OK,
                            )
                        else:
                            return Response(
                                {
                                    "message": "This exact token is already active",
                                    "data": self.get_serializer(token).data,
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                except Exception:
                    continue  # Skip tokens that can't be decrypted

            # Create new token if no existing token found
            token_data = {
                "broker": broker.id,  # Add broker ID
                "token": new_token,
                "token_type": token_type,
                "sandbox_mode": sandbox_mode,
            }

            serializer = self.get_serializer(data=token_data)

            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response(
                    {
                        "message": "Token saved successfully",
                        "data": serializer.data,
                        "id": serializer.instance.id,
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error saving read-only token: {str(e)}")
            return Response(
                {"error": "An error occurred while saving the token"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InteractiveBrokersApiTokenViewSet(BaseApiTokenViewSet):
    """Viewset for Interactive Brokers API tokens."""

    queryset = InteractiveBrokersApiToken.objects.all()
    serializer_class = InteractiveBrokersApiTokenSerializer


class AccountGroupViewSet(viewsets.ModelViewSet):
    """Viewset for account groups."""

    serializer_class = AccountGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get queryset for account groups."""
        return AccountGroup.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """List all account groups."""
        queryset = self.get_queryset()
        groups_data = self.get_serializer(queryset, many=True).data

        # Get available broker accounts for the user
        available_accounts = Accounts.objects.filter(broker__investor=request.user)
        account_choices = [
            {
                "value": account.id,
                "title": account.name,
            }
            for account in available_accounts
        ]

        return Response(
            {
                "groups": {
                    str(group["id"]): {
                        "name": group["name"],
                        "accounts": group["accounts"],
                    }
                    for group in groups_data
                },
                "available_accounts": account_choices,
            }
        )

    def perform_create(self, serializer):
        """Create a group."""
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        """Update a group."""
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Delete a group."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["POST"])
    def add_accounts(self, request, pk=None):
        """Add accounts to a group."""
        group = self.get_object()
        account_ids = request.data.get("account_ids", [])

        try:
            accounts = Accounts.objects.filter(
                id__in=account_ids, broker__investor=request.user
            )
            group.accounts.add(*accounts)
            return Response({"status": "accounts added"})
        except Exception as e:
            return Response(
                {"error": f"Failed to add accounts: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["POST"])
    def remove_accounts(self, request, pk=None):
        """Remove accounts from a group."""
        group = self.get_object()
        account_ids = request.data.get("account_ids", [])

        try:
            accounts = Accounts.objects.filter(
                id__in=account_ids, broker__investor=request.user
            )
            group.accounts.remove(*accounts)
            return Response({"status": "accounts removed"})
        except Exception as e:
            return Response(
                {"error": f"Failed to remove accounts: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom login view that includes effective_current_date in JWT token."""

    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(APIView):
    """
    Custom token refresh view that includes effective_current_date in JWT payload.

    This eliminates session dependency and uses JWT authentication only.
    """

    permission_classes = [AllowAny]

    def __init__(self):
        """Initialize the custom token refresh view."""
        super().__init__()
        self.logger = structlog.get_logger(__name__)

    def post(self, request, *args, **kwargs):
        """Refresh token view that includes effective_current_date in JWT payload."""
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate and decode the refresh token
            refresh = RefreshToken(refresh_token)

            # Check if a new effective_date is provided in the request
            new_effective_date = request.data.get("effective_current_date")
            current_effective_date = getattr(request, "effective_current_date", None)

            # Use new effective_date if provided, otherwise use current one
            effective_date = new_effective_date or current_effective_date

            # Update the refresh token with new effective_date if provided
            if effective_date:
                # Add effective_date to refresh token FIRST
                refresh["effective_current_date"] = effective_date

                # THEN generate the access token from the updated refresh token
                # This ensures the access token contains the effective_date
                access_token = refresh.access_token

                self.logger.info(
                    "CustomTokenRefresh",
                    effective_date=effective_date,
                    user_id=request.user.id if hasattr(request, "user") else "unknown",
                    updated_effective_date=new_effective_date is not None,
                )

                response_data = {
                    "access": str(access_token),
                    "refresh": str(refresh),
                    "effective_current_date": effective_date,
                }
            else:
                # If no effective_date provided, use standard access token generation
                access_token = refresh.access_token
                response_data = {"access": str(access_token), "refresh": str(refresh)}

            self.logger.info(
                "CustomTokenRefresh",
                message="Token refreshed successfully",
                has_effective_date=effective_date is not None,
            )

            return Response(response_data)

        except InvalidToken as e:
            self.logger.warning("CustomTokenRefresh", f"Invalid refresh token: {e}")
            return Response(
                {"error": "Invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            self.logger.error("CustomTokenRefresh", f"Token refresh failed: {e}")
            return Response(
                {"error": "Token refresh failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
