from django.urls import path

from . import views

app_name = "dashboard"  # Optional, but useful for namespacing

urlpatterns = [
    path("api/get-summary/", views.get_dashboard_summary_api, name="get_dashboard_summary_api"),
    path(
        "api/get-breakdown/", views.get_dashboard_breakdown_api, name="get_dashboard_breakdown_api"
    ),
    path(
        "api/get-summary-over-time/",
        views.get_dashboard_summary_over_time_api,
        name="get_dashboard_summary_over_time_api",
    ),
    path("api/get-nav-chart-data/", views.api_nav_chart_data, name="api_nav_chart_data"),
]
