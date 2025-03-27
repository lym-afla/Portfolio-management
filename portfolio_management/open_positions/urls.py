from django.urls import path

from . import views

app_name = "open_positions"  # Optional, but useful for namespacing

urlpatterns = [
    path(
        "api/get_open_positions_table/",
        views.get_open_positions_table_api,
        name="get_open_positions_table_api",
    ),
]
