"""JWT token authentication middleware for Django Channels.

This module provides authentication middleware for WebSocket and HTTP
connections using JWT tokens from the request headers or query parameters.
"""

import logging

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)

User = get_user_model()


@database_sync_to_async
def get_user(token_key):
    """Get user from JWT token.

    Args:
        token_key: JWT token string.

    Returns:
        User object if token is valid, AnonymousUser otherwise.
    """
    try:
        access_token = AccessToken(token_key)
        user = User.objects.get(id=access_token["user_id"])
        return user
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    """JWT token authentication middleware for Channels.

    Extracts JWT token from query parameters or Authorization header
    and authenticates the user for the connection.
    """

    async def __call__(self, scope, receive, send):
        """Process the incoming connection request.

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        try:
            token = None
            logger.debug(f"Processing {scope['type']} request")

            # First check query parameters for token (works for both HTTP and WebSocket)
            query_string = scope.get("query_string", b"").decode()
            query_params = dict(
                param.split("=") for param in query_string.split("&") if param
            )
            token = query_params.get("token")
            logger.debug(f"Token from query params: {token}")

            # If no token in query params and it's HTTP, check headers
            if not token and scope["type"] == "http":
                headers = dict(scope["headers"])
                logger.debug(f"Headers received: {headers}")

                if b"authorization" in headers:
                    auth_header = headers[b"authorization"].decode()
                    logger.debug(f"Authorization header found: {auth_header}")
                    if auth_header.startswith("Bearer "):
                        token = auth_header.split()[1]
                        logger.debug(f"Bearer token extracted: {token}")

            if token:
                logger.debug("Attempting to get user from token")
                scope["user"] = await get_user(token)
                logger.debug(
                    f"User authentication result: "
                    f"{not isinstance(scope['user'], AnonymousUser)}"
                )
            else:
                logger.debug("No token found, setting AnonymousUser")
                scope["user"] = AnonymousUser()

            return await super().__call__(scope, receive, send)
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}", exc_info=True)
            scope["user"] = AnonymousUser()
            return await super().__call__(scope, receive, send)
