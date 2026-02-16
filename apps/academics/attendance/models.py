from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.academics.students.models import Student
from apps.core.utils.managers import SchoolManager

class StudentAttendance(models.Model):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()
    
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)

    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'date', 'academic_session')

    def __str__(self):
        return f"{self.student.first_name} - {self.date} ({self.status})"
