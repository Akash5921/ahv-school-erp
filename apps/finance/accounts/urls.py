from django.urls import path
from .views import accountant_dashboard

urlpatterns = [
    path('accountant/dashboard/', accountant_dashboard, name='accountant_dashboard'),
]
