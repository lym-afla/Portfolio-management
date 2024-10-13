import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path, re_path
from database.consumers import UpdateBrokerPerformanceConsumer, PriceImportConsumer
from transactions.consumers import TransactionConsumer
from channels.security.websocket import AllowedHostsOriginValidator
from .auth_middleware import TokenAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio_management.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": TokenAuthMiddleware(
        URLRouter([
            # Route for SSE POST requests
            path("database/api/update-broker-performance/sse/", UpdateBrokerPerformanceConsumer.as_asgi()),
            path("database/api/price-import/sse/", PriceImportConsumer.as_asgi()),
            # Route all other HTTP requests to Django
            re_path(r"", django_asgi_app),  # This should be the last route
        ])
    ),
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            URLRouter([
                path("ws/transactions/", TransactionConsumer.as_asgi()),
            ])
        )
    ),
})
