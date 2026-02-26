from django.db import models

from apps.academics.staff.models import Staff
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


class TimetableEntry(models.Model):
    DAY_CHOICES = (
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()

    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'staff_type': 'teacher'},
        related_name='timetable_entries'
    )

    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES)
    period_number = models.PositiveIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (
            'academic_session',
            'school_class',
            'section',
            'day_of_week',
            'period_number',
        )
        ordering = ['day_of_week', 'period_number', 'start_time', 'id']

    def __str__(self):
        return f"{self.school_class.name}-{self.section.name} {self.day_of_week} P{self.period_number}"
