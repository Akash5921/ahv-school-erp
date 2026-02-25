from django.urls import path

from .views import notice_feed, notice_manage, notice_mark_read, notice_toggle_publish


urlpatterns = [
    path('manage/', notice_manage, name='notice_manage'),
    path('feed/', notice_feed, name='notice_feed'),
    path('read/<int:notice_id>/', notice_mark_read, name='notice_mark_read'),
    path('toggle/<int:notice_id>/', notice_toggle_publish, name='notice_toggle_publish'),
]
