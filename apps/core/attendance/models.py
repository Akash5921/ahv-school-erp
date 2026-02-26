from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.hr.models import Staff
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.utils.managers import SchoolManager


class StudentAttendance(models.Model):
    STATUS_PRESENT = 'present'
    STATUS_ABSENT = 'absent'
    STATUS_LEAVE = 'leave'
    STATUS_LATE = 'late'
    STATUS_CHOICES = (
        (STATUS_PRESENT, 'Present'),
        (STATUS_ABSENT, 'Absent'),
        (STATUS_LEAVE, 'Leave'),
        (STATUS_LATE, 'Late'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_attendances',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_attendances',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='daily_attendances',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='student_attendances',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='student_attendances',
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marked_student_attendance',
    )
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'student__admission_number']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'date'],
                name='unique_student_daily_attendance_per_date',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'date', 'status']),
            models.Index(fields=['school', 'session', 'school_class', 'section']),
        ]

    def clean(self):
        super().clean()

        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({'student': 'Student must belong to selected school.'})

        if self.session_id:
            if self.session.school_id != self.school_id:
                raise ValidationError({'session': 'Session must belong to selected school.'})
            if self.date and (self.date < self.session.start_date or self.date > self.session.end_date):
                raise ValidationError({'date': 'Attendance date must be within session range.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.section_id and self.section.school_class_id != self.school_class_id:
            raise ValidationError({'section': 'Section must belong to selected class.'})

        if self.student_id and self.session_id and self.school_class_id and self.section_id:
            if not StudentSessionRecord.objects.filter(
                student=self.student,
                session=self.session,
                school_class=self.school_class,
                section=self.section,
            ).exists():
                raise ValidationError('Student is not assigned to selected class-section for this session.')

    def __str__(self):
        return f"{self.student.admission_number} - {self.date} ({self.status})"


class StudentPeriodAttendance(models.Model):
    STATUS_PRESENT = StudentAttendance.STATUS_PRESENT
    STATUS_ABSENT = StudentAttendance.STATUS_ABSENT
    STATUS_LEAVE = StudentAttendance.STATUS_LEAVE
    STATUS_LATE = StudentAttendance.STATUS_LATE
    STATUS_CHOICES = StudentAttendance.STATUS_CHOICES

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='period_attendances',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    date = models.DateField()
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='student_period_attendances',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marked_student_period_attendance',
    )
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'period__period_number', 'student__admission_number']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'date', 'period'],
                name='unique_student_period_attendance_per_slot',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'date', 'period']),
            models.Index(fields=['school', 'session', 'school_class', 'section']),
        ]

    def clean(self):
        super().clean()

        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({'student': 'Student must belong to selected school.'})

        if self.session_id:
            if self.session.school_id != self.school_id:
                raise ValidationError({'session': 'Session must belong to selected school.'})
            if self.date and (self.date < self.session.start_date or self.date > self.session.end_date):
                raise ValidationError({'date': 'Attendance date must be within session range.'})

        if self.period_id:
            if self.period.school_id != self.school_id:
                raise ValidationError({'period': 'Period must belong to selected school.'})
            if self.session_id and self.period.session_id != self.session_id:
                raise ValidationError({'period': 'Period must belong to selected session.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.section_id and self.section.school_class_id != self.school_class_id:
            raise ValidationError({'section': 'Section must belong to selected class.'})

        if self.subject_id and self.subject.school_id != self.school_id:
            raise ValidationError({'subject': 'Subject must belong to selected school.'})

        if self.teacher_id:
            if self.teacher.school_id != self.school_id:
                raise ValidationError({'teacher': 'Teacher must belong to selected school.'})
            if getattr(self.teacher.user, 'role', None) != 'teacher':
                raise ValidationError({'teacher': 'Only teacher staff can mark period attendance.'})

        if self.school_class_id and self.subject_id:
            if not ClassSubject.objects.filter(school_class=self.school_class, subject=self.subject).exists():
                raise ValidationError({'subject': 'Subject is not mapped to selected class.'})

        if self.student_id and self.session_id and self.school_class_id and self.section_id:
            if not StudentSessionRecord.objects.filter(
                student=self.student,
                session=self.session,
                school_class=self.school_class,
                section=self.section,
            ).exists():
                raise ValidationError('Student is not assigned to selected class-section for this session.')

    def __str__(self):
        return f"{self.student.admission_number} - {self.date} P{self.period.period_number} ({self.status})"


class StudentAttendanceSummary(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_attendance_summaries',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_attendance_summaries',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='attendance_summaries',
    )
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    total_working_days = models.PositiveIntegerField(default=0)
    present_days = models.PositiveIntegerField(default=0)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', '-month', 'student__admission_number']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'session', 'year', 'month'],
                name='unique_student_attendance_summary_per_month',
            ),
            models.CheckConstraint(
                condition=Q(month__gte=1) & Q(month__lte=12),
                name='student_attendance_summary_month_range',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'year', 'month']),
            models.Index(fields=['school', 'attendance_percentage']),
        ]

    def clean(self):
        super().clean()
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({'student': 'Student must belong to selected school.'})
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.present_days > self.total_working_days:
            raise ValidationError({'present_days': 'Present days cannot exceed total working days.'})

    def __str__(self):
        return (
            f"{self.student.admission_number} - {self.month}/{self.year} "
            f"({self.attendance_percentage}%)"
        )
