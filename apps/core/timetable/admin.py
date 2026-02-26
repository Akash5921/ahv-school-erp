from django.contrib import admin

from .models import TimetableEntry


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = (
        'session',
        'school_class',
        'section',
        'day_of_week',
        'period',
        'subject',
        'teacher',
        'is_active',
    )
    list_filter = ('school', 'session', 'day_of_week', 'is_active')
    search_fields = (
        'school_class__name',
        'section__name',
        'subject__name',
        'subject__code',
        'teacher__employee_id',
        'teacher__user__username',
    )
