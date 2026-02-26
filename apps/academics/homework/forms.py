from django import forms

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject

from .models import Homework


class HomeworkForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                school=self.school
            ).order_by('-start_date')
            self.fields['school_class'].queryset = SchoolClass.objects.filter(
                school=self.school
            ).order_by('order', 'name')
            self.fields['section'].queryset = Section.objects.filter(
                school_class__school=self.school
            ).order_by('school_class__order', 'name')
            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school
            ).select_related('school_class').order_by('school_class__order', 'name')

    class Meta:
        model = Homework
        fields = [
            'academic_session',
            'school_class',
            'section',
            'subject',
            'title',
            'description',
            'due_date',
            'is_published',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        academic_session = cleaned_data.get('academic_session')
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        subject = cleaned_data.get('subject')

        if section and school_class and section.school_class_id != school_class.id:
            self.add_error('section', 'Selected section does not belong to the selected class.')

        if subject and school_class and subject.school_class_id != school_class.id:
            self.add_error('subject', 'Selected subject does not belong to the selected class.')

        if self.school:
            if academic_session and academic_session.school_id != self.school.id:
                self.add_error('academic_session', 'Selected session does not belong to your school.')
            if school_class and school_class.school_id != self.school.id:
                self.add_error('school_class', 'Selected class does not belong to your school.')
            if section and section.school_class.school_id != self.school.id:
                self.add_error('section', 'Selected section does not belong to your school.')
            if subject and subject.school_id != self.school.id:
                self.add_error('subject', 'Selected subject does not belong to your school.')

        return cleaned_data
