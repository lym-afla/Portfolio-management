from django.urls import path
from .import views

app_name = 'transactions' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.transactions, name='transactions'),

    # API methods
]