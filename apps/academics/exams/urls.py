from django.urls import path

from .views import (
    exam_delete,
    exam_manage,
    exam_schedule_delete,
    exam_schedule_manage,
    exam_schedule_update,
    exam_toggle_publish,
    exam_update,
    parent_exam_schedule,
    teacher_exam_schedule,
)


urlpatterns = [
    path('manage/', exam_manage, name='exam_manage'),
    path('manage/<int:pk>/edit/', exam_update, name='exam_update'),
    path('manage/<int:pk>/toggle-publish/', exam_toggle_publish, name='exam_toggle_publish'),
    path('manage/<int:pk>/delete/', exam_delete, name='exam_delete'),
    path('manage/<int:exam_id>/schedules/', exam_schedule_manage, name='exam_schedule_manage'),
    path(
        'manage/<int:exam_id>/schedules/<int:pk>/edit/',
        exam_schedule_update,
        name='exam_schedule_update'
    ),
    path(
        'manage/<int:exam_id>/schedules/<int:pk>/delete/',
        exam_schedule_delete,
        name='exam_schedule_delete'
    ),
    path('teacher/', teacher_exam_schedule, name='teacher_exam_schedule'),
    path('parent/', parent_exam_schedule, name='parent_exam_schedule'),
]
