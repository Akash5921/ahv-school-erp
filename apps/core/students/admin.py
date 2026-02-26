from django.contrib import admin

from .models import (
    DocumentType,
    Parent,
    Student,
    StudentDocument,
    StudentSessionRecord,
    StudentStatusHistory,
    StudentSubject,
)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        'admission_number',
        'first_name',
        'last_name',
        'school',
        'session',
        'current_class',
        'current_section',
        'status',
        'is_active',
    )
    list_filter = ('school', 'session', 'status', 'admission_type', 'is_active', 'is_archived')
    search_fields = ('admission_number', 'first_name', 'last_name')


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('student', 'guardian_name', 'phone', 'email')
    search_fields = ('student__admission_number', 'father_name', 'mother_name', 'guardian_name', 'phone')


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'required_for', 'is_mandatory', 'is_active')
    list_filter = ('school', 'required_for', 'is_mandatory', 'is_active')
    search_fields = ('name',)


@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display = ('student', 'document_type', 'status', 'uploaded_at', 'verified_by')
    list_filter = ('status', 'document_type__school')
    search_fields = ('student__admission_number', 'document_type__name')


@admin.register(StudentSubject)
class StudentSubjectAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'school_class', 'session', 'is_active')
    list_filter = ('session', 'is_active')
    search_fields = ('student__admission_number', 'subject__name', 'subject__code')


@admin.register(StudentStatusHistory)
class StudentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('student', 'old_status', 'new_status', 'changed_by', 'changed_at')
    list_filter = ('new_status', 'old_status')
    search_fields = ('student__admission_number',)


@admin.register(StudentSessionRecord)
class StudentSessionRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'session', 'school_class', 'section', 'status', 'is_current')
    list_filter = ('session', 'is_current', 'status')
    search_fields = ('student__admission_number',)
