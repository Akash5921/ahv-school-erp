from django.urls import path

from .views import (
    parent_dashboard,
    parent_student_attendance,
    parent_student_fees,
    role_redirect,
    staff_dashboard,
)

urlpatterns = [
    path('dashboard/', role_redirect, name='role_redirect'),
    path('dashboard/parent/', parent_dashboard, name='parent_dashboard'),
    path('dashboard/parent/attendance/<int:student_id>/', parent_student_attendance, name='parent_student_attendance'),
    path('dashboard/parent/fees/<int:student_id>/', parent_student_fees, name='parent_student_fees'),
    path('dashboard/staff/', staff_dashboard, name='staff_dashboard'),
]
