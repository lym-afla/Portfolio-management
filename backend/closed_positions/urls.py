from django.urls import path

from . import views

app_name = "closed_positions"  # Optional, but useful for namespacing

urlpatterns = [
    path(
        "api/get_closed_positions_table/",
        views.get_closed_positions_table_api,
        name="get_closed_positions_table_api",
    ),
]
