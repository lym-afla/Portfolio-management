from django.urls import path
from .import views

app_name = 'dashboard' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # API methods
    path('get_nav_chart_data', views.nav_chart_data_request, name='nav_chart_data_request'),

    # New API methods
    path('api/get-summary/', views.get_dashboard_summary_api, name='get_dashboard_summary_api'),
    path('api/get-breakdown/', views.get_dashboard_breakdown_api, name='get_dashboard_breakdown_api'),
    path('api/get-summary-over-time/', views.get_dashboard_summary_over_time_api, name='get_dashboard_summary_over_time_api'),
]