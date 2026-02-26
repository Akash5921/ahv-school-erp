from django.urls import path

from .views import (
    homework_delete,
    homework_manage,
    homework_toggle_publish,
    homework_update,
    parent_homework_list,
)


urlpatterns = [
    path('manage/', homework_manage, name='homework_manage'),
    path('manage/<int:pk>/edit/', homework_update, name='homework_update'),
    path('manage/<int:pk>/toggle-publish/', homework_toggle_publish, name='homework_toggle_publish'),
    path('manage/<int:pk>/delete/', homework_delete, name='homework_delete'),
    path('parent/', parent_homework_list, name='parent_homework_list'),
]
