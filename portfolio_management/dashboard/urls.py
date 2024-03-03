from django.urls import path
from .import views

app_name = 'dashboard' # Optional, but useful for namespacing

urlpatterns = [
    path('dashboard/', views.pa_dashboard, name='pa_dashboard'),
]