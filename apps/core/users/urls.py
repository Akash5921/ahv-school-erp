from django.urls import path

from .views import role_redirect, role_workspace

urlpatterns = [
    path('dashboard/', role_redirect, name='role_redirect'),
    path('dashboard/workspace/', role_workspace, name='role_workspace'),
]
