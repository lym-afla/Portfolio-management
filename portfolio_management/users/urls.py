from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter
# from .views import SignUpView, CustomObtainAuthToken, RegisterView
from . import views
app_name = 'users' # Optional, but useful for namespacing

router = DefaultRouter()
router.register(r'', views.UserViewSet, basename='user')

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('profile/', views.profile, name='profile'),
    path('edit_profile/', views.edit_profile, name='edit_profile'),
    path('login/', views.user_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('update_dashboard/', views.update_from_dashboard_form, name='update_dashboard'),
    path('update_data_for_broker/', views.update_data_for_broker, name='update_data_for_broker'),

    # New API endpoints
    path('api/profile/', views.user_profile_api, name='api_profile'),
    path('api/profile/edit/', views.edit_profile_api, name='api_edit_profile'),
    path('api/settings/', views.user_settings_api, name='api_settings'),
    path('api/settings/choices/', views.user_settings_choices_api, name='api_settings_choices'),
    path('api/change-password/', views.change_password_api, name='api_change_password'),
    path('api/logout/', views.logout_api, name='api_logout'),

    # New user handling with JWT
    path('api/login/', TokenObtainPairView.as_view(), name='login'),
    path('api/refresh-token/', TokenRefreshView.as_view(), name='refresh_token'),
    path('', include(router.urls)),
    path('api/register/', views.UserViewSet.as_view({'post': 'create_user'}), name='api_register'),

    path('api/get_broker_choices/', views.get_broker_choices_api, name='get_broker_choices_api'),
    path('api/update_user_broker/', views.update_user_broker_api, name='update_user_broker_api'),
    path('api/update-settings-from-dashboard/', views.update_user_settings_from_dashboard, name='update_user_settings_from_dashboard'),
    path('api/dashboard-settings/', views.get_dashboard_settings, name='get_dashboard_settings'),
]