import logging.config
import os

import django
import uvicorn
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings")
django.setup()

# Configure logging

logging.config.dictConfig(settings.LOGGING)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=8000)
    parser.add_argument("-b", "--bind", default="127.0.0.1")
    args = parser.parse_args()

    # Start Uvicorn server
    uvicorn.run(
        "portfolio_management.asgi:application",
        host=args.bind,
        port=args.port,
        log_level="info",
        reload=True,  # Optional: Enable auto-reloading for development
    )
