from django.db import models



class School(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    current_session = models.ForeignKey(
        'academic_sessions.AcademicSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_for_schools'
    )



    def __str__(self):
        return self.name
