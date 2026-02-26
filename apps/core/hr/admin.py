from django.contrib import admin

from .models import (
    ClassTeacher,
    Designation,
    LeaveRequest,
    SalaryHistory,
    SalaryStructure,
    Staff,
    StaffAttendance,
    Substitution,
    TeacherSubjectAssignment,
)


@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'is_active')
    list_filter = ('school', 'is_active')
    search_fields = ('name',)


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'designation', 'school', 'status', 'is_active')
    list_filter = ('school', 'status', 'is_active', 'designation')
    search_fields = ('employee_id', 'user__username', 'user__first_name', 'user__last_name')


@admin.register(TeacherSubjectAssignment)
class TeacherSubjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'school_class', 'subject', 'session', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('teacher__employee_id', 'subject__name', 'subject__code', 'school_class__name')


@admin.register(ClassTeacher)
class ClassTeacherAdmin(admin.ModelAdmin):
    list_display = ('school_class', 'section', 'teacher', 'session', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('teacher__employee_id', 'school_class__name', 'section__name')


@admin.register(StaffAttendance)
class StaffAttendanceAdmin(admin.ModelAdmin):
    list_display = ('staff', 'date', 'status', 'check_in_time', 'check_out_time', 'marked_by')
    list_filter = ('school', 'date', 'status')
    search_fields = ('staff__employee_id', 'staff__user__username')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('staff', 'leave_type', 'start_date', 'end_date', 'status', 'approved_by')
    list_filter = ('school', 'status', 'leave_type')
    search_fields = ('staff__employee_id', 'staff__user__username')


@admin.register(Substitution)
class SubstitutionAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'period',
        'school_class',
        'section',
        'subject',
        'original_teacher',
        'substitute_teacher',
        'is_active',
    )
    list_filter = ('school', 'session', 'date', 'is_active')
    search_fields = ('subject__name', 'school_class__name', 'original_teacher__employee_id', 'substitute_teacher__employee_id')


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ('staff', 'basic_salary', 'effective_from', 'is_active')
    list_filter = ('school', 'is_active')
    search_fields = ('staff__employee_id', 'staff__user__username')


@admin.register(SalaryHistory)
class SalaryHistoryAdmin(admin.ModelAdmin):
    list_display = ('staff', 'old_salary', 'new_salary', 'changed_on', 'changed_by')
    list_filter = ('school', 'changed_on')
    search_fields = ('staff__employee_id',)
