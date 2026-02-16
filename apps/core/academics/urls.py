from django.urls import path
from .views import (
    class_list, class_create, class_update, class_delete,
    section_list, section_create, section_update, section_delete
)

urlpatterns = [
    path('classes/', class_list, name='class_list'),
    path('classes/add/', class_create, name='class_create'),
    path('classes/<int:pk>/edit/', class_update, name='class_update'),
    path('classes/<int:pk>/delete/', class_delete, name='class_delete'),

    path('sections/', section_list, name='section_list'),
    path('sections/add/', section_create, name='section_create'),
    path('sections/<int:pk>/edit/', section_update, name='section_update'),
    path('sections/<int:pk>/delete/', section_delete, name='section_delete'),
]
