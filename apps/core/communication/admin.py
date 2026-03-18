from django.contrib import admin

from .models import (
    Announcement,
    EmailLog,
    GlobalSettings,
    Message,
    MessageThread,
    MessageThreadParticipant,
    Notification,
    ParentStudentLink,
    ParentUser,
    SMSLog,
)


class HistoryProtectedAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = ('school', 'email_enabled', 'sms_enabled', 'updated_at')
    search_fields = ('school__name', 'school__code')


@admin.register(ParentUser)
class ParentUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'school', 'parent_info', 'is_active', 'updated_at')
    list_filter = ('school', 'is_active')
    search_fields = ('user__username', 'user__email', 'parent_info__student__admission_number')


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = ('parent_user', 'student', 'is_primary', 'created_at')
    list_filter = ('parent_user__school', 'is_primary')
    search_fields = ('parent_user__user__username', 'student__admission_number', 'student__first_name')


@admin.register(Announcement)
class AnnouncementAdmin(HistoryProtectedAdmin):
    list_display = ('title', 'school', 'session', 'target_role', 'school_class', 'section', 'is_active', 'expires_at')
    list_filter = ('school', 'session', 'target_role', 'is_active')
    search_fields = ('title', 'message')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_expired:
            return tuple(field.name for field in self.model._meta.fields)
        return super().get_readonly_fields(request, obj=obj)


@admin.register(MessageThread)
class MessageThreadAdmin(HistoryProtectedAdmin):
    list_display = ('subject', 'school', 'session', 'created_by', 'created_at', 'updated_at')
    list_filter = ('school', 'session')
    search_fields = ('subject', 'created_by__username')


@admin.register(MessageThreadParticipant)
class MessageThreadParticipantAdmin(HistoryProtectedAdmin):
    list_display = ('thread', 'user', 'joined_at', 'last_read_at')
    list_filter = ('thread__school',)
    search_fields = ('thread__subject', 'user__username')


@admin.register(Message)
class MessageAdmin(HistoryProtectedAdmin):
    list_display = ('thread', 'sender', 'receiver', 'sent_at', 'is_read', 'edited_at')
    list_filter = ('thread__school', 'is_read')
    search_fields = ('thread__subject', 'sender__username', 'receiver__username', 'message_text')


@admin.register(Notification)
class NotificationAdmin(HistoryProtectedAdmin):
    list_display = ('user', 'title', 'school', 'session', 'is_read', 'created_at')
    list_filter = ('school', 'session', 'is_read')
    search_fields = ('user__username', 'title', 'message', 'event_key')


@admin.register(EmailLog)
class EmailLogAdmin(HistoryProtectedAdmin):
    list_display = ('recipient', 'subject', 'status', 'school', 'session', 'timestamp')
    list_filter = ('school', 'session', 'status')
    search_fields = ('recipient', 'subject', 'error_message')


@admin.register(SMSLog)
class SMSLogAdmin(HistoryProtectedAdmin):
    list_display = ('recipient_number', 'status', 'school', 'session', 'timestamp')
    list_filter = ('school', 'session', 'status')
    search_fields = ('recipient_number', 'message', 'error_message')
