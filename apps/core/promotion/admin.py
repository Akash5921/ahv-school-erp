from django.contrib import admin

from .models import PromotionRecord


@admin.register(PromotionRecord)
class PromotionRecordAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'from_session',
        'to_session',
        'status',
        'promoted_by',
        'promoted_on',
    )
    list_filter = ('school', 'from_session', 'to_session', 'status')
    search_fields = ('student__admission_number', 'student__first_name', 'student__last_name')
    readonly_fields = ('promoted_on',)
