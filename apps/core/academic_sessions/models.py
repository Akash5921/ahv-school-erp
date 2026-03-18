from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.utils.managers import SchoolManager


class AcademicSession(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='academic_sessions'
    )
    objects = SchoolManager()

    name = models.CharField(max_length=20)  # e.g. 2026-27
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    attendance_locked = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_academic_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name'], name='unique_session_name_per_school'),
            models.UniqueConstraint(
                fields=['school'],
                condition=Q(is_active=True),
                name='unique_active_session_per_school',
            ),
            models.CheckConstraint(
                condition=Q(end_date__gt=F('start_date')),
                name='session_end_after_start',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'start_date']),
            models.Index(fields=['school', 'attendance_locked']),
            models.Index(fields=['school', 'is_locked']),
        ]

    def clean(self):
        super().clean()
        if self.is_locked and not self.locked_at:
            self.locked_at = timezone.now()
        if not self.is_locked:
            self.locked_at = None
            self.locked_by = None

    def ensure_editable(self, allow_override=False, message='This academic session is locked.'):
        if self.is_locked and not allow_override:
            raise ValidationError(message)

    def __str__(self):
        return f"{self.school.name} - {self.name}"
