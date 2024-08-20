from django.urls import path
from .import views

app_name = 'transactions' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.transactions, name='transactions'),

    # API methods
    path('api/get_transactions_table/', views.compile_transactions_table_api, name='get_transactions_table_api'),
]