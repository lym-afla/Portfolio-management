from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'summary_analysis' # Optional, but useful for namespacing

router = DefaultRouter()
router.register(r'api', views.SummaryViewSet, basename='summary')

urlpatterns = [
    # path('', views.summary_view, name='summary_view'),
    path('', include(router.urls)),

    # API methods
    path('exposure-table/', views.exposure_table_update, name='exposure_table_update'),
]