from django.db import models
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager

class SchoolClass(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='classes'
    )
    objects = SchoolManager()

    name = models.CharField(max_length=50)  # e.g. Class 1, Nursery
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.school.name} - {self.name}"


class Section(models.Model):
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='sections'
    )
    name = models.CharField(max_length=10)  # A, B, C

    def __str__(self):
        return f"{self.school_class.name} - {self.name}"
