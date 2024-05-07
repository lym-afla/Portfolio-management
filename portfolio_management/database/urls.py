from django.urls import path
from .import views

app_name = 'database' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.database, name='database'),

    # API methods

]