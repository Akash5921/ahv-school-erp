from django import forms
from .models import Student

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'first_name',
            'last_name',
            'academic_session',
            'school_class',
            'section'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'school_class': forms.Select(attrs={'class': 'form-control'}),
            'section': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'academic_session': 'Academic Session',
            'school_class': 'Class',
            'section': 'Section',
        }