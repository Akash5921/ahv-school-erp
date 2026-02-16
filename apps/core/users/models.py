from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.core.schools.models import School


class User(AbstractUser):

    ROLE_CHOICES = (
        ('superadmin', 'Super Admin'),
        ('schooladmin', 'School Admin'),
        ('accountant', 'Accountant'),
        ('teacher', 'Teacher'),
        ('staff', 'Staff'),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='teacher'
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,      # Superadmin can be null
        blank=True
    )

    def save(self, *args, **kwargs):
        """
        Enforce:
        - Superadmin → no school required
        - All other roles → school required
        """

        if self.role != 'superadmin' and not self.school:
            raise ValueError("Non-superadmin users must be assigned to a school.")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"
