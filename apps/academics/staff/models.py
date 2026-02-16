from django.db import models
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager

class Staff(models.Model):
    STAFF_TYPE = (
        ('teacher', 'Teacher'),
        ('accountant', 'Accountant'),
        ('office', 'Office Staff'),
        ('driver', 'Driver'),
        ('helper', 'Helper'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()
    staff_id = models.CharField(max_length=50, unique=True)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)

    staff_type = models.CharField(max_length=20, choices=STAFF_TYPE)

    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    joining_date = models.DateField()
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} ({self.staff_type})"
