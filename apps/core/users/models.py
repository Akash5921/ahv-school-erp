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
        ('parent', 'Parent'),
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


class AuditLog(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    action = models.CharField(max_length=100)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    details = models.TextField(blank=True)

    method = models.CharField(max_length=10, blank=True)
    path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} by {self.user_id or 'system'}"
