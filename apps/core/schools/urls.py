from django.urls import path
from .views import school_admin_dashboard

urlpatterns = [
    path('school-dashboard/', school_admin_dashboard, name='school_dashboard'),
]
