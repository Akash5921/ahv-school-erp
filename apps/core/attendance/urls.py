from django.urls import path

from .views import (
    attendance_lock_manage,
    attendance_report_absentees,
    attendance_report_class,
    attendance_report_staff,
    attendance_report_student_monthly,
    attendance_report_threshold,
    attendance_staff_edit,
    attendance_staff_list,
    attendance_staff_mark,
    attendance_student_daily_mark,
    attendance_student_period_mark,
)

urlpatterns = [
    path('staff/', attendance_staff_list, name='attendance_staff_list'),
    path('staff/mark/', attendance_staff_mark, name='attendance_staff_mark'),
    path('staff/<int:pk>/edit/', attendance_staff_edit, name='attendance_staff_edit'),

    path('students/daily/', attendance_student_daily_mark, name='attendance_student_daily_mark'),
    path('students/period/', attendance_student_period_mark, name='attendance_student_period_mark'),

    path('lock/', attendance_lock_manage, name='attendance_lock_manage'),

    path('reports/class/', attendance_report_class, name='attendance_report_class'),
    path('reports/student-monthly/', attendance_report_student_monthly, name='attendance_report_student_monthly'),
    path('reports/staff/', attendance_report_staff, name='attendance_report_staff'),
    path('reports/threshold/', attendance_report_threshold, name='attendance_report_threshold'),
    path('reports/absentees/', attendance_report_absentees, name='attendance_report_absentees'),
]
