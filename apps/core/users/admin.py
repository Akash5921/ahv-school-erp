from django.contrib import admin
from .models import User, AuditLog

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'school', 'is_staff')
    list_filter = ('role', 'school')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'user', 'school', 'target_model', 'target_id')
    list_filter = ('action', 'school', 'method', 'created_at')
    search_fields = ('details', 'path', 'target_model', 'target_id', 'user__username')
