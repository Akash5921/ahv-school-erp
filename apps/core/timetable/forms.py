from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import Period, SchoolClass, Section, Subject
from apps.core.hr.models import Staff

from .models import TimetableEntry
from .services import get_available_teachers


class TimetableEntryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.fixed_session = kwargs.pop('session', None)
        self.fixed_class = kwargs.pop('school_class', None)
        self.fixed_section = kwargs.pop('section', None)
        self.fixed_day = kwargs.pop('day_of_week', None)
        self.fixed_period = kwargs.pop('period', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        selected_session = self.fixed_session or getattr(self.instance, 'session', None)
        selected_class = self.fixed_class or getattr(self.instance, 'school_class', None)
        selected_day = self.fixed_day or getattr(self.instance, 'day_of_week', None)
        selected_period = self.fixed_period or getattr(self.instance, 'period', None)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()
        self.fields['period'].queryset = Period.objects.none()
        self.fields['subject'].queryset = Subject.objects.none()
        self.fields['teacher'].queryset = Staff.objects.none()

        if self.school:
            self.fields['session'].queryset = AcademicSession.objects.filter(school=self.school).order_by('-start_date')

            classes = SchoolClass.objects.filter(school=self.school, is_active=True)
            if selected_session:
                classes = classes.filter(session=selected_session)
            self.fields['school_class'].queryset = classes.order_by('display_order', 'name')

            selected_class_id = selected_class.id if selected_class else None
            sections = Section.objects.filter(school_class__school=self.school, is_active=True)
            if selected_class_id:
                sections = sections.filter(school_class_id=selected_class_id)
            self.fields['section'].queryset = sections.order_by('name')

            periods = Period.objects.filter(school=self.school, is_active=True)
            if selected_session:
                periods = periods.filter(session=selected_session)
            self.fields['period'].queryset = periods.order_by('period_number')

            subjects = Subject.objects.filter(school=self.school, is_active=True)
            self.fields['subject'].queryset = subjects.order_by('name')

            if selected_session and selected_class and selected_day and selected_period:
                selected_subject = None
                if self.is_bound:
                    selected_subject = self.cleaned_data.get('subject') if hasattr(self, 'cleaned_data') else None
                    if not selected_subject:
                        subject_id = self.data.get('subject')
                        selected_subject = Subject.objects.filter(id=subject_id).first() if subject_id else None
                else:
                    selected_subject = getattr(self.instance, 'subject', None)

                if selected_subject:
                    self.fields['teacher'].queryset = get_available_teachers(
                        school=self.school,
                        session=selected_session,
                        school_class=selected_class,
                        subject=selected_subject,
                        day_of_week=selected_day,
                        period=selected_period,
                        exclude_entry=self.instance if self.instance.pk else None,
                    )
                else:
                    self.fields['teacher'].queryset = Staff.objects.filter(
                        school=self.school,
                        is_active=True,
                        user__role='teacher',
                    ).order_by('employee_id')

        for field_name, field_value in [
            ('session', self.fixed_session),
            ('school_class', self.fixed_class),
            ('section', self.fixed_section),
            ('day_of_week', self.fixed_day),
            ('period', self.fixed_period),
        ]:
            if field_value is not None:
                self.fields[field_name].initial = field_value
                self.fields[field_name].widget = forms.HiddenInput()

    class Meta:
        model = TimetableEntry
        fields = [
            'session',
            'school_class',
            'section',
            'day_of_week',
            'period',
            'subject',
            'teacher',
            'is_active',
        ]

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session

    def clean_school_class(self):
        school_class = self.cleaned_data.get('school_class')
        if self.school and school_class and school_class.school_id != self.school.id:
            raise ValidationError('Selected class does not belong to your school.')
        return school_class

    def clean_section(self):
        section = self.cleaned_data.get('section')
        school_class = self.cleaned_data.get('school_class')
        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')
        return section

    def clean_period(self):
        period = self.cleaned_data.get('period')
        if self.school and period and period.school_id != self.school.id:
            raise ValidationError('Selected period does not belong to your school.')
        return period

    def clean_teacher(self):
        teacher = self.cleaned_data.get('teacher')
        if self.school and teacher and teacher.school_id != self.school.id:
            raise ValidationError('Selected teacher does not belong to your school.')
        return teacher


class TimetableSelectionForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=False)
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), required=False)
    section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False)
    view_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['session'].queryset = AcademicSession.objects.filter(school=self.school).order_by('-start_date')
            self.fields['school_class'].queryset = SchoolClass.objects.filter(school=self.school, is_active=True).order_by(
                'display_order', 'name'
            )

            class_id = self.data.get('school_class') if self.is_bound else self.initial.get('school_class')
            sections = Section.objects.filter(school_class__school=self.school, is_active=True)
            if class_id:
                sections = sections.filter(school_class_id=class_id)
            else:
                sections = sections.none()
            self.fields['section'].queryset = sections.order_by('name')


class TeacherTimetableFilterForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=False)
    teacher = forms.ModelChoiceField(queryset=Staff.objects.none(), required=False)
    anchor_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.allow_teacher_selection = kwargs.pop('allow_teacher_selection', False)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['session'].queryset = AcademicSession.objects.filter(school=self.school).order_by('-start_date')
            self.fields['teacher'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
                user__role='teacher',
            ).order_by('employee_id')

        if not self.allow_teacher_selection:
            self.fields['teacher'].widget = forms.HiddenInput()
