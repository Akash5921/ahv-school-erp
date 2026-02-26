from django import forms

from .models import GradeScale, Student


class StudentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

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

    def clean(self):
        cleaned_data = super().clean()
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        academic_session = cleaned_data.get('academic_session')
        parent_user = cleaned_data.get('parent_user')

        if school_class and section and section.school_class_id != school_class.id:
            self.add_error('section', 'Selected section does not belong to the selected class.')

        if parent_user and parent_user.role != 'parent':
            self.add_error('parent_user', 'Selected user must have parent role.')

        if self.school:
            if school_class and school_class.school_id != self.school.id:
                self.add_error('school_class', 'Selected class does not belong to your school.')
            if section and section.school_class.school_id != self.school.id:
                self.add_error('section', 'Selected section does not belong to your school.')
            if academic_session and academic_session.school_id != self.school.id:
                self.add_error('academic_session', 'Selected session does not belong to your school.')
            if parent_user and parent_user.school_id != self.school.id:
                self.add_error('parent_user', 'Selected parent does not belong to your school.')

        return cleaned_data


class GradeScaleForm(forms.ModelForm):
    class Meta:
        model = GradeScale
        fields = [
            'grade_name',
            'min_percentage',
            'max_percentage',
            'remarks',
        ]
