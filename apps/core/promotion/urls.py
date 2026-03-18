from django.urls import path

from .views import (
    lifecycle_dashboard,
    promotion_dashboard,
    session_close_view,
    session_unlock_view,
)

urlpatterns = [
    path('', lifecycle_dashboard, name='promotion_lifecycle'),
    path('dashboard/', promotion_dashboard, name='promotion_dashboard'),
    path('close/', session_close_view, name='promotion_session_close'),
    path('unlock/<int:pk>/', session_unlock_view, name='promotion_session_unlock'),
]
