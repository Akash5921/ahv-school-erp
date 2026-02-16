from django.urls import path
from .views import school_admin_dashboard, school_list, school_onboard

urlpatterns = [
    path('', school_list, name='school_list'),
    path('onboard/', school_onboard, name='school_onboard'),
    path('school-dashboard/', school_admin_dashboard, name='school_dashboard'),
]
