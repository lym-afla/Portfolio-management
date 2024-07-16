from django.urls import path
from .import views

app_name = 'closed_positions' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.closed_positions, name='closed_positions'),

    # API methods
    path('update_table/', views.update_closed_positions_table, name='update_closed_positions_table'),
]