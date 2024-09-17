from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import UntypedToken, AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from urllib.parse import parse_qs
import logging
import jwt

logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user_from_token(token_key):
    try:
        access_token = AccessToken(token_key)
        user = get_user_model().objects.get(id=access_token['user_id'])
        return user
    except (TokenError, get_user_model().DoesNotExist):
        return AnonymousUser()

class TokenAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope['query_string'].decode()
        query_params = dict(q.split('=') for q in query_string.split('&') if '=' in q)
        token_key = query_params.get('token')
        
        if token_key:
            scope['user'] = await get_user_from_token(token_key)
            logger.debug(f"Authenticated user: {scope['user']}")
        else:
            scope['user'] = AnonymousUser()
            logger.debug("No token provided, user is anonymous")

        return await self.inner(scope, receive, send)

# class TokenAuthMiddleware:
#     def __init__(self, inner):
#         self.inner = inner

#     async def __call__(self, scope, receive, send):
#         query_string = scope['query_string'].decode()
#         query_params = parse_qs(query_string)
#         token_key = query_params.get('token', [None])[0]
#         logger.debug(f"Received token: {token_key}")
#         if token_key:
#             scope['user'] = await get_user(token_key)
#             logger.debug(f"Authenticated user: {scope['user']}")
#         else:
#             scope['user'] = AnonymousUser()
#             logger.debug("No token provided, user is anonymous")
#         return await self.inner(scope, receive, send)