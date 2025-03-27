from django.urls import path

from . import views

app_name = "open_positions"  # Optional, but useful for namespacing

urlpatterns = [
    # path('', views.open_positions, name='open_positions'),
    # API methods
    # path('update_table/', views.update_open_positions_table, name='update_open_positions_table'),
    # New API endpoints
    path(
        "api/get_open_positions_table/",
        views.get_open_positions_table_api,
        name="get_open_positions_table_api",
    ),
]
