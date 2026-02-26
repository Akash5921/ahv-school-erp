from django import forms

from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass

from .models import FeeInstallment, FeeStructure, StudentFee


class FeeStructureForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = FeeStructure
        fields = ['academic_session', 'school_class', 'name', 'amount']

    def clean(self):
        cleaned_data = super().clean()
        academic_session = cleaned_data.get('academic_session')
        school_class = cleaned_data.get('school_class')

        if academic_session and school_class and academic_session.school_id != school_class.school_id:
            self.add_error('school_class', 'Selected class does not belong to the selected session school.')

        if self.school:
            if academic_session and academic_session.school_id != self.school.id:
                self.add_error('academic_session', 'Selected session does not belong to your school.')
            if school_class and school_class.school_id != self.school.id:
                self.add_error('school_class', 'Selected class does not belong to your school.')

        return cleaned_data


class FeeInstallmentForm(forms.ModelForm):
    class Meta:
        model = FeeInstallment
        fields = ['title', 'due_date', 'amount']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class StudentFeeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = StudentFee
        fields = ['student', 'fee_structure', 'total_amount', 'concession_amount', 'concession_note']

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        fee_structure = cleaned_data.get('fee_structure')

        if student and fee_structure and student.school_id != fee_structure.school_id:
            self.add_error('fee_structure', 'Selected fee structure does not belong to the student school.')

        if self.school:
            if student and student.school_id != self.school.id:
                self.add_error('student', 'Selected student does not belong to your school.')
            if fee_structure and fee_structure.school_id != self.school.id:
                self.add_error('fee_structure', 'Selected fee structure does not belong to your school.')

        return cleaned_data


class FeeCollectionForm(forms.Form):
    student_fee = forms.ModelChoiceField(queryset=StudentFee.objects.none())
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    def clean_student_fee(self):
        student_fee = self.cleaned_data.get('student_fee')
        if self.school and student_fee and student_fee.student.school_id != self.school.id:
            raise forms.ValidationError('Selected fee record does not belong to your school.')
        return student_fee


def bind_school_fee_structure_form(form, school):
    form.school = school
    form.fields['academic_session'].queryset = AcademicSession.objects.filter(
        school=school
    ).order_by('-start_date')
    form.fields['school_class'].queryset = SchoolClass.objects.filter(
        school=school
    ).order_by('order', 'name')


def bind_school_student_fee_form(form, school):
    form.school = school
    form.fields['student'].queryset = Student.objects.filter(
        school=school
    ).order_by('first_name', 'last_name')
    form.fields['fee_structure'].queryset = FeeStructure.objects.filter(
        school=school
    ).select_related('school_class', 'academic_session').order_by(
        '-academic_session__start_date', 'school_class__order', 'name'
    )


def bind_school_fee_collection_form(form, school):
    form.school = school
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
