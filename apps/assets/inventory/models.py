from django.db import models
from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.finance.accounts.models import Ledger
from apps.core.utils.managers import SchoolManager

class InventoryCategory(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True)

    name = models.CharField(max_length=150)
    location = models.CharField(max_length=100, blank=True)  # Lab, Room, Office
    quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name


class InventoryPurchase(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)

    quantity_purchased = models.PositiveIntegerField()
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_date = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # increase stock
        self.item.quantity += self.quantity_purchased
        self.item.save()

        super().save(*args, **kwargs)

        # record expense
        Ledger.objects.create(
            school=self.item.school,
            academic_session=self.academic_session,
            entry_type='expense',
            description=f"Inventory purchase: {self.item.name}",
            amount=self.total_cost
        )

    def __str__(self):
        return f"{self.item.name} - {self.quantity_purchased}"
