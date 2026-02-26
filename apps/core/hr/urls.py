from django.urls import path

from .views import (
    hr_class_teacher_create,
    hr_class_teacher_deactivate,
    hr_class_teacher_list,
    hr_class_teacher_update,
    hr_designation_create,
    hr_designation_deactivate,
    hr_designation_list,
    hr_designation_update,
    hr_leave_request_create,
    hr_leave_request_list,
    hr_leave_request_review,
    hr_salary_structure_list,
    hr_staff_attendance_edit,
    hr_staff_attendance_list,
    hr_staff_attendance_mark,
    hr_staff_create,
    hr_staff_deactivate,
    hr_staff_list,
    hr_staff_update,
    hr_substitution_create,
    hr_substitution_deactivate,
    hr_substitution_list,
    hr_substitution_update,
    hr_teacher_subject_create,
    hr_teacher_subject_deactivate,
    hr_teacher_subject_list,
    hr_teacher_subject_update,
)

urlpatterns = [
    path('designations/', hr_designation_list, name='hr_designation_list'),
    path('designations/add/', hr_designation_create, name='hr_designation_create'),
    path('designations/<int:pk>/edit/', hr_designation_update, name='hr_designation_update'),
    path('designations/<int:pk>/deactivate/', hr_designation_deactivate, name='hr_designation_deactivate'),

    path('staff/', hr_staff_list, name='hr_staff_list'),
    path('staff/add/', hr_staff_create, name='hr_staff_create'),
    path('staff/<int:pk>/edit/', hr_staff_update, name='hr_staff_update'),
    path('staff/<int:pk>/deactivate/', hr_staff_deactivate, name='hr_staff_deactivate'),

    path('teacher-subjects/', hr_teacher_subject_list, name='hr_teacher_subject_list'),
    path('teacher-subjects/add/', hr_teacher_subject_create, name='hr_teacher_subject_create'),
    path('teacher-subjects/<int:pk>/edit/', hr_teacher_subject_update, name='hr_teacher_subject_update'),
    path('teacher-subjects/<int:pk>/deactivate/', hr_teacher_subject_deactivate, name='hr_teacher_subject_deactivate'),

    path('class-teachers/', hr_class_teacher_list, name='hr_class_teacher_list'),
    path('class-teachers/add/', hr_class_teacher_create, name='hr_class_teacher_create'),
    path('class-teachers/<int:pk>/edit/', hr_class_teacher_update, name='hr_class_teacher_update'),
    path('class-teachers/<int:pk>/deactivate/', hr_class_teacher_deactivate, name='hr_class_teacher_deactivate'),

    path('attendance/', hr_staff_attendance_list, name='hr_staff_attendance_list'),
    path('attendance/mark/', hr_staff_attendance_mark, name='hr_staff_attendance_mark'),
    path('attendance/<int:pk>/edit/', hr_staff_attendance_edit, name='hr_staff_attendance_edit'),

    path('leave/', hr_leave_request_list, name='hr_leave_request_list'),
    path('leave/add/', hr_leave_request_create, name='hr_leave_request_create'),
    path('leave/<int:pk>/review/', hr_leave_request_review, name='hr_leave_request_review'),

    path('substitutions/', hr_substitution_list, name='hr_substitution_list'),
    path('substitutions/add/', hr_substitution_create, name='hr_substitution_create'),
    path('substitutions/<int:pk>/edit/', hr_substitution_update, name='hr_substitution_update'),
    path('substitutions/<int:pk>/deactivate/', hr_substitution_deactivate, name='hr_substitution_deactivate'),

    path('salary/', hr_salary_structure_list, name='hr_salary_structure_list'),
]
