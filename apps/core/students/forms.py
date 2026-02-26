from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section

from .models import DocumentType, Parent, Student, StudentDocument


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class StudentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('session', None)
        super().__init__(*args, **kwargs)

        # Model-level validation checks class/section against school.
        # Set it early so form validation can run before view assigns school on save.
        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['current_class'].queryset = SchoolClass.objects.none()
        self.fields['current_section'].queryset = Section.objects.none()

        selected_session_id = None
        selected_class_id = None

        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('current_class')
        else:
            if self.instance and self.instance.pk:
                selected_session_id = self.instance.session_id
                selected_class_id = self.instance.current_class_id
            elif self.default_session:
                selected_session_id = self.default_session.id
                self.initial.setdefault('session', self.default_session)

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

            classes = SchoolClass.objects.filter(school=self.school).order_by(
                'display_order', 'name'
            )
            if selected_session_id:
                classes = classes.filter(session_id=selected_session_id)
            self.fields['current_class'].queryset = classes

            sections = Section.objects.filter(school_class__school=self.school).select_related(
                'school_class'
            )
            if selected_class_id:
                sections = sections.filter(school_class_id=selected_class_id)
            else:
                sections = sections.none()
            self.fields['current_section'].queryset = sections.order_by('school_class__name', 'name')

    class Meta:
        model = Student
        fields = [
            'session',
            'admission_number',
            'first_name',
            'last_name',
            'gender',
            'date_of_birth',
            'blood_group',
            'admission_date',
            'admission_type',
            'previous_school_name',
            'current_class',
            'current_section',
            'roll_number',
            'photo',
            'allergies',
            'medical_conditions',
            'emergency_contact_name',
            'emergency_contact_phone',
            'doctor_name',
            'transport_assigned',
            'hostel_assigned',
            'house',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'admission_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session

    def clean_current_class(self):
        school_class = self.cleaned_data.get('current_class')
        if not school_class:
            return school_class

        session = self.cleaned_data.get('session')
        if session and school_class.session_id != session.id:
            raise ValidationError('Selected class does not belong to selected session.')

        return school_class

    def clean_current_section(self):
        section = self.cleaned_data.get('current_section')
        school_class = self.cleaned_data.get('current_class')

        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')

        return section

    def clean_roll_number(self):
        roll_number = (self.cleaned_data.get('roll_number') or '').strip()
        return roll_number or None


class ParentForm(forms.ModelForm):
    phone = forms.CharField(required=False)

    class Meta:
        model = Parent
        fields = [
            'father_name',
            'mother_name',
            'guardian_name',
            'phone',
            'email',
            'occupation',
            'address',
        ]

    def has_data(self):
        if not hasattr(self, 'cleaned_data'):
            return False
        return any(
            self.cleaned_data.get(field)
            for field in ['father_name', 'mother_name', 'guardian_name', 'phone', 'email', 'occupation', 'address']
        )

    def clean(self):
        cleaned_data = super().clean()
        phone = (cleaned_data.get('phone') or '').strip()

        fields_except_phone = [
            'father_name',
            'mother_name',
            'guardian_name',
            'email',
            'occupation',
            'address',
        ]
        has_other_data = any(cleaned_data.get(field) for field in fields_except_phone)

        if has_other_data and not phone:
            raise ValidationError('Parent phone is required when parent details are provided.')

        cleaned_data['phone'] = phone
        return cleaned_data


class DocumentTypeForm(forms.ModelForm):
    class Meta:
        model = DocumentType
        fields = ['name', 'required_for', 'is_mandatory', 'is_active']


class StudentDocumentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        if self.student:
            self.fields['document_type'].queryset = DocumentType.objects.filter(
                school=self.student.school,
                is_active=True,
            ).order_by('name')

    class Meta:
        model = StudentDocument
        fields = ['document_type', 'file', 'remarks']

    def clean_document_type(self):
        document_type = self.cleaned_data.get('document_type')
        if self.student and document_type and document_type.school_id != self.student.school_id:
            raise ValidationError('Selected document type does not belong to student school.')
        return document_type


class StudentStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Student.STATUS_CHOICES)
    reason = forms.CharField(max_length=255, required=False)
