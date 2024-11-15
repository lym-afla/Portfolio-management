from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import PriceImportView, UpdateAccountPerformanceViewSet, BrokerViewSet

app_name = 'database'

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet, basename='account')
router.register(r'fx', views.FXViewSet, basename='fx')
router.register(r'brokers', BrokerViewSet, basename='broker')
router.register(r'update-account-performance', UpdateAccountPerformanceViewSet, basename='update-account-performance')

urlpatterns = [
    path('api/get-asset-types/', views.api_get_asset_types, name='api_get_asset_types'),
    path('api/get-securities/', views.api_get_securities, name='api_get_securities'),
    path('api/get-prices-table/', views.api_get_prices_table, name='api_get_prices_table'),
    path('api/get-securities-for-database/', views.api_get_securities_table, name='api_get_securities_for_database'),
    path('api/add-price/', views.api_add_price, name='api_add_price'),
    path('api/delete-price/<int:price_id>/', views.api_delete_price, name='api_delete_price'),
    path('api/get-price-details/<int:price_id>/', views.api_get_price_details, name='api_get_price_details'),
    path('api/update-price/<int:price_id>/', views.api_update_price, name='api_update_price'),
    path('api/security-form-structure/', views.api_security_form_structure, name='api_security_form_structure'),
    path('api/create-security/', views.api_create_security, name='api_create_security'),
    path('api/update-security/<int:security_id>/', views.api_update_security, name='api_update_security'),
    path('api/delete-security/<int:security_id>/', views.api_delete_security, name='api_delete_security'),
    path('api/get-security-details/<int:security_id>/', views.api_get_security_details_for_editing, name='api_get_security_details'),
    path('api/securities/<int:security_id>/', views.api_get_security_detail, name='api_get_security_detail'),
    path('api/securities/<int:security_id>/price-history/', views.api_get_security_price_history, name='api_get_security_price_history'),
    path('api/securities/<int:security_id>/position-history/', views.api_get_security_position_history, name='api_get_security_position_history'),
    path('api/securities/<int:security_id>/transactions/', views.api_get_security_transactions, name='api_get_security_transactions'),
    path('api/price-import/', PriceImportView.as_view(), name='price_import'),
    path('api/', include(router.urls)),
]