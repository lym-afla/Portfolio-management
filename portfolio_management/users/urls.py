from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'users' # Optional, but useful for namespacing

# Create a separate router for broker groups
broker_router = DefaultRouter()
broker_router.register(r'broker-groups', views.BrokerGroupViewSet, basename='broker-groups')

# Create main router for other viewsets
router = DefaultRouter()
router.register(r'tinkoff-tokens', views.TinkoffApiTokenViewSet, basename='tinkoff-token')
router.register(r'ib-tokens', views.InteractiveBrokersApiTokenViewSet, basename='ib-token')
router.register(r'', views.UserViewSet, basename='user')

urlpatterns = [
    # JWT auth endpoints
    path('api/login/', TokenObtainPairView.as_view(), name='login'),
    path('api/refresh-token/', TokenRefreshView.as_view(), name='refresh_token'),
    path('api/register/', views.UserViewSet.as_view({'post': 'create_user'}), name='api_register'),
    
    # Include broker groups router
    path('api/', include(broker_router.urls)),
    # Include main router
    path('api/', include(router.urls)),
]