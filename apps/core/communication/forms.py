from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.students.models import Parent, Student

from .models import (
    Announcement,
    GlobalSettings,
    ParentStudentLink,
    ParentUser,
)
from .services import can_user_message


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class GlobalSettingsForm(forms.ModelForm):
    class Meta:
        model = GlobalSettings
        fields = [
            'email_enabled',
            'smtp_host',
            'smtp_port',
            'smtp_username',
            'smtp_password',
            'smtp_use_tls',
            'smtp_from_email',
            'sms_enabled',
            'sms_api_url',
            'sms_api_key',
            'sms_sender_id',
        ]
        widgets = {
            'smtp_password': forms.PasswordInput(render_value=True),
            'sms_api_key': forms.PasswordInput(render_value=True),
        }


class ParentUserForm(forms.ModelForm):
    class Meta:
        model = ParentUser
        fields = ['user', 'parent_info', 'is_active']

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        self.fields['user'].queryset = get_user_model().objects.none()
        self.fields['parent_info'].queryset = Parent.objects.none()

        if not self.school:
            return

        users = get_user_model().objects.filter(
            school=self.school,
            role='parent',
        ).order_by('username')

        if self.instance and self.instance.pk:
            users = users.filter(Q(parent_profile__isnull=True) | Q(id=self.instance.user_id))
        else:
            users = users.filter(parent_profile__isnull=True)

        self.fields['user'].queryset = users
        self.fields['parent_info'].queryset = Parent.objects.filter(
            student__school=self.school,
            student__is_archived=False,
        ).select_related('student').order_by('student__admission_number')


class ParentStudentLinkForm(forms.ModelForm):
    class Meta:
        model = ParentStudentLink
        fields = ['parent_user', 'student', 'is_primary']

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        self.fields['parent_user'].queryset = ParentUser.objects.none()
        self.fields['student'].queryset = Student.objects.none()

        if not self.school:
            return

        self.fields['parent_user'].queryset = ParentUser.objects.filter(
            school=self.school,
            is_active=True,
        ).select_related('user').order_by('user__username')

        self.fields['student'].queryset = Student.objects.filter(
            school=self.school,
            is_active=True,
            is_archived=False,
        ).order_by('admission_number')


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            'session',
            'title',
            'message',
            'target_role',
            'school_class',
            'section',
            'attachment',
            'expires_at',
            'is_active',
        ]
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        selected_session_id = None
        selected_class_id = None

        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
            selected_class_id = self.instance.school_class_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        class_qs = SchoolClass.objects.filter(school=self.school, is_active=True).order_by('display_order', 'name')
        if selected_session_id:
            class_qs = class_qs.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = class_qs

        section_qs = Section.objects.filter(
            school_class__school=self.school,
            is_active=True,
        ).order_by('school_class__display_order', 'name')
        if selected_class_id:
            section_qs = section_qs.filter(school_class_id=selected_class_id)
        else:
            section_qs = section_qs.none()
        self.fields['section'].queryset = section_qs

    def clean(self):
        cleaned = super().clean()
        if self.instance and self.instance.pk and self.instance.is_expired:
            raise ValidationError('Expired announcements cannot be edited.')
        return cleaned


class MessageThreadCreateForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=True)
    subject = forms.CharField(max_length=150)
    receiver = forms.ModelChoiceField(queryset=get_user_model().objects.none())
    message_text = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    attachment = forms.FileField(required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.sender = kwargs.pop('sender', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['receiver'].queryset = get_user_model().objects.none()

        if not self.school or not self.sender:
            return

        self.fields['session'].queryset = _school_sessions(self.school)
        if self.default_session and not self.is_bound:
            self.initial.setdefault('session', self.default_session.id)

        candidates = get_user_model().objects.filter(
            school=self.school,
        ).exclude(id=self.sender.id).exclude(role='superadmin').order_by('username')

        allowed_ids = [user.id for user in candidates if can_user_message(sender=self.sender, receiver=user)]
        self.fields['receiver'].queryset = candidates.filter(id__in=allowed_ids)

    def clean(self):
        cleaned = super().clean()
        message_text = (cleaned.get('message_text') or '').strip()
        attachment = cleaned.get('attachment')
        if not message_text and not attachment:
            raise ValidationError('Message text or attachment is required.')
        cleaned['message_text'] = message_text
        return cleaned


class MessageReplyForm(forms.Form):
    receiver = forms.ModelChoiceField(queryset=get_user_model().objects.none(), required=False)
    message_text = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    attachment = forms.FileField(required=False)

    def __init__(self, *args, **kwargs):
        self.thread = kwargs.pop('thread', None)
        self.sender = kwargs.pop('sender', None)
        super().__init__(*args, **kwargs)

        self.fields['receiver'].queryset = get_user_model().objects.none()
        if not self.thread or not self.sender:
            return

        participants = self.thread.participants.exclude(id=self.sender.id).order_by('username')
        self.fields['receiver'].queryset = participants

        if participants.count() == 1:
            self.initial.setdefault('receiver', participants.first().id)
            self.fields['receiver'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        message_text = (cleaned.get('message_text') or '').strip()
        attachment = cleaned.get('attachment')
        receiver = cleaned.get('receiver')

        if not receiver:
            raise ValidationError('Receiver is required.')
        if not message_text and not attachment:
            raise ValidationError('Message text or attachment is required.')

        cleaned['message_text'] = message_text
        return cleaned


class MessageEditForm(forms.Form):
    message_text = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)

    def clean_message_text(self):
        return (self.cleaned_data.get('message_text') or '').strip()


class BulkEmailForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none())
    section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False)
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        selected_session_id = None
        selected_class_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        class_qs = SchoolClass.objects.filter(school=self.school, is_active=True)
        if selected_session_id:
            class_qs = class_qs.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = class_qs.order_by('display_order', 'name')

        section_qs = Section.objects.filter(school_class__school=self.school, is_active=True)
        if selected_class_id:
            section_qs = section_qs.filter(school_class_id=selected_class_id)
        else:
            section_qs = section_qs.none()
        self.fields['section'].queryset = section_qs.order_by('name')


class BulkSMSForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none())
    section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        selected_session_id = None
        selected_class_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
            selected_class_id = self.data.get('school_class')
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['school_class'].queryset = SchoolClass.objects.none()
        self.fields['section'].queryset = Section.objects.none()

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)

        class_qs = SchoolClass.objects.filter(school=self.school, is_active=True)
        if selected_session_id:
            class_qs = class_qs.filter(session_id=selected_session_id)
        self.fields['school_class'].queryset = class_qs.order_by('display_order', 'name')

        section_qs = Section.objects.filter(school_class__school=self.school, is_active=True)
        if selected_class_id:
            section_qs = section_qs.filter(school_class_id=selected_class_id)
        else:
            section_qs = section_qs.none()
        self.fields['section'].queryset = section_qs.order_by('name')


class SessionFilterForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)
        if self.default_session and not self.is_bound:
            self.initial.setdefault('session', self.default_session.id)


class NotificationFilterForm(forms.Form):
    unread_only = forms.BooleanField(required=False)


class MonthYearForm(forms.Form):
    month = forms.IntegerField(min_value=1, max_value=12)
    year = forms.IntegerField(min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        if not self.is_bound:
            self.initial.setdefault('month', today.month)
            self.initial.setdefault('year', today.year)
