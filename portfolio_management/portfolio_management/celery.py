import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio_management.settings')

app = Celery('portfolio_management') 
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Add this to ensure Celery doesn't hang on Windows
app.conf.broker_connection_retry_on_startup = True