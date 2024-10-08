from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user(user_id):
    User = get_user_model()
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class TokenAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope['headers'])
        if b'authorization' in headers:
            try:
                token = headers[b'authorization'].decode().split()[1]
                # This will raise an error if the token is invalid
                UntypedToken(token)
                # Decode the token
                decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = decoded_data['user_id']
                scope['user'] = await get_user(user_id)
                logger.debug(f"Authenticated user: {scope['user']}")
            except (InvalidToken, TokenError, KeyError) as e:
                logger.error(f"Invalid token: {str(e)}")
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()
        
        return await self.inner(scope, receive, send)