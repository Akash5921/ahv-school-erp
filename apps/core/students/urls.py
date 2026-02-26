from django.urls import path

from .views import (
    document_type_create,
    document_type_deactivate,
    document_type_list,
    document_type_update,
    student_archive,
    student_create,
    student_document_list,
    student_document_verify,
    student_finalize_admission,
    student_id_card_bulk_download,
    student_id_card_download,
    student_list,
    student_parent_update,
    student_status_update,
    student_transfer_certificate_download,
    student_update,
)

urlpatterns = [
    path('', student_list, name='student_list'),
    path('add/', student_create, name='student_create'),
    path('<int:pk>/edit/', student_update, name='student_update'),
    path('<int:pk>/archive/', student_archive, name='student_archive'),

    path('<int:pk>/parent/', student_parent_update, name='student_parent_update'),
    path('<int:pk>/status/', student_status_update, name='student_status_update'),

    path('documents/types/', document_type_list, name='document_type_list'),
    path('documents/types/add/', document_type_create, name='document_type_create'),
    path('documents/types/<int:pk>/edit/', document_type_update, name='document_type_update'),
    path('documents/types/<int:pk>/deactivate/', document_type_deactivate, name='document_type_deactivate'),

    path('<int:pk>/documents/', student_document_list, name='student_document_list'),
    path(
        '<int:student_pk>/documents/<int:document_pk>/verify/',
        student_document_verify,
        name='student_document_verify',
    ),
    path('<int:pk>/finalize/', student_finalize_admission, name='student_finalize_admission'),

    path('<int:pk>/id-card/', student_id_card_download, name='student_id_card_download'),
    path('id-cards/bulk/', student_id_card_bulk_download, name='student_id_card_bulk_download'),
    path(
        '<int:pk>/transfer-certificate/',
        student_transfer_certificate_download,
        name='student_transfer_certificate_download',
    ),
]
