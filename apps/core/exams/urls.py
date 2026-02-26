from django.urls import path

from .views import (
    exam_create,
    exam_list,
    exam_lock,
    exam_result_generate,
    exam_result_summary,
    exam_subject_deactivate,
    exam_subject_manage,
    exam_subject_update,
    exam_type_create,
    exam_type_deactivate,
    exam_type_list,
    exam_type_update,
    exam_update,
    grade_scale_create,
    grade_scale_deactivate,
    grade_scale_list,
    grade_scale_update,
    marks_entry,
    report_card_bulk_download,
    report_card_download,
)

urlpatterns = [
    path('types/', exam_type_list, name='exam_type_list'),
    path('types/add/', exam_type_create, name='exam_type_create'),
    path('types/<int:pk>/edit/', exam_type_update, name='exam_type_update'),
    path('types/<int:pk>/deactivate/', exam_type_deactivate, name='exam_type_deactivate'),

    path('manage/', exam_list, name='exam_list_core'),
    path('manage/add/', exam_create, name='exam_create_core'),
    path('manage/<int:pk>/edit/', exam_update, name='exam_update_core'),
    path('manage/<int:pk>/lock/', exam_lock, name='exam_lock_core'),
    path('manage/<int:exam_id>/subjects/', exam_subject_manage, name='exam_subject_manage'),
    path('manage/<int:exam_id>/subjects/<int:pk>/edit/', exam_subject_update, name='exam_subject_update'),
    path('manage/<int:exam_id>/subjects/<int:pk>/deactivate/', exam_subject_deactivate, name='exam_subject_deactivate'),

    path('grades/', grade_scale_list, name='grade_scale_list_core'),
    path('grades/add/', grade_scale_create, name='grade_scale_create_core'),
    path('grades/<int:pk>/edit/', grade_scale_update, name='grade_scale_update_core'),
    path('grades/<int:pk>/deactivate/', grade_scale_deactivate, name='grade_scale_deactivate_core'),

    path('marks-entry/', marks_entry, name='marks_entry_core'),

    path('results/<int:exam_id>/', exam_result_summary, name='exam_result_summary'),
    path('results/<int:exam_id>/generate/', exam_result_generate, name='exam_result_generate'),
    path('results/<int:exam_id>/report-card/<int:student_id>/', report_card_download, name='report_card_download'),
    path('results/<int:exam_id>/report-card-bulk/', report_card_bulk_download, name='report_card_bulk_download'),
]
