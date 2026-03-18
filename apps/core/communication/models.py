from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.schools.models import School
from apps.core.students.models import Parent, Student
from apps.core.utils.managers import SchoolManager


class GlobalSettings(models.Model):
    school = models.OneToOneField(
        School,
        on_delete=models.CASCADE,
        related_name='communication_settings',
    )

    email_enabled = models.BooleanField(default=False)
    smtp_host = models.CharField(max_length=150, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=150, blank=True)
    smtp_password = models.CharField(max_length=255, blank=True)
    smtp_use_tls = models.BooleanField(default=True)
    smtp_from_email = models.EmailField(blank=True)

    sms_enabled = models.BooleanField(default=False)
    sms_api_url = models.URLField(blank=True)
    sms_api_key = models.CharField(max_length=255, blank=True)
    sms_sender_id = models.CharField(max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Global Communication Settings'
        verbose_name_plural = 'Global Communication Settings'

    def clean(self):
        super().clean()

        if self.email_enabled:
            missing = []
            if not self.smtp_host.strip():
                missing.append('SMTP host')
            if not self.smtp_from_email.strip():
                missing.append('SMTP from email')
            if missing:
                raise ValidationError(f"Email is enabled but missing configuration: {', '.join(missing)}.")

        if self.sms_enabled:
            missing = []
            if not self.sms_api_url.strip():
                missing.append('SMS API URL')
            if not self.sms_api_key.strip():
                missing.append('SMS API key')
            if missing:
                raise ValidationError(f"SMS is enabled but missing configuration: {', '.join(missing)}.")

    def __str__(self):
        return f"Communication Settings - {self.school.name}"


class ParentUser(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='parent_users',
    )
    objects = SchoolManager()

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='parent_profile',
    )
    parent_info = models.ForeignKey(
        Parent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_users',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]

    def clean(self):
        super().clean()
        if self.user_id:
            if self.user.school_id != self.school_id:
                raise ValidationError({'user': 'Parent user must belong to selected school.'})
            if self.user.role != 'parent':
                raise ValidationError({'user': 'User role must be parent.'})
        if self.parent_info_id and self.parent_info.student.school_id != self.school_id:
            raise ValidationError({'parent_info': 'Parent info must belong to selected school.'})

    def __str__(self):
        return self.user.username


class ParentStudentLink(models.Model):
    parent_user = models.ForeignKey(
        ParentUser,
        on_delete=models.CASCADE,
        related_name='student_links',
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='parent_links',
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'student__admission_number']
        constraints = [
            models.UniqueConstraint(
                fields=['parent_user', 'student'],
                name='unique_parent_student_link',
            ),
            models.UniqueConstraint(
                fields=['parent_user'],
                condition=Q(is_primary=True),
                name='unique_primary_student_per_parent_user',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'is_primary']),
        ]

    def clean(self):
        super().clean()
        if self.student_id and self.parent_user_id:
            if self.student.school_id != self.parent_user.school_id:
                raise ValidationError({'student': 'Student must belong to same school as parent user.'})

    def __str__(self):
        return f"{self.parent_user.user.username} -> {self.student.admission_number}"


class Announcement(models.Model):
    ROLE_ALL = 'all'
    ROLE_STUDENT = 'student'
    ROLE_PARENT = 'parent'
    ROLE_TEACHER = 'teacher'
    ROLE_STAFF = 'staff'
    ROLE_ACCOUNTANT = 'accountant'
    ROLE_SCHOOLADMIN = 'schooladmin'
    TARGET_ROLE_CHOICES = (
        (ROLE_ALL, 'All'),
        (ROLE_STUDENT, 'Student'),
        (ROLE_PARENT, 'Parent'),
        (ROLE_TEACHER, 'Teacher'),
        (ROLE_STAFF, 'Staff'),
        (ROLE_ACCOUNTANT, 'Accountant'),
        (ROLE_SCHOOLADMIN, 'School Admin'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='announcements',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='announcements',
    )
    objects = SchoolManager()

    title = models.CharField(max_length=150)
    message = models.TextField()
    target_role = models.CharField(max_length=20, choices=TARGET_ROLE_CHOICES, default=ROLE_ALL)
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='announcements',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='announcements',
    )
    attachment = models.FileField(upload_to='communication/announcements/', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_announcements',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
            models.Index(fields=['school', 'target_role']),
            models.Index(fields=['school', 'expires_at']),
        ]

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def clean(self):
        super().clean()
        self.title = (self.title or '').strip()
        if not self.title:
            raise ValidationError({'title': 'Title is required.'})

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.section_id:
            if not self.school_class_id:
                raise ValidationError({'section': 'Select class before section.'})
            if self.section.school_class_id != self.school_class_id:
                raise ValidationError({'section': 'Section must belong to selected class.'})

        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError({'expires_at': 'Expiry must be in the future.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return self.title


class MessageThread(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='message_threads',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='message_threads',
    )
    objects = SchoolManager()

    subject = models.CharField(max_length=150)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_threads_created',
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='MessageThreadParticipant',
        related_name='message_threads',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [
            models.Index(fields=['school', 'session']),
        ]

    def clean(self):
        super().clean()
        self.subject = (self.subject or '').strip()
        if not self.subject:
            raise ValidationError({'subject': 'Thread subject is required.'})
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.created_by_id and self.created_by.school_id != self.school_id:
            raise ValidationError({'created_by': 'Creator must belong to selected school.'})

    def __str__(self):
        return self.subject


class MessageThreadParticipant(models.Model):
    thread = models.ForeignKey(
        MessageThread,
        on_delete=models.CASCADE,
        related_name='thread_participants',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='thread_participation',
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['thread_id', 'user_id']
        constraints = [
            models.UniqueConstraint(
                fields=['thread', 'user'],
                name='unique_thread_participant',
            ),
        ]

    def clean(self):
        super().clean()
        if self.thread_id and self.user_id and self.user.school_id != self.thread.school_id:
            raise ValidationError({'user': 'Participant must belong to thread school.'})

    def __str__(self):
        return f"{self.thread_id}:{self.user_id}"


class Message(models.Model):
    thread = models.ForeignKey(
        MessageThread,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages_sent',
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages_received',
    )
    message_text = models.TextField()
    attachment = models.FileField(upload_to='communication/messages/', null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages_edited',
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['sent_at', 'id']
        indexes = [
            models.Index(fields=['thread', 'sent_at']),
            models.Index(fields=['receiver', 'is_read']),
            models.Index(fields=['sender', 'sent_at']),
        ]

    def clean(self):
        super().clean()
        self.message_text = (self.message_text or '').strip()
        if not self.message_text and not self.attachment:
            raise ValidationError('Message text or attachment is required.')
        if self.sender_id == self.receiver_id:
            raise ValidationError({'receiver': 'Receiver must be different from sender.'})
        if self.sender_id and self.sender.school_id != self.thread.school_id:
            raise ValidationError({'sender': 'Sender must belong to thread school.'})
        if self.receiver_id and self.receiver.school_id != self.thread.school_id:
            raise ValidationError({'receiver': 'Receiver must belong to thread school.'})

        participant_user_ids = set(
            self.thread.thread_participants.values_list('user_id', flat=True)
        )
        if self.sender_id not in participant_user_ids or self.receiver_id not in participant_user_ids:
            raise ValidationError('Sender and receiver must be participants in this thread.')

    def delete(self, *args, **kwargs):
        raise ValidationError('Messages cannot be deleted.')

    def __str__(self):
        return f"{self.sender_id}->{self.receiver_id} ({self.sent_at})"


class Notification(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    objects = SchoolManager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=150)
    message = models.TextField()
    related_model = models.CharField(max_length=120, blank=True)
    related_id = models.CharField(max_length=64, blank=True)
    event_key = models.CharField(max_length=150, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event_key'],
                condition=~Q(event_key=''),
                name='unique_notification_event_key_per_user',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'created_at']),
            models.Index(fields=['user', 'is_read']),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.user.school_id != self.school_id:
            raise ValidationError({'user': 'Notification user must belong to selected school.'})
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        self.title = (self.title or '').strip()
        if not self.title:
            raise ValidationError({'title': 'Notification title is required.'})

    def __str__(self):
        return f"{self.user.username}: {self.title}"

    def delete(self, *args, **kwargs):
        raise ValidationError('Notification history cannot be deleted.')


class EmailLog(models.Model):
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='email_logs',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
    )
    objects = SchoolManager()

    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.CharField(max_length=255, blank=True)
    related_model = models.CharField(max_length=120, blank=True)
    related_id = models.CharField(max_length=64, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs_triggered',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['school', 'session', 'timestamp']),
            models.Index(fields=['school', 'status']),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

    def __str__(self):
        return f"{self.recipient} ({self.status})"

    def delete(self, *args, **kwargs):
        raise ValidationError('Email history cannot be deleted.')


class SMSLog(models.Model):
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='sms_logs',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_logs',
    )
    objects = SchoolManager()

    recipient_number = models.CharField(max_length=20)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.CharField(max_length=255, blank=True)
    related_model = models.CharField(max_length=120, blank=True)
    related_id = models.CharField(max_length=64, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_logs_triggered',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['school', 'session', 'timestamp']),
            models.Index(fields=['school', 'status']),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

    def __str__(self):
        return f"{self.recipient_number} ({self.status})"

    def delete(self, *args, **kwargs):
        raise ValidationError('SMS history cannot be deleted.')
