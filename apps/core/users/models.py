from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models

from apps.core.schools.models import School


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'superadmin')
        extra_fields['school'] = None
        return super().create_superuser(username, email=email, password=password, **extra_fields)


class User(AbstractUser):
    ROLE_SUPERADMIN = 'superadmin'
    ROLE_SCHOOLADMIN = 'schooladmin'
    ROLE_ACCOUNTANT = 'accountant'
    ROLE_TEACHER = 'teacher'
    ROLE_STAFF = 'staff'
    ROLE_PARENT = 'parent'

    ROLE_CHOICES = (
        (ROLE_SUPERADMIN, 'Super Admin'),
        (ROLE_SCHOOLADMIN, 'School Admin'),
        (ROLE_ACCOUNTANT, 'Accountant'),
        (ROLE_TEACHER, 'Teacher'),
        (ROLE_STAFF, 'Staff'),
        (ROLE_PARENT, 'Parent'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_TEACHER)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
    )

    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['school', 'role']),
        ]

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != self.ROLE_SUPERADMIN:
            self.role = self.ROLE_SUPERADMIN

        if self.role == self.ROLE_SUPERADMIN:
            self.school = None
        elif not self.school:
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
        indexes = [
            models.Index(fields=['school', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f"{self.action} by {self.user_id or 'system'}"
