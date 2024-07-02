from django.urls import path
from .import views
from common.models import Brokers, Assets, Transactions, Prices
from database.forms import BrokerForm, SecurityForm, TransactionForm, PriceForm

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
    path('edit_broker/<int:item_id>/', views.edit_item, {'model_class': Brokers, 'form_class': BrokerForm, 'type': 'broker'}, name='edit_broker'),
    path('delete_broker/<int:item_id>/', views.delete_item, {'model_class': Brokers}, name='delete_broker'),
    path('edit_transaction/<int:item_id>/', views.edit_item, {'model_class': Transactions, 'form_class': TransactionForm, 'type': 'transaction'}, name='edit_transaction'),
    path('delete_transaction/<int:item_id>/', views.delete_item, {'model_class': Transactions}, name='delete_transaction'),
    path('edit_security/<int:item_id>/', views.edit_item, {'model_class': Assets, 'form_class': SecurityForm, 'type': 'security'}, name='edit_security'),
    path('delete_security/<int:item_id>/', views.delete_item, {'model_class': Assets}, name='delete_security'),
    path('edit_price/<int:item_id>/', views.edit_item, {'model_class': Prices, 'form_class': PriceForm, 'type': 'price  '}, name='edit_price'),
    path('delete_price/<int:item_id>/', views.delete_item, {'model_class': Prices}, name='delete_price'),
    path('import_transactions_form/', views.import_transactions_form, name='import_transactions_form'),
    path('import_transactions/', views.import_transactions, name='import_transactions'),
    path('process_import_transactions/', views.process_import_transactions, name='process_import_transactions'),
    path('prices/update_fx_dates/', views.get_update_fx_dates, name='update_fx_dates'),
    path('prices/update_fx/', views.update_FX, name='update_fx'),
    path('update_broker_performance/', views.update_broker_performance, name='update_broker_performance'),
    
]