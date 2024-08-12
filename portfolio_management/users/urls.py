from django.urls import path
from django.contrib.auth import views as auth_views
from .views import SignUpView, CustomObtainAuthToken, RegisterView
from . import views

app_name = 'users' # Optional, but useful for namespacing

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
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

    path('api/login/', CustomObtainAuthToken.as_view(), name='api_login'),
    path('api/register/', RegisterView.as_view(), name='api_register'),
]