from django.urls import path
from .views import role_redirect, parent_dashboard, parent_student_attendance, staff_dashboard

urlpatterns = [
    path('dashboard/', role_redirect, name='role_redirect'),
    path('dashboard/parent/', parent_dashboard, name='parent_dashboard'),
    path('dashboard/parent/attendance/<int:student_id>/', parent_student_attendance, name='parent_student_attendance'),
    path('dashboard/staff/', staff_dashboard, name='staff_dashboard'),
]
