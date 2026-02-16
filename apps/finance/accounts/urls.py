from django.urls import path
from .views import accountant_dashboard

urlpatterns = [
    path('dashboard/', accountant_dashboard, name='accountant_dashboard'),
]
