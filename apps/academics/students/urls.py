from django.urls import path
from .views import (
    add_marks,
    student_list,
    student_create,
    student_report,
    exam_report_card,
    student_update,
    student_delete,
    student_detail,
    enrollment_history,
    enrollment_status_update,
    grade_scale_list,
    grade_scale_create,
    grade_scale_update,
    grade_scale_delete,
)



urlpatterns = [
    path('', student_list, name='student_list'),
    path('create/', student_create, name='student_create'),
    path('<int:pk>/edit/', student_update, name='student_update'),
    path('<int:pk>/delete/', student_delete, name='student_delete'),
    path('<int:pk>/', student_detail, name='student_detail'),
    path('<int:pk>/enrollments/', enrollment_history, name='enrollment_history'),
    path('enrollments/<int:enrollment_id>/status/', enrollment_status_update, name='enrollment_status_update'),
    path('add/marks/', add_marks, name='add_marks'),
    path('<int:student_id>/report/', student_report, name='student_report'),
    path('<int:student_id>/report-card/', exam_report_card, name='exam_report_card'),
    path('grade-scales/', grade_scale_list, name='grade_scale_list'),
    path('grade-scales/add/', grade_scale_create, name='grade_scale_create'),
    path('grade-scales/<int:pk>/edit/', grade_scale_update, name='grade_scale_update'),
    path('grade-scales/<int:pk>/delete/', grade_scale_delete, name='grade_scale_delete'),
]
