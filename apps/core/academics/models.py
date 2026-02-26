from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


DAY_CHOICES = (
    ('monday', 'Monday'),
    ('tuesday', 'Tuesday'),
    ('wednesday', 'Wednesday'),
    ('thursday', 'Thursday'),
    ('friday', 'Friday'),
    ('saturday', 'Saturday'),
    ('sunday', 'Sunday'),
)


class SchoolClass(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='classes',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='classes',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=50)  # e.g. 1st, 10th
    code = models.CharField(max_length=20, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'name'],
                name='unique_class_name_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.school_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Selected session does not belong to the selected school.'})

    def delete(self, *args, **kwargs):
        if self.sections.exists():
            raise ValidationError('Cannot delete class while sections exist.')
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.name} ({self.session.name})"


class Section(models.Model):
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='sections',
    )
    name = models.CharField(max_length=10)  # A, B, C
    capacity = models.PositiveIntegerField(null=True, blank=True)
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='class_teacher_sections',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school_class', 'name'],
                name='unique_section_name_per_class',
            ),
        ]

    @property
    def school(self):
        return self.school_class.school

    @property
    def session(self):
        return self.school_class.session

    def clean(self):
        super().clean()
        if self.class_teacher_id:
            if self.class_teacher.school_id != self.school_class.school_id:
                raise ValidationError({'class_teacher': 'Class teacher must belong to the same school.'})

    def delete(self, *args, **kwargs):
        # Student dependency check will be enforced in a later phase.
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.school_class.name} - {self.name}"


class Subject(models.Model):
    TYPE_THEORY = 'theory'
    TYPE_PRACTICAL = 'practical'
    SUBJECT_TYPE_CHOICES = (
        (TYPE_THEORY, 'Theory'),
        (TYPE_PRACTICAL, 'Practical'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='subjects',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    subject_type = models.CharField(max_length=20, choices=SUBJECT_TYPE_CHOICES, default=TYPE_THEORY)
    is_optional = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'code'],
                name='unique_subject_code_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()
        if not self.code:
            raise ValidationError({'code': 'Subject code is required.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.code} - {self.name}"


class ClassSubject(models.Model):
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='class_subjects',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='class_subjects',
    )
    is_compulsory = models.BooleanField(default=True)
    max_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('100'))
    pass_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('33'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['school_class__display_order', 'subject__name']
        constraints = [
            models.UniqueConstraint(
                fields=['school_class', 'subject'],
                name='unique_subject_mapping_per_class',
            ),
        ]

    def clean(self):
        super().clean()
        if self.school_class_id and self.subject_id:
            if self.school_class.school_id != self.subject.school_id:
                raise ValidationError({'subject': 'Subject must belong to the same school as the class.'})
            if not self.subject.is_active:
                raise ValidationError({'subject': 'Only active subjects can be mapped.'})

        if self.max_marks is not None and self.max_marks <= 0:
            raise ValidationError({'max_marks': 'Maximum marks must be greater than zero.'})
        if self.pass_marks is not None and self.pass_marks < 0:
            raise ValidationError({'pass_marks': 'Pass marks cannot be negative.'})
        if self.max_marks is not None and self.pass_marks is not None and self.pass_marks > self.max_marks:
            raise ValidationError({'pass_marks': 'Pass marks cannot exceed maximum marks.'})

    def __str__(self):
        return f"{self.school_class.name} -> {self.subject.code}"


class Period(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='periods',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='periods',
    )
    objects = SchoolManager()

    period_number = models.PositiveIntegerField()  # 1,2,3...
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['period_number', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'period_number'],
                name='unique_period_number_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.school_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Selected session does not belong to the selected school.'})

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})

        if not (self.is_active and self.school_id and self.session_id and self.start_time and self.end_time):
            return

        active_periods = Period.objects.filter(
            school_id=self.school_id,
            session_id=self.session_id,
            is_active=True,
        ).exclude(pk=self.pk)

        overlap_exists = active_periods.filter(
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
        ).exists()
        if overlap_exists:
            raise ValidationError('Period timing overlaps with another active period in this session.')

        current_duration = datetime.combine(datetime.min.date(), self.end_time) - datetime.combine(
            datetime.min.date(), self.start_time
        )
        reference_period = active_periods.order_by('period_number').first()
        if reference_period:
            reference_duration = datetime.combine(datetime.min.date(), reference_period.end_time) - datetime.combine(
                datetime.min.date(), reference_period.start_time
            )
            if current_duration != reference_duration:
                raise ValidationError('Period duration must be consistent for the session.')

    @property
    def duration(self):
        if not self.start_time or not self.end_time:
            return timedelta(0)
        return datetime.combine(datetime.min.date(), self.end_time) - datetime.combine(
            datetime.min.date(), self.start_time
        )

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"P{self.period_number} ({self.session.name})"


class AcademicConfig(models.Model):
    ATTENDANCE_DAILY = 'daily'
    ATTENDANCE_PERIOD = 'period-wise'
    ATTENDANCE_CHOICES = (
        (ATTENDANCE_DAILY, 'Daily'),
        (ATTENDANCE_PERIOD, 'Period-wise'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='academic_configs',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='academic_configs',
    )
    objects = SchoolManager()

    total_periods_per_day = models.PositiveIntegerField(default=8)
    working_days = models.JSONField(default=list)
    grading_enabled = models.BooleanField(default=True)
    attendance_type = models.CharField(max_length=20, choices=ATTENDANCE_CHOICES, default=ATTENDANCE_DAILY)
    marks_decimal_allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-session__start_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session'],
                name='unique_academic_config_per_session',
            ),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.school_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Selected session does not belong to the selected school.'})

        if self.total_periods_per_day <= 0:
            raise ValidationError({'total_periods_per_day': 'Total periods per day must be greater than zero.'})

        if not isinstance(self.working_days, list) or not self.working_days:
            raise ValidationError({'working_days': 'Working days must contain at least one day.'})

        allowed_days = {choice[0] for choice in DAY_CHOICES}
        invalid_days = [day for day in self.working_days if day not in allowed_days]
        if invalid_days:
            raise ValidationError({'working_days': f'Invalid working days: {", ".join(invalid_days)}'})

    def __str__(self):
        return f"Academic Config - {self.school.name} ({self.session.name})"
