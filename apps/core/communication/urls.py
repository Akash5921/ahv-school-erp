from django.urls import path

from .views import (
    communication_announcement_deactivate,
    communication_announcement_feed,
    communication_announcement_list,
    communication_announcement_update,
    communication_bulk_dispatch,
    communication_message_edit,
    communication_message_mark_read,
    communication_notification_list,
    communication_notification_mark_all_read,
    communication_notification_mark_read,
    communication_parent_portal,
    communication_parent_student_attendance,
    communication_parent_student_fees,
    communication_parent_student_marks,
    communication_parent_users,
    communication_report_dashboard,
    communication_report_emails,
    communication_report_messages,
    communication_report_notifications,
    communication_report_sms,
    communication_settings_manage,
    communication_thread_detail,
    communication_thread_list,
)

urlpatterns = [
    path('announcements/manage/', communication_announcement_list, name='communication_announcement_list_core'),
    path('announcements/<int:pk>/edit/', communication_announcement_update, name='communication_announcement_update_core'),
    path('announcements/<int:pk>/deactivate/', communication_announcement_deactivate, name='communication_announcement_deactivate_core'),
    path('announcements/feed/', communication_announcement_feed, name='communication_announcement_feed_core'),

    path('parent-users/', communication_parent_users, name='communication_parent_users_core'),

    path('messages/threads/', communication_thread_list, name='communication_thread_list_core'),
    path('messages/threads/<int:thread_id>/', communication_thread_detail, name='communication_thread_detail_core'),
    path('messages/<int:message_id>/edit/', communication_message_edit, name='communication_message_edit_core'),
    path('messages/<int:message_id>/read/', communication_message_mark_read, name='communication_message_mark_read_core'),

    path('notifications/', communication_notification_list, name='communication_notification_list_core'),
    path('notifications/<int:pk>/read/', communication_notification_mark_read, name='communication_notification_mark_read_core'),
    path('notifications/read-all/', communication_notification_mark_all_read, name='communication_notification_mark_all_read_core'),

    path('settings/', communication_settings_manage, name='communication_settings_core'),
    path('bulk-dispatch/', communication_bulk_dispatch, name='communication_bulk_dispatch_core'),

    path('reports/', communication_report_dashboard, name='communication_report_dashboard_core'),
    path('reports/messages/', communication_report_messages, name='communication_report_messages_core'),
    path('reports/emails/', communication_report_emails, name='communication_report_emails_core'),
    path('reports/sms/', communication_report_sms, name='communication_report_sms_core'),
    path('reports/notifications/', communication_report_notifications, name='communication_report_notifications_core'),

    path('parent/portal/', communication_parent_portal, name='communication_parent_portal_core'),
    path('parent/students/<int:student_id>/attendance/', communication_parent_student_attendance, name='communication_parent_student_attendance_core'),
    path('parent/students/<int:student_id>/marks/', communication_parent_student_marks, name='communication_parent_student_marks_core'),
    path('parent/students/<int:student_id>/fees/', communication_parent_student_fees, name='communication_parent_student_fees_core'),
]
