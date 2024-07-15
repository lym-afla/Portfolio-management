from django.urls import path
from .import views

app_name = 'summary_analysis' # Optional, but useful for namespacing

urlpatterns = [
    path('', views.summary_view, name='summary_view'),

    # API methods
    path('exposure-table/', views.exposure_table_update, name='exposure_table_update'),
]