from django.contrib import admin
from django.urls import path, include
from dashboard import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard/', include('dashboard.urls')),
    path('users/', include('users.urls', namespace='users')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('open_positions/', include('open_positions.urls', namespace='open_positions')),
    path('closed_positions/', include('closed_positions.urls', namespace='closed_positions')),
    path('transactions/', include('transactions.urls', namespace='transactions')),
    path('database/', include('database.urls', namespace='database')),
    path('summary/', include('summary_analysis.urls', namespace='summary_analysis')),

    path('api/', include('portfolio_management.api_urls')),
]
