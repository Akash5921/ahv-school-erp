from django.urls import path

from .views import (
    dashboard_accountant,
    dashboard_parent,
    dashboard_principal,
    dashboard_super_admin,
    dashboard_teacher,
)

urlpatterns = [
    path('super-admin/', dashboard_super_admin, name='dashboard_super_admin'),
    path('principal/', dashboard_principal, name='dashboard_principal'),
    path('accountant/', dashboard_accountant, name='dashboard_accountant'),
    path('teacher/', dashboard_teacher, name='dashboard_teacher'),
    path('parent/', dashboard_parent, name='dashboard_parent'),
]
