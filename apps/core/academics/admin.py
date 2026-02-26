from django.contrib import admin

from .models import AcademicConfig, ClassSubject, Period, SchoolClass, Section, Subject


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school', 'session', 'display_order', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('name', 'code', 'school__name', 'session__name')


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'school_class', 'capacity', 'class_teacher', 'is_active')
    list_filter = ('school_class__school', 'school_class__session', 'is_active')
    search_fields = ('name', 'school_class__name', 'class_teacher__username')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'subject_type', 'school', 'is_optional', 'is_active')
    list_filter = ('school', 'subject_type', 'is_optional', 'is_active')
    search_fields = ('code', 'name', 'school__name')


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ('school_class', 'subject', 'is_compulsory', 'max_marks', 'pass_marks')
    list_filter = ('school_class__school', 'school_class__session', 'is_compulsory')
    search_fields = ('school_class__name', 'subject__name', 'subject__code')


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('school', 'session', 'period_number', 'start_time', 'end_time', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('session__name',)


@admin.register(AcademicConfig)
class AcademicConfigAdmin(admin.ModelAdmin):
    list_display = (
        'school',
        'session',
        'total_periods_per_day',
        'attendance_type',
        'grading_enabled',
        'marks_decimal_allowed',
    )
    list_filter = ('school', 'session', 'attendance_type', 'grading_enabled', 'marks_decimal_allowed')
    search_fields = ('school__name', 'session__name')
