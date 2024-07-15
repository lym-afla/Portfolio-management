from django.urls import path
from .import views

app_name = 'open_positions' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.open_positions, name='open_positions'),

    # API methods
    path('update_table/', views.update_open_positions_table, name='update_open_positions_table'),
    path('get_cash_balances/', views.get_cash_balances, name='get_cash_balances'),
]