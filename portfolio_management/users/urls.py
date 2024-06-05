from django.urls import path
from django.contrib.auth import views as auth_views
from .views import SignUpView
from . import views

app_name = 'users' # Optional, but useful for namespacing

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path('profile/', views.profile, name='profile'),
    path('edit_profile/', views.edit_profile, name='edit_profile'),
    path('login/', views.user_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('update_dashboard/', views.update_from_dashboard_form, name='update_dashboard'),
]
