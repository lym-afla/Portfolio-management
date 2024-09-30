from django.contrib import admin
from django.urls import path, include
from common import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard/', include('dashboard.urls')),
    path('users/', include('users.urls', namespace='users')),
    # path('accounts/', include('django.contrib.auth.urls')),
    path('open_positions/', include('open_positions.urls', namespace='open_positions')),
    path('closed_positions/', include('closed_positions.urls', namespace='closed_positions')),
    path('transactions/', include('transactions.urls', namespace='transactions')),
    path('database/', include('database.urls', namespace='database')),
    path('summary/', include('summary_analysis.urls', namespace='summary_analysis')),

    # APIs not related to any specific app
    path('api/get-year-options/', views.get_year_options_api, name='get_year_options_api'),
    path('api/effective-current-date/', views.get_effective_current_date, name='get_effective_current_date'),

    path('__debug__/', include('debug_toolbar.urls')),

]