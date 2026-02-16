from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass
from apps.academics.students.models import Student
from apps.core.utils.managers import SchoolManager

# What fee applies to a class in a session
class FeeStructure(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()

    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)

    name = models.CharField(max_length=100)  # Tuition, Transport, etc.
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.school_class.name} - {self.name}"


# Fee assigned to a student
class StudentFee(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def due_amount(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"{self.student.first_name} - {self.fee_structure.name}"


# Payment records
class FeePayment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.student.first_name} - {self.amount}"
