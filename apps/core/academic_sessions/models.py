from django.db import models
from apps.core.utils.managers import SchoolManager

class AcademicSession(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='academic_sessions'
    )



    objects = SchoolManager()
    
    name = models.CharField(max_length=20)  # e.g. 2024-25
    start_date = models.DateField()
    end_date = models.DateField()

    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'name')

    def __str__(self):
        return f"{self.school.name} - {self.name}"
