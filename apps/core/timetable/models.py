from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.hr.models import Staff, TeacherSubjectAssignment
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


DAY_CHOICES = (
    ('monday', 'Monday'),
    ('tuesday', 'Tuesday'),
    ('wednesday', 'Wednesday'),
    ('thursday', 'Thursday'),
    ('friday', 'Friday'),
    ('saturday', 'Saturday'),
)


class TimetableEntry(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )
    objects = SchoolManager()

    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )
    day_of_week = models.CharField(max_length=20, choices=DAY_CHOICES)
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='timetable_entries',
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['school_class__display_order', 'section__name', 'day_of_week', 'period__period_number']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'school_class', 'section', 'day_of_week', 'period'],
                condition=Q(is_active=True),
                name='unique_active_class_section_period_day_entry',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'day_of_week']),
            models.Index(fields=['school', 'session', 'teacher', 'day_of_week']),
            models.Index(fields=['school', 'session', 'school_class', 'section', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.school_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.section_id and self.section.school_class_id != self.school_class_id:
            raise ValidationError({'section': 'Section must belong to selected class.'})

        if self.period_id:
            if self.period.school_id != self.school_id:
                raise ValidationError({'period': 'Period must belong to selected school.'})
            if self.session_id and self.period.session_id != self.session_id:
                raise ValidationError({'period': 'Period must belong to selected session.'})

        if self.subject_id and self.subject.school_id != self.school_id:
            raise ValidationError({'subject': 'Subject must belong to selected school.'})

        if self.teacher_id:
            if self.teacher.school_id != self.school_id:
                raise ValidationError({'teacher': 'Teacher must belong to selected school.'})
            if not self.teacher.is_active:
                raise ValidationError({'teacher': 'Only active staff can be used in timetable.'})
            if getattr(self.teacher.user, 'role', None) != 'teacher':
                raise ValidationError({'teacher': 'Selected staff member is not a teacher.'})

        if self.school_class_id and self.subject_id and not ClassSubject.objects.filter(
            school_class=self.school_class,
            subject=self.subject,
        ).exists():
            raise ValidationError({'subject': 'Subject is not mapped to selected class.'})

        if self.teacher_id and self.school_class_id and self.subject_id and self.session_id:
            if not TeacherSubjectAssignment.objects.filter(
                school=self.school,
                session=self.session,
                teacher=self.teacher,
                school_class=self.school_class,
                subject=self.subject,
                is_active=True,
            ).exists():
                raise ValidationError(
                    {'teacher': 'Teacher is not allocated to this class-subject in selected session.'}
                )

        if not self.is_active:
            return

        class_conflict = TimetableEntry.objects.filter(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            day_of_week=self.day_of_week,
            period=self.period,
            is_active=True,
        ).exclude(pk=self.pk)
        if class_conflict.exists():
            raise ValidationError('Class-section already has an active timetable entry for this slot.')

        teacher_conflict = TimetableEntry.objects.filter(
            school=self.school,
            session=self.session,
            teacher=self.teacher,
            day_of_week=self.day_of_week,
            period=self.period,
            is_active=True,
        ).exclude(pk=self.pk)
        if teacher_conflict.exists():
            raise ValidationError({'teacher': 'Teacher is already assigned in another class for this slot.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return (
            f"{self.school_class.name}-{self.section.name} {self.get_day_of_week_display()} "
            f"P{self.period.period_number}"
        )
