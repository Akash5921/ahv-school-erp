from django.urls import path

from .views import (
    parent_timetable,
    teacher_timetable,
    timetable_delete,
    timetable_manage,
    timetable_update,
)


urlpatterns = [
    path('manage/', timetable_manage, name='timetable_manage'),
    path('manage/<int:pk>/edit/', timetable_update, name='timetable_update'),
    path('manage/<int:pk>/delete/', timetable_delete, name='timetable_delete'),
    path('teacher/', teacher_timetable, name='teacher_timetable'),
    path('parent/', parent_timetable, name='parent_timetable'),
]
