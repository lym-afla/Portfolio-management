from django.urls import path
from .import views

app_name = 'database' # Optional, but useful for namespacing

urlpatterns = [
    path('brokers/', views.database_brokers, name='brokers'),
    path('securities/', views.database_securities, name='securities'),
    path('prices/', views.database_prices, name='prices'),

    # API methods
    path('add-transaction/', views.add_transaction, name='add_transaction'),
    path('add-broker/', views.add_broker, name='add_broker'),
    path('add-price/', views.add_price, name='add_price'),
    path('add-security/', views.add_security, name='add_security'),

]