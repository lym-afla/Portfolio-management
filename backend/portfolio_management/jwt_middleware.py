"""
JWT-based middleware for handling effective_current_date.

This eliminates session dependency and uses JWT authentication only.
"""

from datetime import date

import structlog
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = structlog.get_logger(__name__)


class JWTEffectiveDateMiddleware:
    """
    JWT-based middleware for handling effective_current_date.

    Middleware to handle effective_current_date using JWT authentication
    instead of Django sessions. Much more reliable for SPA applications.
    """

    def __init__(self, get_response):
        """Initialize the middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Call the middleware."""
        # Only process JWT middleware for requests that have tokens
        # Skip authentication endpoints like login/register
        auth_endpoints = [
            "/users/api/login/",
            "/users/api/register/",
            "/users/api/refresh-token/",
        ]

        if request.path in auth_endpoints or not self._has_jwt_token(request):
            # For auth endpoints or requests without tokens, use default date
            default_date = date.today().isoformat()
            request.effective_current_date = default_date

            # Minimal logging for auth endpoints
            if request.path in auth_endpoints:
                logger.debug("JWT Middleware skipping auth endpoint", path=request.path)

            return self.get_response(request)

        # Process JWT token for authenticated requests
        effective_date = self._extract_effective_date_from_jwt(request)

        # Store it in request for views to use
        request.effective_current_date = effective_date

        # Log the middleware processing (only for authenticated requests)
        logger.debug(
            "JWT Middleware processing authenticated request",
            path=request.path,
            method=request.method,
            effective_date=effective_date,
            has_jwt=self._has_jwt_token(request),
            user_id=self._get_user_id_from_jwt(request),
        )

        response = self.get_response(request)

        # For API responses that modify effective_date, add it to response
        if hasattr(response, "data") and isinstance(response.data, dict):
            if "table_date" in response.data:
                response.data["effective_current_date"] = response.data["table_date"]

        return response

    def _has_jwt_token(self, request):
        """Check if request has JWT token."""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        return auth_header.startswith("Bearer ")

    def _extract_jwt_token(self, request):
        """Extract JWT token from request."""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove 'Bearer ' prefix
        return None

    def _decode_jwt_token(self, request):
        """Decode JWT token and return payload."""
        token = self._extract_jwt_token(request)
        if not token:
            return None

        try:
            # Use SimpleJWT to decode the token properly
            access_token = AccessToken(token)
            return access_token.payload
        except (InvalidToken, TokenError) as e:
            # Only log debug info for invalid tokens, not warnings
            # This is normal for login/register endpoints that don't have tokens yet
            if "Token is expired" not in str(e):
                logger.debug("JWT Middleware invalid token", error=str(e))
            else:
                logger.debug(
                    "JWT Middleware expired token - "
                    "this is expected for unauthenticated requests"
                )
            return None

    def _get_user_id_from_jwt(self, request):
        """Get user ID from JWT token."""
        payload = self._decode_jwt_token(request)
        if payload:
            return payload.get("user_id")
        return None

    def _extract_effective_date_from_jwt(self, request):
        """
        Extract effective_current_date from JWT token.

        This should be stored in the JWT token when it's issued.
        """
        payload = self._decode_jwt_token(request)
        if payload:
            # Try to get effective_date from JWT token
            effective_date = payload.get("effective_current_date")
            if effective_date:
                logger.debug(
                    "JWT Middleware found effective_date in JWT token",
                    effective_date=effective_date,
                )
                return effective_date

        # Fallback: try to get from database (for existing sessions)
        user_id = self._get_user_id_from_jwt(request)
        if user_id:
            effective_date = self._get_effective_date_from_database(user_id)
            if effective_date:
                logger.debug(
                    "JWT Middleware found effective_date in database",
                    effective_date=effective_date,
                )
                return effective_date

        # Final fallback: use today's date
        default_date = date.today().isoformat()
        logger.debug("JWT Middleware using default date", default_date=default_date)
        return default_date

    def _get_effective_date_from_database(self, user_id):
        """
        Get effective_current_date from user preferences in database.

        This is a fallback mechanism for existing users.
        """
        try:
            # from users.models import CustomUser

            # user = CustomUser.objects.get(id=user_id)

            # Try to get effective_date from recent session as fallback
            # This helps with migration from session-based to JWT-based
            from django.contrib.sessions.models import Session

            recent_sessions = (
                Session.objects.filter(
                    session_data__contains=f'"_auth_user_id": "{user_id}"'
                )
                .order_by("-expire_date")
                .first()
            )

            if recent_sessions:
                session_data = recent_sessions.get_decoded()
                if session_data and "effective_current_date" in session_data:
                    return session_data["effective_current_date"]

        # except CustomUser.DoesNotExist:
        #     pass
        except Exception as e:
            logger.error(
                "JWT Middleware error getting effective date from database",
                error=str(e),
            )

        return None
