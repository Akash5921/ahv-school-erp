from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import Period, SchoolClass, Section
from apps.core.hr.models import Staff, StaffAttendance
from apps.core.students.models import Student


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _month_choices():
    return [(index, str(index)) for index in range(1, 13)]


def _extract_choice_id(value):
    if value is None:
        return None
    return str(getattr(value, 'id', value))


class StaffAttendanceFilterForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=False)
    date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    staff = forms.ModelChoiceField(queryset=Staff.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.allow_staff_selection = kwargs.pop('allow_staff_selection', True)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
            self.fields['staff'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).select_related('user').order_by('employee_id')

        if not self.allow_staff_selection:
            self.fields['staff'].widget = forms.HiddenInput()


class StaffAttendanceMarkForm(forms.ModelForm):
    class Meta:
        model = StaffAttendance
        fields = ['session', 'staff', 'date', 'check_in_time', 'check_out_time', 'status']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'check_in_time': forms.TimeInput(attrs={'type': 'time'}),
            'check_out_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.actor_staff = kwargs.pop('actor_staff', None)
        self.lock_staff = kwargs.pop('lock_staff', False)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['staff'].queryset = Staff.objects.none()

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
            self.fields['staff'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).select_related('user').order_by('employee_id')

        if self.default_session and not self.instance.session_id and not self.is_bound:
            self.initial.setdefault('session', self.default_session)

        if self.actor_staff and self.lock_staff:
            self.fields['staff'].queryset = Staff.objects.filter(id=self.actor_staff.id)
            self.fields['staff'].initial = self.actor_staff
            self.fields['staff'].widget = forms.HiddenInput()

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session

    def clean_staff(self):
        staff = self.cleaned_data.get('staff')
        if self.school and staff and staff.school_id != self.school.id:
            raise ValidationError('Selected staff does not belong to your school.')
        if self.actor_staff and self.lock_staff and staff and staff.id != self.actor_staff.id:
            raise ValidationError('You can mark attendance only for yourself.')
        return staff


class StudentDailyAttendanceSelectionForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), label='Class')
    section = forms.ModelChoiceField(queryset=Section.objects.none())
    target_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        selected_session_id = None
        selected_class_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        else:
            if self.initial.get('session'):
                selected_session_id = _extract_choice_id(self.initial['session'])
            elif self.default_session:
                selected_session_id = str(self.default_session.id)
                self.initial.setdefault('session', self.default_session.id)

            if self.initial.get('school_class'):
                selected_class_id = _extract_choice_id(self.initial['school_class'])

        classes = SchoolClass.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('display_order', 'name')
        if selected_session_id:
            classes = classes.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = classes

        sections = Section.objects.filter(
            school_class__school=self.school,
            is_active=True,
        ).select_related('school_class').order_by('name')
        if selected_class_id:
            sections = sections.filter(school_class_id=selected_class_id)
        else:
            sections = sections.none()
        self.fields['section'].queryset = sections

    def clean(self):
        cleaned_data = super().clean()
        session = cleaned_data.get('session')
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')

        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        if school_class and school_class.school_id != self.school.id:
            raise ValidationError('Selected class does not belong to your school.')
        if session and school_class and school_class.session_id != session.id:
            raise ValidationError('Selected class does not belong to selected session.')
        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')
        return cleaned_data


class StudentPeriodAttendanceSelectionForm(StudentDailyAttendanceSelectionForm):
    period = forms.ModelChoiceField(queryset=Period.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['period'].queryset = Period.objects.none()

        if not self.school:
            return

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        else:
            if self.initial.get('session'):
                selected_session_id = _extract_choice_id(self.initial['session'])
            elif self.default_session:
                selected_session_id = str(self.default_session.id)

        periods = Period.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('period_number')
        if selected_session_id:
            periods = periods.filter(session_id=selected_session_id)
        else:
            periods = periods.none()
        self.fields['period'].queryset = periods

    def clean(self):
        cleaned_data = super().clean()
        period = cleaned_data.get('period')
        session = cleaned_data.get('session')

        if period and period.school_id != self.school.id:
            raise ValidationError('Selected period does not belong to your school.')
        if session and period and period.session_id != session.id:
            raise ValidationError('Selected period does not belong to selected session.')
        return cleaned_data


class AttendanceLockForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    target_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), required=False, label='Class')
    section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        selected_session_id = None
        selected_class_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        else:
            if self.initial.get('session'):
                selected_session_id = _extract_choice_id(self.initial['session'])
            elif self.default_session:
                selected_session_id = str(self.default_session.id)
                self.initial.setdefault('session', self.default_session.id)
            if self.initial.get('school_class'):
                selected_class_id = _extract_choice_id(self.initial['school_class'])

        classes = SchoolClass.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('display_order', 'name')
        if selected_session_id:
            classes = classes.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = classes

        sections = Section.objects.filter(
            school_class__school=self.school,
            is_active=True,
        ).order_by('name')
        if selected_class_id:
            sections = sections.filter(school_class_id=selected_class_id)
        else:
            sections = sections.none()
        self.fields['section'].queryset = sections

    def clean(self):
        cleaned_data = super().clean()
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        session = cleaned_data.get('session')

        if school_class and school_class.school_id != self.school.id:
            raise ValidationError('Selected class does not belong to your school.')
        if session and school_class and school_class.session_id != session.id:
            raise ValidationError('Selected class does not belong to selected session.')
        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')
        return cleaned_data


class ClassAttendanceReportForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), label='Class')
    section = forms.ModelChoiceField(queryset=Section.objects.none())
    date_from = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        selected_session_id = None
        selected_class_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        else:
            if self.default_session:
                self.initial.setdefault('session', self.default_session.id)
                selected_session_id = str(self.default_session.id)
            if self.initial.get('school_class'):
                selected_class_id = _extract_choice_id(self.initial['school_class'])

        classes = SchoolClass.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('display_order', 'name')
        if selected_session_id:
            classes = classes.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = classes

        sections = Section.objects.filter(
            school_class__school=self.school,
            is_active=True,
        ).order_by('name')
        if selected_class_id:
            sections = sections.filter(school_class_id=selected_class_id)
        else:
            sections = sections.none()
        self.fields['section'].queryset = sections

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        session = cleaned_data.get('session')

        if date_from and date_to and date_from > date_to:
            raise ValidationError('From date must be before or equal to to date.')
        if school_class and session and school_class.session_id != session.id:
            raise ValidationError('Selected class does not belong to selected session.')
        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')
        return cleaned_data


class StudentMonthlyReportForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    student = forms.ModelChoiceField(queryset=Student.objects.none())
    year = forms.IntegerField(min_value=2000, max_value=2100)
    month = forms.TypedChoiceField(choices=_month_choices(), coerce=int)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['student'].queryset = Student.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)
        self.fields['student'].queryset = Student.objects.filter(
            school=self.school,
            is_archived=False,
        ).order_by('admission_number')

        if not self.is_bound:
            today = date.today()
            self.initial.setdefault('year', today.year)
            self.initial.setdefault('month', today.month)
            if self.default_session:
                self.initial.setdefault('session', self.default_session.id)

    def clean(self):
        cleaned_data = super().clean()
        session = cleaned_data.get('session')
        student = cleaned_data.get('student')
        if session and student and student.school_id != session.school_id:
            raise ValidationError('Student does not belong to selected session school.')
        return cleaned_data


class StaffAttendanceReportForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    date_from = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    staff = forms.ModelChoiceField(queryset=Staff.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['staff'].queryset = Staff.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)
        self.fields['staff'].queryset = Staff.objects.filter(
            school=self.school,
            is_active=True,
        ).select_related('user').order_by('employee_id')

        if not self.is_bound and self.default_session:
            self.initial.setdefault('session', self.default_session.id)

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')

        if date_from and date_to and date_from > date_to:
            raise ValidationError('From date must be before or equal to to date.')
        return cleaned_data


class ThresholdReportForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    year = forms.IntegerField(min_value=2000, max_value=2100)
    month = forms.TypedChoiceField(choices=_month_choices(), coerce=int)
    threshold = forms.DecimalField(min_value=0, max_value=100, decimal_places=2, max_digits=5)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

        if not self.is_bound:
            today = date.today()
            self.initial.setdefault('year', today.year)
            self.initial.setdefault('month', today.month)
            self.initial.setdefault('threshold', 75)
            if self.default_session:
                self.initial.setdefault('session', self.default_session.id)


class DailyAbsenteeReportForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    target_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), required=False, label='Class')
    section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        selected_session_id = None
        selected_class_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        else:
            if self.default_session:
                self.initial.setdefault('session', self.default_session.id)
                selected_session_id = str(self.default_session.id)
            if self.initial.get('school_class'):
                selected_class_id = _extract_choice_id(self.initial['school_class'])
            self.initial.setdefault('target_date', date.today())

        classes = SchoolClass.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('display_order', 'name')
        if selected_session_id:
            classes = classes.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = classes

        sections = Section.objects.filter(
            school_class__school=self.school,
            is_active=True,
        ).order_by('name')
        if selected_class_id:
            sections = sections.filter(school_class_id=selected_class_id)
        else:
            sections = sections.none()
        self.fields['section'].queryset = sections

    def clean(self):
        cleaned_data = super().clean()
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        session = cleaned_data.get('session')
        if school_class and session and school_class.session_id != session.id:
            raise ValidationError('Selected class does not belong to selected session.')
        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')
        return cleaned_data
