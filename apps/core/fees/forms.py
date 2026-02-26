from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass
from apps.core.students.models import Student

from .models import (
    ClassFeeStructure,
    FeePayment,
    FeeType,
    Installment,
    StudentConcession,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class FeeTypeForm(forms.ModelForm):
    class Meta:
        model = FeeType
        fields = ['name', 'category', 'is_active']


class ClassFeeStructureForm(forms.ModelForm):
    class Meta:
        model = ClassFeeStructure
        fields = ['session', 'school_class', 'fee_type', 'amount', 'is_active']

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['fee_type'].queryset = FeeType.objects.none()

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        class_qs = SchoolClass.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('display_order', 'name')
        if selected_session_id:
            class_qs = class_qs.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = class_qs

        self.fields['fee_type'].queryset = FeeType.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('name')

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get('session')
        school_class = cleaned.get('school_class')
        fee_type = cleaned.get('fee_type')

        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Session does not belong to selected school.')
        if school_class and session and school_class.session_id != session.id:
            raise ValidationError('Class does not belong to selected session.')
        if self.school and fee_type and fee_type.school_id != self.school.id:
            raise ValidationError('Fee type does not belong to selected school.')
        return cleaned


class InstallmentForm(forms.ModelForm):
    class Meta:
        model = Installment
        fields = [
            'session',
            'name',
            'due_date',
            'fine_per_day',
            'split_percentage',
            'fixed_amount',
            'is_active',
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

        if self.default_session and not self.instance.pk and not self.is_bound:
            self.initial.setdefault('session', self.default_session.id)

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Session does not belong to selected school.')
        return session


class StudentConcessionForm(forms.ModelForm):
    class Meta:
        model = StudentConcession
        fields = [
            'session',
            'student',
            'fee_type',
            'percentage',
            'fixed_amount',
            'reason',
            'is_active',
        ]

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['student'].queryset = Student.objects.none()
        self.fields['fee_type'].queryset = FeeType.objects.none()

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        students_qs = Student.objects.filter(
            school=self.school,
            is_archived=False,
        ).order_by('admission_number')
        fee_types_qs = FeeType.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('name')

        if selected_session_id:
            students_qs = students_qs.filter(session_id=selected_session_id)

        self.fields['student'].queryset = students_qs
        self.fields['fee_type'].queryset = fee_types_qs

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get('session')
        student = cleaned.get('student')
        fee_type = cleaned.get('fee_type')

        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Session does not belong to selected school.')
        if student and session and student.session_id != session.id:
            raise ValidationError('Student does not belong to selected session.')
        if self.school and fee_type and fee_type.school_id != self.school.id:
            raise ValidationError('Fee type does not belong to selected school.')

        percentage = cleaned.get('percentage')
        fixed_amount = cleaned.get('fixed_amount')
        if bool(percentage) == bool(fixed_amount):
            raise ValidationError('Provide either percentage or fixed amount.')
        return cleaned


class FeePaymentCollectionForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    student = forms.ModelChoiceField(queryset=Student.objects.none())
    installment = forms.ModelChoiceField(queryset=Installment.objects.none())
    amount_paid = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    payment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    payment_mode = forms.ChoiceField(choices=FeePayment.PAYMENT_MODE_CHOICES)
    reference_number = forms.CharField(max_length=120, required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['student'].queryset = Student.objects.none()
        self.fields['installment'].queryset = Installment.objects.none()

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        students = Student.objects.filter(
            school=self.school,
            is_archived=False,
        ).order_by('admission_number')
        installments = Installment.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('due_date', 'id')

        if selected_session_id:
            students = students.filter(session_id=selected_session_id)
            installments = installments.filter(session_id=selected_session_id)

        self.fields['student'].queryset = students
        self.fields['installment'].queryset = installments


class FeePaymentReverseForm(forms.Form):
    reason = forms.CharField(max_length=255)


class FeeRefundForm(forms.Form):
    payment = forms.ModelChoiceField(queryset=FeePayment.objects.none())
    refund_amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    reason = forms.CharField(max_length=255)
    refund_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        payments = FeePayment.objects.none()
        if self.school:
            payments = FeePayment.objects.filter(
                school=self.school,
                is_reversed=False,
            ).select_related('student', 'session').order_by('-payment_date', '-id')
            if self.default_session:
                payments = payments.filter(session=self.default_session)
        self.fields['payment'].queryset = payments


class FeeRefundReverseForm(forms.Form):
    reason = forms.CharField(max_length=255)


class CarryForwardForm(forms.Form):
    student = forms.ModelChoiceField(queryset=Student.objects.none())
    from_session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    to_session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['student'].queryset = Student.objects.none()
        self.fields['from_session'].queryset = AcademicSession.objects.none()
        self.fields['to_session'].queryset = AcademicSession.objects.none()

        if not self.school:
            return

        sessions = _school_sessions(self.school)
        students = Student.objects.filter(
            school=self.school,
            is_archived=False,
        ).order_by('admission_number')

        self.fields['student'].queryset = students
        self.fields['from_session'].queryset = sessions
        self.fields['to_session'].queryset = sessions

        if self.default_session and not self.is_bound:
            self.initial.setdefault('to_session', self.default_session.id)


class StudentFeeSyncForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        classes = SchoolClass.objects.filter(school=self.school, is_active=True).order_by('display_order', 'name')
        if selected_session_id:
            classes = classes.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = classes
