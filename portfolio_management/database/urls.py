from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .import views
from common.models import Brokers, Assets, Transactions, Prices
from database.forms import BrokerForm, SecurityForm, TransactionForm, PriceForm
from .views import PriceImportView, UpdateBrokerPerformanceView

app_name = 'database' # Optional, but useful for namespacing

router = DefaultRouter()
router.register(r'brokers', views.BrokerViewSet, basename='broker')
router.register(r'fx', views.FXViewSet, basename='fx')


urlpatterns = [
    # path('brokers/', views.database_brokers, name='brokers'),
    # path('securities/', views.database_securities, name='securities'),
    # path('prices/', views.database_prices, name='prices'),

    # API methods
    # path('add-transaction/', views.add_transaction, name='add_transaction'),
    # path('add_fx_transaction/', views.add_fx_transaction, name='add_fx_transaction'),
    # path('add-broker/', views.add_broker, name='add_broker'),
    # path('add-price/', views.add_price, name='add_price'),
    # path('add-security/', views.add_security, name='add_security'),
    # path('edit_broker/<int:item_id>/', views.edit_item, {'model_class': Brokers, 'form_class': BrokerForm, 'type': 'broker'}, name='edit_broker'),
    # path('delete_broker/<int:item_id>/', views.delete_item, {'model_class': Brokers}, name='delete_broker'),
    # path('edit_transaction/<int:item_id>/', views.edit_item, {'model_class': Transactions, 'form_class': TransactionForm, 'type': 'transaction'}, name='edit_transaction'),
    # path('delete_transaction/<int:item_id>/', views.delete_item, {'model_class': Transactions}, name='delete_transaction'),
    # path('edit_security/<int:item_id>/', views.edit_item, {'model_class': Assets, 'form_class': SecurityForm, 'type': 'security'}, name='edit_security'),
    # path('delete_security/<int:item_id>/', views.delete_item, {'model_class': Assets}, name='delete_security'),
    # path('edit_price/<int:item_id>/', views.edit_item, {'model_class': Prices, 'form_class': PriceForm, 'type': 'price'}, name='edit_price'),
    # path('delete_price/<int:item_id>/', views.delete_item, {'model_class': Prices}, name='delete_price'),
    # path('import_transactions_form/', views.import_transactions_form, name='import_transactions_form'),
    path('import_transactions/', views.import_transactions, name='import_transactions'),
    path('process_import_transactions/', views.process_import_transactions, name='process_import_transactions'),
    path('prices/update_fx_dates/', views.get_update_fx_dates, name='update_fx_dates'),
    path('prices/update_fx/', views.update_FX, name='update_fx'),
    # path('update_broker_performance/', views.update_broker_performance, name='update_broker_performance'),
    # path('get_price_data_for_table/', views.get_price_data_for_table, name='get_price_data_for_table'),
    # path('prices/import_prices/', views.import_prices, name='import_prices'),
    path('get_broker_securities/', views.get_broker_securities, name='get_broker_securities'),

    #New API methods
    path('api/get-asset-types/', views.api_get_asset_types, name='api_get_asset_types'),
    # path('api/get-brokers/', views.api_get_brokers, name='api_get_brokers'),
    path('api/get-securities/', views.api_get_securities, name='api_get_securities'),
    path('api/get-prices-table/', views.api_get_prices_table, name='api_get_prices_table'),
    # path('api/get-brokers-for-database/', views.api_get_brokers_table, name='api_get_brokers_for_database'),
    path('api/get-securities-for-database/', views.api_get_securities_table, name='api_get_securities_for_database'),
    path('api/add-price/', views.api_add_price, name='api_add_price'),
    path('api/delete-price/<int:price_id>/', views.api_delete_price, name='api_delete_price'),
    path('api/get-price-details/<int:price_id>/', views.api_get_price_details, name='api_get_price_details'),
    path('api/update-price/<int:price_id>/', views.api_update_price, name='api_update_price'),
    path('api/security-form-structure/', views.api_security_form_structure, name='api_security_form_structure'),
    path('api/create-security/', views.api_create_security, name='api_create_security'),
    path('api/update-security/<int:security_id>/', views.api_update_security, name='api_update_security'),
    path('api/delete-security/<int:security_id>/', views.api_delete_security, name='api_delete_security'),
    path('api/get-security-details/<int:security_id>/', views.api_get_security_details, name='api_get_security_details'),
    # path('api/price-import-form-structure/', views.api_price_import_form_structure, name='api_price_import_form_structure'),
    path('api/price-import/', PriceImportView.as_view(), name='price_import'),
    path('api/', include(router.urls)),
    path('api/update-broker-performance/', UpdateBrokerPerformanceView.as_view(), name='update_broker_performance'),
]