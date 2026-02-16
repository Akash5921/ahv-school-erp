from django.db import models

class SchoolQuerySet(models.QuerySet):
    def for_school(self, school):
        return self.filter(school=school)


class SchoolManager(models.Manager):
    def get_queryset(self):
        return SchoolQuerySet(self.model, using=self._db)

    def for_school(self, school):
        return self.get_queryset().for_school(school)
