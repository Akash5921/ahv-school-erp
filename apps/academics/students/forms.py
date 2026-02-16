from django import forms
from .models import GradeScale, Student

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'admission_number',
            'first_name',
            'last_name',
            'date_of_birth',
            'gender',
            'academic_session',
            'school_class',
            'section',
            'parent_user',
        ]
        widgets = {
            'admission_number': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.TextInput(attrs={'class': 'form-control'}),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'school_class': forms.Select(attrs={'class': 'form-control'}),
            'section': forms.Select(attrs={'class': 'form-control'}),
            'parent_user': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'admission_number': 'Admission Number',
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'date_of_birth': 'Date of Birth',
            'gender': 'Gender',
            'academic_session': 'Academic Session',
            'school_class': 'Class',
            'section': 'Section',
            'parent_user': 'Parent Login',
        }


class GradeScaleForm(forms.ModelForm):
    class Meta:
        model = GradeScale
        fields = [
            'grade_name',
            'min_percentage',
            'max_percentage',
            'remarks',
        ]
