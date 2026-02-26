from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession

from .models import (
    DAY_CHOICES,
    AcademicConfig,
    ClassSubject,
    Period,
    SchoolClass,
    Section,
    Subject,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class SchoolClassForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

    class Meta:
        model = SchoolClass
        fields = ['session', 'name', 'code', 'display_order', 'is_active']

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session


class SectionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.session = kwargs.pop('session', None)
        super().__init__(*args, **kwargs)

        if self.school:
            classes = SchoolClass.objects.filter(school=self.school)
            if self.session:
                classes = classes.filter(session=self.session)
            self.fields['school_class'].queryset = classes.order_by('display_order', 'name')

            user_model = get_user_model()
            self.fields['class_teacher'].queryset = user_model.objects.filter(
                school=self.school,
                role__in=['teacher', 'staff'],
                is_active=True,
            ).order_by('first_name', 'username')

    class Meta:
        model = Section
        fields = ['school_class', 'name', 'capacity', 'class_teacher', 'is_active']

    def clean_school_class(self):
        school_class = self.cleaned_data.get('school_class')
        if self.school and school_class and school_class.school_id != self.school.id:
            raise ValidationError('Selected class does not belong to your school.')
        if self.session and school_class and school_class.session_id != self.session.id:
            raise ValidationError('Selected class does not belong to the selected session.')
        return school_class

    def clean_class_teacher(self):
        class_teacher = self.cleaned_data.get('class_teacher')
        if self.school and class_teacher and class_teacher.school_id != self.school.id:
            raise ValidationError('Selected class teacher does not belong to your school.')
        return class_teacher


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'subject_type', 'is_optional', 'is_active']


class ClassSubjectForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.session = kwargs.pop('session', None)
        super().__init__(*args, **kwargs)

        if self.school:
            classes = SchoolClass.objects.filter(
                school=self.school,
                is_active=True,
            )
            if self.session:
                classes = classes.filter(session=self.session)
            self.fields['school_class'].queryset = classes.order_by('display_order', 'name')

            subjects = Subject.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('name')
            self.fields['subject'].queryset = subjects

    class Meta:
        model = ClassSubject
        fields = ['school_class', 'subject', 'is_compulsory', 'max_marks', 'pass_marks']

    def clean_school_class(self):
        school_class = self.cleaned_data.get('school_class')
        if self.school and school_class and school_class.school_id != self.school.id:
            raise ValidationError('Selected class does not belong to your school.')
        return school_class

    def clean_subject(self):
        subject = self.cleaned_data.get('subject')
        if self.school and subject and subject.school_id != self.school.id:
            raise ValidationError('Selected subject does not belong to your school.')
        if subject and not subject.is_active:
            raise ValidationError('Only active subjects can be mapped.')
        return subject


class PeriodForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

    class Meta:
        model = Period
        fields = ['session', 'period_number', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session


class AcademicConfigForm(forms.ModelForm):
    working_days = forms.MultipleChoiceField(
        choices=DAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['working_days'] = self.instance.working_days
        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

    class Meta:
        model = AcademicConfig
        fields = [
            'session',
            'total_periods_per_day',
            'working_days',
            'grading_enabled',
            'attendance_type',
            'marks_decimal_allowed',
        ]

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session

    def clean_working_days(self):
        days = self.cleaned_data.get('working_days') or []
        if not days:
            raise ValidationError('Select at least one working day.')
        return days

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.working_days = self.cleaned_data.get('working_days', [])
        if commit:
            instance.save()
        return instance
