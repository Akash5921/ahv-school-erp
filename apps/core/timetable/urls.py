from django.urls import path

from .views import (
    timetable_cell_deactivate,
    timetable_cell_edit,
    timetable_class_grid,
    timetable_class_pdf,
    timetable_teacher_pdf,
    timetable_teacher_view,
)

urlpatterns = [
    path('class-grid/', timetable_class_grid, name='timetable_class_grid'),
    path(
        'class-grid/<int:class_id>/<int:section_id>/<str:day_of_week>/<int:period_id>/edit/',
        timetable_cell_edit,
        name='timetable_cell_edit',
    ),
    path(
        'class-grid/<int:class_id>/<int:section_id>/<str:day_of_week>/<int:period_id>/deactivate/',
        timetable_cell_deactivate,
        name='timetable_cell_deactivate',
    ),
    path('class-grid/<int:class_id>/<int:section_id>/pdf/', timetable_class_pdf, name='timetable_class_pdf'),

    path('teacher/', timetable_teacher_view, name='timetable_teacher_view'),
    path('teacher/pdf/', timetable_teacher_pdf, name='timetable_teacher_pdf'),
]
