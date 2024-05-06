from django.urls import path
from .import views

app_name = 'open_positions' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.open_positions, name='open_positions'),

    # API methods
]