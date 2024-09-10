from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'transactions'

router = DefaultRouter()
router.register(r'', views.TransactionViewSet, basename='transaction___')
router.register(r'fx', views.FXTransactionViewSet, basename='fx_transaction')

urlpatterns = [
    path('', views.transactions, name='transactions'),
    path('api/', include(router.urls)),
]