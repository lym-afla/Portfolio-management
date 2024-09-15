from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token
from urllib.parse import parse_qs
import logging

logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user(token_key):
    try:
        token = Token.objects.get(key=token_key)
        return token.user
    except Token.DoesNotExist:
        return AnonymousUser()

class TokenAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope['query_string'].decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get('token', [None])[0]
        logger.debug(f"Received token: {token_key}")
        if token_key:
            scope['user'] = await get_user(token_key)
            logger.debug(f"Authenticated user: {scope['user']}")
        else:
            scope['user'] = AnonymousUser()
            logger.debug("No token provided, user is anonymous")
        return await self.inner(scope, receive, send)