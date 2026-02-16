from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.utils.managers import SchoolManager


# Permanent student profile
class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)

    objects = SchoolManager()
    
    admission_number = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)

    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.admission_number} - {self.first_name}"


# Session-wise enrollment
class StudentEnrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)

    roll_number = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=20,
        choices=(
            ('active', 'Active'),
            ('passed', 'Passed'),
            ('left', 'Left'),
        ),
        default='active'
    )

    class Meta:
        unique_together = ('student', 'academic_session')

    def __str__(self):
        return f"{self.student.first_name} ({self.academic_session.name})"


class StudentMark(models.Model):

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100)

    marks_obtained = models.FloatField()
    total_marks = models.FloatField()

    exam_type = models.CharField(max_length=50)  # Midterm, Final etc.

    created_at = models.DateTimeField(auto_now_add=True)

    def percentage(self):
        if self.total_marks > 0:
            return round((self.marks_obtained / self.total_marks) * 100, 2)
        return 0

    def __str__(self):
        return f"{self.student} - {self.subject}"
