from django.urls import path
from .views import (
    staff_assign_user,
    staff_create,
    staff_list,
    staff_toggle_active,
    staff_update,
    teacher_dashboard,
)

urlpatterns = [
    path('dashboard/', teacher_dashboard, name='teacher_dashboard'),
    path('manage/', staff_list, name='staff_list'),
    path('manage/add/', staff_create, name='staff_create'),
    path('manage/<int:pk>/edit/', staff_update, name='staff_update'),
    path('manage/<int:pk>/toggle-active/', staff_toggle_active, name='staff_toggle_active'),
    path('manage/<int:pk>/assign-user/', staff_assign_user, name='staff_assign_user'),
]
