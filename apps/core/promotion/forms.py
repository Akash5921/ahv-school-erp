from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession


def _school_sessions(school):
    if not school:
        return AcademicSession.objects.none()
    return AcademicSession.objects.filter(school=school).order_by('-start_date', '-id')


class SessionInitializationForm(forms.Form):
    source_session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=False)
    name = forms.CharField(max_length=20)
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    copy_academic_structure = forms.BooleanField(required=False, initial=True)
    copy_fee_structure = forms.BooleanField(required=False)
    make_current = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        self.fields['source_session'].queryset = _school_sessions(self.school)
        if self.school and getattr(self.school, 'current_session_id', None) and not self.is_bound:
            current_session = self.fields['source_session'].queryset.filter(
                id=self.school.current_session_id
            ).first()
            if current_session:
                self.initial.setdefault('source_session', current_session)

    def clean_source_session(self):
        session = self.cleaned_data.get('source_session')
        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Selected source session does not belong to your school.')
        return session

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        source_session = cleaned_data.get('source_session')
        copy_academic_structure = cleaned_data.get('copy_academic_structure')
        copy_fee_structure = cleaned_data.get('copy_fee_structure')

        if start_date and end_date and start_date >= end_date:
            self.add_error('end_date', 'End date must be after start date.')

        if copy_fee_structure and not source_session:
            self.add_error('source_session', 'Choose a source session before copying fee structure.')

        if copy_academic_structure and not source_session:
            self.add_error('source_session', 'Choose a source session before copying setup.')

        return cleaned_data


class SessionCloseForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    next_session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        sessions = _school_sessions(self.school)
        self.fields['session'].queryset = sessions
        self.fields['next_session'].queryset = sessions
        if self.school and getattr(self.school, 'current_session_id', None) and not self.is_bound:
            current_session = sessions.filter(id=self.school.current_session_id).first()
            if current_session:
                self.initial.setdefault('session', current_session)

    def clean(self):
        cleaned_data = super().clean()
        session = cleaned_data.get('session')
        next_session = cleaned_data.get('next_session')
        if session and self.school and session.school_id != self.school.id:
            raise ValidationError('Selected session does not belong to your school.')
        if next_session and self.school and next_session.school_id != self.school.id:
            raise ValidationError('Selected next session does not belong to your school.')
        if session and next_session and session.id == next_session.id:
            raise ValidationError('Next session must be different from closing session.')
        return cleaned_data
