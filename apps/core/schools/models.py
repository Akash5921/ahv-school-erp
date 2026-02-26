from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils.text import slugify


class School(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False, db_index=True)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=40, unique=True, null=True, blank=True)
    subdomain = models.SlugField(max_length=63, unique=True, null=True, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=64, default='UTC')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    current_session = models.ForeignKey(
        'academic_sessions.AcademicSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_for_schools'
    )

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['subdomain']),
            models.Index(fields=['is_active']),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            base_code = slugify(self.name).replace('-', '_')[:30] or 'school'
            candidate = base_code
            sequence = 1
            while School.objects.exclude(pk=self.pk).filter(code=candidate).exists():
                suffix = f'_{sequence}'
                candidate = f'{base_code[:30 - len(suffix)]}{suffix}'
                sequence += 1
            self.code = candidate

        if self.subdomain:
            self.subdomain = slugify(self.subdomain)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class SchoolDomain(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='domains',
    )
    domain = models.CharField(max_length=253, unique=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'domain']
        constraints = [
            models.UniqueConstraint(
                fields=['school'],
                condition=Q(is_primary=True),
                name='unique_primary_domain_per_school',
            )
        ]

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.domain
