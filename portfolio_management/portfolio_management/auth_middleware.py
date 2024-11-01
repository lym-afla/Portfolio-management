from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

@database_sync_to_async
def get_user(token_key):
    try:
        access_token = AccessToken(token_key)
        user = User.objects.get(id=access_token['user_id'])
        return user
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()

class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        try:
            token = None

            # Check if it's a WebSocket connection
            if scope["type"] == "websocket":
                # Extract token from query string
                query_string = scope.get('query_string', b'').decode()
                query_params = dict(param.split('=') for param in query_string.split('&') if param)
                token = query_params.get('token', None)

            # Check if it's a HTTP connection
            elif scope["type"] == "http":
                # Extract token from headers
                headers = dict(scope['headers'])
                if b'authorization' in headers:
                    auth_header = headers[b'authorization'].decode()
                    if auth_header.startswith('Bearer '):
                        token = auth_header.split()[1]

            if token:
                scope['user'] = await get_user(token)
            else:
                scope['user'] = AnonymousUser()

            # Add this debug logging
            logger.debug(f"User authenticated: {scope['user']}")
            
            return await super().__call__(scope, receive, send)
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            scope['user'] = AnonymousUser()
            return await super().__call__(scope, receive, send)