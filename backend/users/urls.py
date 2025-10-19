from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = "users"  # Optional, but useful for namespacing

# Create a separate router for broker groups
broker_router = DefaultRouter()
broker_router.register(
    r"account-groups", views.AccountGroupViewSet, basename="account-groups"
)

# Create main router for other viewsets
router = DefaultRouter()
router.register(
    r"tinkoff-tokens", views.TinkoffApiTokenViewSet, basename="tinkoff-token"
)
router.register(
    r"ib-tokens", views.InteractiveBrokersApiTokenViewSet, basename="ib-token"
)
router.register(r"", views.UserViewSet, basename="user")

urlpatterns = [
    # JWT auth endpoints
    path("api/login/", views.CustomTokenObtainPairView.as_view(), name="login"),
    path(
        "api/refresh-token/",
        views.CustomTokenRefreshView.as_view(),
        name="refresh_token",
    ),
    path(
        "api/refresh-token-standard/",
        TokenRefreshView.as_view(),
        name="refresh_token_standard",
    ),
    path(
        "api/register/",
        views.UserViewSet.as_view({"post": "create_user"}),
        name="api_register",
    ),
    # Include broker groups router
    path("api/", include(broker_router.urls)),
    # Include main router
    path("api/", include(router.urls)),
]
