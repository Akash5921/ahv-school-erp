from django.contrib import admin

from .models import Exam, ExamResultSummary, ExamSubject, ExamType, GradeScale, StudentMark


@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'session', 'weightage', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('name',)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        'exam_type',
        'school_class',
        'section',
        'session',
        'start_date',
        'end_date',
        'is_locked',
        'is_active',
    )
    list_filter = ('school', 'session', 'exam_type', 'is_locked', 'is_active')
    search_fields = ('exam_type__name', 'school_class__name', 'section__name')


@admin.register(ExamSubject)
class ExamSubjectAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'max_marks', 'pass_marks', 'is_active')
    list_filter = ('exam__school', 'exam__session', 'is_active')
    search_fields = ('exam__exam_type__name', 'subject__name', 'subject__code')


@admin.register(StudentMark)
class StudentMarkAdmin(admin.ModelAdmin):
    list_display = ('exam', 'student', 'subject', 'marks_obtained', 'grade', 'is_locked')
    list_filter = ('school', 'session', 'exam', 'subject', 'is_locked')
    search_fields = ('student__admission_number', 'student__first_name', 'subject__name')


@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display = ('grade_name', 'session', 'min_percentage', 'max_percentage', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('grade_name',)


@admin.register(ExamResultSummary)
class ExamResultSummaryAdmin(admin.ModelAdmin):
    list_display = ('exam', 'student', 'total_marks', 'percentage', 'grade', 'rank', 'result_status', 'is_locked')
    list_filter = ('school', 'session', 'exam', 'result_status', 'is_locked')
    search_fields = ('student__admission_number', 'student__first_name')
