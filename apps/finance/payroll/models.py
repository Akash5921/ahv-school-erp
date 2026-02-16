from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.academics.staff.models import Staff
from apps.finance.accounts.models import Ledger
from apps.core.utils.managers import SchoolManager

# Monthly salary definition
class SalaryStructure(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    staff = models.OneToOneField(Staff, on_delete=models.CASCADE)
    objects = SchoolManager()
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.staff.first_name} - {self.monthly_salary}"


# Actual payment record
class SalaryPayment(models.Model):
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE)
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)

    month = models.CharField(max_length=20)  # e.g. April 2025
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        Ledger.objects.create(
            school=self.salary_structure.school,
            academic_session=self.academic_session,
            entry_type='expense',
            description=f"Salary paid to {self.salary_structure.staff.first_name}",
            amount=self.amount_paid
        )

    def __str__(self):
        return f"{self.salary_structure.staff.first_name} - {self.month}"
