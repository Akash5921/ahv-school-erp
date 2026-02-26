from django.contrib import admin

from .models import StudentAttendance, StudentAttendanceSummary, StudentPeriodAttendance


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'student',
        'school_class',
        'section',
        'status',
        'session',
        'is_locked',
    )
    list_filter = ('school', 'session', 'status', 'is_locked', 'date')
    search_fields = (
        'student__admission_number',
        'student__first_name',
        'student__last_name',
        'school_class__name',
        'section__name',
    )


@admin.register(StudentPeriodAttendance)
class StudentPeriodAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'period',
        'student',
        'school_class',
        'section',
        'subject',
        'teacher',
        'status',
        'is_locked',
    )
    list_filter = ('school', 'session', 'status', 'period', 'is_locked', 'date')
    search_fields = (
        'student__admission_number',
        'subject__name',
        'subject__code',
        'teacher__employee_id',
    )


@admin.register(StudentAttendanceSummary)
class StudentAttendanceSummaryAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'session',
        'year',
        'month',
        'total_working_days',
        'present_days',
        'attendance_percentage',
    )
    list_filter = ('school', 'session', 'year', 'month')
    search_fields = (
        'student__admission_number',
        'student__first_name',
        'student__last_name',
    )
