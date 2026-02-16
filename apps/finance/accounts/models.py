from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.core.utils.managers import SchoolManager


class Ledger(models.Model):

    ENTRY_TYPE = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )


    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='ledgers'
    )
    objects = SchoolManager()

    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='ledgers'
    )

    entry_type = models.CharField(
        max_length=10,
        choices=ENTRY_TYPE
    )

    description = models.CharField(
        max_length=255
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    transaction_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date']

    def __str__(self):
        return f"{self.entry_type.upper()} - {self.amount}"
