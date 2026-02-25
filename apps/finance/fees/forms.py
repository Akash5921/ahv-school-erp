from django import forms

from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass

from .models import FeeInstallment, FeeStructure, StudentFee


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = ['academic_session', 'school_class', 'name', 'amount']


class FeeInstallmentForm(forms.ModelForm):
    class Meta:
        model = FeeInstallment
        fields = ['title', 'due_date', 'amount']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class StudentFeeForm(forms.ModelForm):
    class Meta:
        model = StudentFee
        fields = ['student', 'fee_structure', 'total_amount', 'concession_amount', 'concession_note']


class FeeCollectionForm(forms.Form):
    student_fee = forms.ModelChoiceField(queryset=StudentFee.objects.none())
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))


def bind_school_fee_structure_form(form, school):
    form.fields['academic_session'].queryset = AcademicSession.objects.filter(
        school=school
    ).order_by('-start_date')
    form.fields['school_class'].queryset = SchoolClass.objects.filter(
        school=school
    ).order_by('order', 'name')


def bind_school_student_fee_form(form, school):
    form.fields['student'].queryset = Student.objects.filter(
        school=school
    ).order_by('first_name', 'last_name')
    form.fields['fee_structure'].queryset = FeeStructure.objects.filter(
        school=school
    ).select_related('school_class', 'academic_session').order_by(
        '-academic_session__start_date', 'school_class__order', 'name'
    )


def bind_school_fee_collection_form(form, school):
    form.fields['student_fee'].queryset = StudentFee.objects.filter(
        student__school=school
    ).select_related(
        'student',
        'fee_structure',
        'fee_structure__academic_session',
        'fee_structure__school_class',
    ).order_by(
        'student__first_name',
        'student__last_name',
        '-fee_structure__academic_session__start_date',
    )
