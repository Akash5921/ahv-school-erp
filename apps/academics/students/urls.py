from django.urls import path
from .views import (
    add_marks,
    student_list,
    student_create,
    student_report,
    student_update,
    student_delete,
    student_detail
)



urlpatterns = [
    path('', student_list, name='student_list'),
    path('create/', student_create, name='student_create'),
    path('<int:pk>/edit/', student_update, name='student_update'),
    path('<int:pk>/delete/', student_delete, name='student_delete'),
    path('<int:pk>/', student_detail, name='student_detail'),
    path('add/marks/', add_marks, name='add_marks'),
    path('<int:student_id>/report/', student_report, name='student_report'),
]
