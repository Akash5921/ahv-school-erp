from django.conf import settings
from django.db import models

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


class Homework(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()

    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    is_published = models.BooleanField(default=True)

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_homeworks'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', '-id']

    def __str__(self):
        return f"{self.title} ({self.school_class.name}-{self.section.name})"
