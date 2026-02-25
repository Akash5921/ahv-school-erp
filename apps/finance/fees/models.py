from decimal import Decimal

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

    class Meta:
        unique_together = ('school', 'academic_session', 'school_class', 'name')

    def __str__(self):
        return f"{self.school_class.name} - {self.name}"


class FeeInstallment(models.Model):
    fee_structure = models.ForeignKey(
        FeeStructure,
        on_delete=models.CASCADE,
        related_name='installments'
    )
    title = models.CharField(max_length=50)  # Installment 1, Quarter 1, etc.
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('fee_structure', 'title')
        ordering = ['due_date', 'id']

    def __str__(self):
        return f"{self.fee_structure} - {self.title}"


# Fee assigned to a student
class StudentFee(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    concession_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    concession_note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('student', 'fee_structure')

    @property
    def net_amount(self):
        net = Decimal(self.total_amount) - Decimal(self.concession_amount)
        if net < 0:
            return Decimal('0')
        return net

    @property
    def due_amount(self):
        due = self.net_amount - Decimal(self.paid_amount)
        if due < 0:
            return Decimal('0')
        return due

    def __str__(self):
        return f"{self.student.first_name} - {self.fee_structure.name}"


# Payment records
class FeePayment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    student_fee = models.ForeignKey(
        StudentFee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    receipt_number = models.CharField(max_length=50, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.student.first_name} - {self.amount} ({self.receipt_number or 'no-receipt'})"
