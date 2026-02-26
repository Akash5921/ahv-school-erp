from django.urls import path

from .views import (
    academic_config_create,
    academic_config_list,
    academic_config_update,
    class_create,
    class_deactivate,
    class_list,
    class_subject_create,
    class_subject_delete,
    class_subject_list,
    class_subject_update,
    class_update,
    period_create,
    period_deactivate,
    period_list,
    period_update,
    section_create,
    section_deactivate,
    section_list,
    section_update,
    subject_create,
    subject_deactivate,
    subject_list,
    subject_update,
)

urlpatterns = [
    path('classes/', class_list, name='class_list'),
    path('classes/add/', class_create, name='class_create'),
    path('classes/<int:pk>/edit/', class_update, name='class_update'),
    path('classes/<int:pk>/deactivate/', class_deactivate, name='class_deactivate'),

    path('sections/', section_list, name='section_list'),
    path('sections/add/', section_create, name='section_create'),
    path('sections/<int:pk>/edit/', section_update, name='section_update'),
    path('sections/<int:pk>/deactivate/', section_deactivate, name='section_deactivate'),

    path('subjects/', subject_list, name='subject_list'),
    path('subjects/add/', subject_create, name='subject_create'),
    path('subjects/<int:pk>/edit/', subject_update, name='subject_update'),
    path('subjects/<int:pk>/deactivate/', subject_deactivate, name='subject_deactivate'),

    path('class-subjects/', class_subject_list, name='class_subject_list'),
    path('class-subjects/add/', class_subject_create, name='class_subject_create'),
    path('class-subjects/<int:pk>/edit/', class_subject_update, name='class_subject_update'),
    path('class-subjects/<int:pk>/delete/', class_subject_delete, name='class_subject_delete'),

    path('periods/', period_list, name='period_list'),
    path('periods/add/', period_create, name='period_create'),
    path('periods/<int:pk>/edit/', period_update, name='period_update'),
    path('periods/<int:pk>/deactivate/', period_deactivate, name='period_deactivate'),

    path('config/', academic_config_list, name='academic_config_list'),
    path('config/add/', academic_config_create, name='academic_config_create'),
    path('config/<int:pk>/edit/', academic_config_update, name='academic_config_update'),
]
