from django.urls import path
from .import views

app_name = 'closed_positions' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.closed_positions, name='closed_positions'),

    # API methods
    path('update_table/', views.update_closed_positions_table, name='update_closed_positions_table'),

    # New API endpoints
    path('api/get_closed_positions_table/', views.get_closed_positions_table_api, name='get_closed_positions_table_api'),
    # path('api/get_year_options/', views.get_year_options_api, name='get_year_options_api'),
]