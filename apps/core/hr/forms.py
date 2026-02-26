from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import Period, SchoolClass, Section, Subject

from .models import (
    ClassTeacher,
    Designation,
    LeaveRequest,
    Staff,
    StaffAttendance,
    Substitution,
    TeacherSubjectAssignment,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ['name', 'description', 'is_active']


class StaffForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        if self.school:
            self.fields['designation'].queryset = Designation.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('name')

            user_model = get_user_model()
            allowed_roles = ['teacher', 'staff', 'accountant']
            users = user_model.objects.filter(
                school=self.school,
                role__in=allowed_roles,
            ).order_by('first_name', 'username')

            if self.instance and self.instance.pk:
                users = users.filter(
                    Q(staff_profile__isnull=True)
                    | Q(id=self.instance.user_id)
                )
            else:
                users = users.filter(staff_profile__isnull=True)

            self.fields['user'].queryset = users

    class Meta:
        model = Staff
        fields = [
            'user',
            'employee_id',
            'joining_date',
            'designation',
            'department',
            'qualification',
            'experience_years',
            'phone',
            'address',
            'photo',
            'status',
            'is_active',
        ]
        widgets = {
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_user(self):
        user = self.cleaned_data.get('user')
        if self.school and user and user.school_id != self.school.id:
            raise ValidationError('Selected user does not belong to your school.')
        return user

    def clean_designation(self):
        designation = self.cleaned_data.get('designation')
        if self.school and designation and designation.school_id != self.school.id:
            raise ValidationError('Selected designation does not belong to your school.')
        return designation


class TeacherSubjectAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['teacher'].queryset = Staff.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['subject'].queryset = Subject.objects.none()

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
            self.fields['teacher'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
                user__role='teacher',
            ).order_by('employee_id')

            classes = SchoolClass.objects.filter(school=self.school, is_active=True)
            if selected_session_id:
                classes = classes.filter(session_id=selected_session_id)
            self.fields['school_class'].queryset = classes.order_by('display_order', 'name')

            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('name')

    class Meta:
        model = TeacherSubjectAssignment
        fields = ['session', 'teacher', 'school_class', 'subject', 'is_active']


class ClassTeacherForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        selected_session_id = None
        selected_class_id = None

        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
            selected_class_id = self.instance.school_class_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['teacher'].queryset = Staff.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
            self.fields['teacher'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
                user__role='teacher',
            ).order_by('employee_id')

            classes = SchoolClass.objects.filter(school=self.school, is_active=True)
            if selected_session_id:
                classes = classes.filter(session_id=selected_session_id)
            self.fields['school_class'].queryset = classes.order_by('display_order', 'name')

            sections = Section.objects.filter(school_class__school=self.school, is_active=True)
            if selected_class_id:
                sections = sections.filter(school_class_id=selected_class_id)
            else:
                sections = sections.none()
            self.fields['section'].queryset = sections.order_by('name')

    class Meta:
        model = ClassTeacher
        fields = ['session', 'school_class', 'section', 'teacher', 'is_active']


class StaffAttendanceForm(forms.ModelForm):
    class Meta:
        model = StaffAttendance
        fields = ['staff', 'date', 'check_in_time', 'check_out_time', 'status']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'check_in_time': forms.TimeInput(attrs={'type': 'time'}),
            'check_out_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.actor_staff = kwargs.pop('actor_staff', None)
        self.lock_staff = kwargs.pop('lock_staff', False)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        if self.school:
            self.fields['staff'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('employee_id')

        if self.actor_staff and self.lock_staff:
            self.fields['staff'].queryset = Staff.objects.filter(id=self.actor_staff.id)
            self.fields['staff'].initial = self.actor_staff
            self.fields['staff'].widget = forms.HiddenInput()

    def clean_staff(self):
        staff = self.cleaned_data.get('staff')
        if self.school and staff and staff.school_id != self.school.id:
            raise ValidationError('Selected staff does not belong to your school.')
        if self.actor_staff and self.lock_staff and staff and staff.id != self.actor_staff.id:
            raise ValidationError('You can mark attendance only for yourself.')
        return staff


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['staff', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.actor_staff = kwargs.pop('actor_staff', None)
        self.lock_staff = kwargs.pop('lock_staff', False)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        if self.school:
            self.fields['staff'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('employee_id')

        if self.actor_staff and self.lock_staff:
            self.fields['staff'].queryset = Staff.objects.filter(id=self.actor_staff.id)
            self.fields['staff'].initial = self.actor_staff
            self.fields['staff'].widget = forms.HiddenInput()

    def clean_staff(self):
        staff = self.cleaned_data.get('staff')
        if self.school and staff and staff.school_id != self.school.id:
            raise ValidationError('Selected staff does not belong to your school.')
        if self.actor_staff and self.lock_staff and staff and staff.id != self.actor_staff.id:
            raise ValidationError('You can create leave request only for yourself.')
        return staff


class LeaveReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=(
            (LeaveRequest.STATUS_APPROVED, 'Approve'),
            (LeaveRequest.STATUS_REJECTED, 'Reject'),
        )
    )


class SubstitutionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        selected_session_id = None
        selected_class_id = None

        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
            selected_class_id = self.instance.school_class_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['period'].queryset = Period.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()
        self.fields['subject'].queryset = Subject.objects.none()
        self.fields['original_teacher'].queryset = Staff.objects.none()
        self.fields['substitute_teacher'].queryset = Staff.objects.none()

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

            periods = Period.objects.filter(school=self.school, is_active=True)
            classes = SchoolClass.objects.filter(school=self.school, is_active=True)
            if selected_session_id:
                periods = periods.filter(session_id=selected_session_id)
                classes = classes.filter(session_id=selected_session_id)

            self.fields['period'].queryset = periods.order_by('period_number')
            self.fields['school_class'].queryset = classes.order_by('display_order', 'name')

            sections = Section.objects.filter(school_class__school=self.school, is_active=True)
            if selected_class_id:
                sections = sections.filter(school_class_id=selected_class_id)
            else:
                sections = sections.none()
            self.fields['section'].queryset = sections.order_by('name')

            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('name')

            teachers = Staff.objects.filter(
                school=self.school,
                is_active=True,
                user__role='teacher',
            ).order_by('employee_id')
            self.fields['original_teacher'].queryset = teachers
            self.fields['substitute_teacher'].queryset = teachers

    class Meta:
        model = Substitution
        fields = [
            'session',
            'date',
            'period',
            'school_class',
            'section',
            'subject',
            'original_teacher',
            'substitute_teacher',
            'is_active',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }


class SalaryStructureForm(forms.Form):
    staff = forms.ModelChoiceField(queryset=Staff.objects.none())
    basic_salary = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    allowances = forms.JSONField(required=False)
    deductions = forms.JSONField(required=False)
    effective_from = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    reason = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['staff'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('employee_id')

    def clean_allowances(self):
        allowances = self.cleaned_data.get('allowances')
        if allowances in [None, '']:
            return {}
        if not isinstance(allowances, dict):
            raise ValidationError('Allowances must be a JSON object.')
        return allowances

    def clean_deductions(self):
        deductions = self.cleaned_data.get('deductions')
        if deductions in [None, '']:
            return {}
        if not isinstance(deductions, dict):
            raise ValidationError('Deductions must be a JSON object.')
        return deductions
