from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


class Notice(models.Model):
    TARGET_ROLE_CHOICES = (
        ('all', 'All Users'),
        ('parent', 'Parents'),
        ('teacher', 'Teachers'),
        ('accountant', 'Accountants'),
        ('staff', 'Staff'),
        ('schooladmin', 'School Admin'),
    )
    PRIORITY_CHOICES = (
        ('info', 'Info'),
        ('important', 'Important'),
        ('urgent', 'Urgent'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    objects = SchoolManager()

    title = models.CharField(max_length=150)
    message = models.TextField()
    target_role = models.CharField(max_length=20, choices=TARGET_ROLE_CHOICES, default='all')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='info')
    is_published = models.BooleanField(default=True)
    publish_at = models.DateTimeField(default=timezone.now)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_notices'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-publish_at', '-id']

    def __str__(self):
        return f"{self.title} ({self.school_id})"


class NoticeRead(models.Model):
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='read_entries')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notice_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('notice', 'user')

    def __str__(self):
        return f"NoticeRead<{self.notice_id},{self.user_id}>"
