from django.urls import path
from .import views

app_name = 'database' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.database, name='database'),
    path('brokers/', views.database_brokers, name='brokers'),
    path('securities/', views.database_securities, name='securities'),
    path('prices/', views.database_prices, name='prices'),

    # API methods

]