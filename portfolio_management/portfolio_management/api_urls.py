from django.urls import path, include
from dashboard.views import dashboard_summary_api
from users.views import CustomObtainAuthToken, RegisterView

urlpatterns = [
    path('dashboard-summary/', dashboard_summary_api, name='dashboard_summary_api'),

    # path('login/', CustomObtainAuthToken.as_view(), name='api_login'),
    # path('register/', RegisterView.as_view(), name='api_register'),
]