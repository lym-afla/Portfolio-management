from django.urls import path
from .import views

app_name = 'dashboard' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # API methods
    path('get_nav_chart_data', views.nav_chart_data_request, name='nav_chart_data_request'),
]