import os
import django
from channels.routing import get_default_application
import logging.config

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio_management.settings')
django.setup()

# Configure logging
from django.conf import settings
logging.config.dictConfig(settings.LOGGING)

application = get_default_application()

if __name__ == "__main__":
    from daphne.server import Server
    from daphne.endpoints import build_endpoint_description_strings

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=8000)
    parser.add_argument('-b', '--bind', default='127.0.0.1')
    args = parser.parse_args()

    endpoints = build_endpoint_description_strings(host=args.bind, port=args.port)
    Server(application=application, endpoints=endpoints).run()