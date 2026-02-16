from django.urls import path

from .views import (
    session_activate,
    session_create,
    session_delete,
    session_list,
    session_update,
)

urlpatterns = [
    path('', session_list, name='session_list'),
    path('add/', session_create, name='session_create'),
    path('<int:pk>/edit/', session_update, name='session_update'),
    path('<int:pk>/delete/', session_delete, name='session_delete'),
    path('<int:pk>/activate/', session_activate, name='session_activate'),
]
