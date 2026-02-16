from django import forms
from .models import SchoolClass, Section, Subject


class SchoolClassForm(forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ['name']


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ['name', 'school_class']


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'school_class']
