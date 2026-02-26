from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject

from .models import Exam, ExamSubject, ExamType, GradeScale


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _extract_id(value):
    if value is None:
        return None
    return str(getattr(value, 'id', value))


class ExamTypeForm(forms.ModelForm):
    class Meta:
        model = ExamType
        fields = ['session', 'name', 'weightage', 'is_active']

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
        if self.default_session and not self.is_bound and not self.instance.pk:
            self.initial.setdefault('session', self.default_session.id)

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = [
            'session',
            'exam_type',
            'school_class',
            'section',
            'start_date',
            'end_date',
            'total_marks',
            'is_active',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['exam_type'].queryset = ExamType.objects.none()
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
            if self.instance and self.instance.pk:
                selected_session_id = str(self.instance.session_id)
                selected_class_id = str(self.instance.school_class_id)
            elif self.default_session:
                selected_session_id = str(self.default_session.id)
                self.initial.setdefault('session', self.default_session.id)

        exam_types = ExamType.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('name')
        classes = SchoolClass.objects.filter(
            school=self.school,
            is_active=True,
        ).order_by('display_order', 'name')

        if selected_session_id:
            exam_types = exam_types.filter(session_id=selected_session_id)
            classes = classes.filter(session_id=selected_session_id)

        self.fields['exam_type'].queryset = exam_types
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
        cleaned = super().clean()
        session = cleaned.get('session')
        exam_type = cleaned.get('exam_type')
        school_class = cleaned.get('school_class')
        section = cleaned.get('section')

        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        if exam_type and session and exam_type.session_id != session.id:
            raise ValidationError('Selected exam type does not belong to selected session.')
        if school_class and session and school_class.session_id != session.id:
            raise ValidationError('Selected class does not belong to selected session.')
        if section and school_class and section.school_class_id != school_class.id:
            raise ValidationError('Selected section does not belong to selected class.')
        return cleaned


class ExamSubjectForm(forms.ModelForm):
    class Meta:
        model = ExamSubject
        fields = ['subject', 'max_marks', 'pass_marks', 'is_active']

    def __init__(self, *args, **kwargs):
        self.exam = kwargs.pop('exam', None)
        super().__init__(*args, **kwargs)

        self.fields['subject'].queryset = Subject.objects.none()
        if not self.exam:
            return

        subject_ids = self.exam.school_class.class_subjects.values_list('subject_id', flat=True)
        queryset = Subject.objects.filter(
            id__in=subject_ids,
            school=self.exam.school,
            is_active=True,
        ).order_by('name')

        if self.instance and self.instance.pk:
            queryset = queryset | Subject.objects.filter(id=self.instance.subject_id)
            queryset = queryset.order_by('name')

        self.fields['subject'].queryset = queryset


class GradeScaleForm(forms.ModelForm):
    class Meta:
        model = GradeScale
        fields = [
            'session',
            'grade_name',
            'min_percentage',
            'max_percentage',
            'description',
            'display_order',
            'is_active',
        ]

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        if self.school and not self.instance.school_id:
            self.instance.school = self.school

        self.fields['session'].queryset = AcademicSession.objects.none()
        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)

        if self.default_session and not self.is_bound and not self.instance.pk:
            self.initial.setdefault('session', self.default_session.id)

    def clean_session(self):
        session = self.cleaned_data.get('session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        return session


class MarkEntrySelectionForm(forms.Form):
    exam = forms.ModelChoiceField(queryset=Exam.objects.none())
    subject = forms.ModelChoiceField(queryset=Subject.objects.none())

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['exam'].queryset = Exam.objects.none()
        self.fields['subject'].queryset = Subject.objects.none()

        if not self.school:
            return

        exams = Exam.objects.filter(
            school=self.school,
            is_active=True,
        ).select_related('exam_type', 'school_class', 'section').order_by('-start_date')
        if self.default_session:
            exams = exams.filter(session=self.default_session)
        self.fields['exam'].queryset = exams

        selected_exam_id = None
        if self.is_bound:
            selected_exam_id = self.data.get('exam')
        else:
            selected_exam_id = _extract_id(self.initial.get('exam'))

        if selected_exam_id and str(selected_exam_id).isdigit():
            exam_subjects = ExamSubject.objects.filter(
                exam_id=int(selected_exam_id),
                is_active=True,
            ).select_related('subject')
            self.fields['subject'].queryset = Subject.objects.filter(
                id__in=exam_subjects.values_list('subject_id', flat=True)
            ).order_by('name')

    def clean(self):
        cleaned = super().clean()
        exam = cleaned.get('exam')
        subject = cleaned.get('subject')
        if exam and exam.school_id != self.school.id:
            raise ValidationError('Selected exam does not belong to your school.')
        if exam and subject and not ExamSubject.objects.filter(
            exam=exam,
            subject=subject,
            is_active=True,
        ).exists():
            raise ValidationError('Selected subject is not configured for selected exam.')
        return cleaned
