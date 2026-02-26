from django.conf import settings
from django.db import models

from apps.academics.staff.models import Staff
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


class Exam(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()

    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_exams'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'academic_session', 'name')
        ordering = ['-academic_session__start_date', '-start_date', 'name']

    def __str__(self):
        return f"{self.name} ({self.academic_session.name})"


class ExamSchedule(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='schedules')
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    max_marks = models.DecimalField(max_digits=7, decimal_places=2, default=100)
    pass_marks = models.DecimalField(max_digits=7, decimal_places=2, default=40)
    room = models.CharField(max_length=50, blank=True)
    invigilator = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invigilated_exam_schedules'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'exam', 'school_class', 'section', 'subject')
        ordering = ['date', 'start_time', 'school_class__order', 'section__name']

    def __str__(self):
        return f"{self.exam.name} - {self.school_class.name}-{self.section.name} - {self.subject.name}"
