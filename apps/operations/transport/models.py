from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.academics.students.models import Student
from apps.academics.staff.models import Staff
from apps.core.utils.managers import SchoolManager

class Bus(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()
    bus_number = models.CharField(max_length=50)
    capacity = models.PositiveIntegerField()
    driver = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'staff_type': 'driver'}
    )

    def __str__(self):
        return f"{self.bus_number}"


class Route(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    start_point = models.CharField(max_length=100)
    end_point = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class StudentTransport(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    route = models.ForeignKey(Route, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('student', 'academic_session')

    def __str__(self):
        return f"{self.student.first_name} - {self.bus.bus_number}"
