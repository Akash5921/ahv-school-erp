from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.schools.models import School
from apps.core.students.models import Student
from apps.core.utils.managers import SchoolManager


class PromotionRecord(models.Model):
    STATUS_PROMOTED = 'promoted'
    STATUS_RETAINED = 'retained'
    STATUS_DROPPED = 'dropped'
    STATUS_CHOICES = (
        (STATUS_PROMOTED, 'Promoted'),
        (STATUS_RETAINED, 'Retained'),
        (STATUS_DROPPED, 'Dropped'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='promotion_records',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='promotion_records',
    )
    from_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name='promotion_records_from',
    )
    from_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name='promotion_records_from',
    )
    to_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name='promotion_records_to',
        null=True,
        blank=True,
    )
    to_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name='promotion_records_to',
        null=True,
        blank=True,
    )
    from_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.PROTECT,
        related_name='promotion_records_from',
    )
    to_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.PROTECT,
        related_name='promotion_records_to',
    )
    promoted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_promotions',
    )
    promoted_on = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROMOTED)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-promoted_on', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'from_session', 'to_session'],
                name='unique_student_promotion_transition',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'from_session', 'to_session']),
            models.Index(fields=['school', 'status', 'promoted_on']),
        ]

    def clean(self):
        super().clean()

        if self.school_id and self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({'student': 'Student must belong to selected school.'})

        if self.from_session_id and self.from_session.school_id != self.school_id:
            raise ValidationError({'from_session': 'From session must belong to selected school.'})
        if self.to_session_id and self.to_session.school_id != self.school_id:
            raise ValidationError({'to_session': 'To session must belong to selected school.'})

        if self.from_session_id and self.to_session_id and self.from_session_id == self.to_session_id:
            raise ValidationError('From session and to session must be different.')

        if self.from_class_id:
            if self.from_class.school_id != self.school_id:
                raise ValidationError({'from_class': 'From class must belong to selected school.'})
            if self.from_session_id and self.from_class.session_id != self.from_session_id:
                raise ValidationError({'from_class': 'From class must belong to from session.'})

        if self.from_section_id and self.from_section.school_class_id != self.from_class_id:
            raise ValidationError({'from_section': 'From section must belong to from class.'})

        if self.status in {self.STATUS_PROMOTED, self.STATUS_RETAINED}:
            if not self.to_class_id:
                raise ValidationError({'to_class': 'Target class is required.'})
            if not self.to_section_id:
                raise ValidationError({'to_section': 'Target section is required.'})

        if self.to_class_id:
            if self.to_class.school_id != self.school_id:
                raise ValidationError({'to_class': 'Target class must belong to selected school.'})
            if self.to_session_id and self.to_class.session_id != self.to_session_id:
                raise ValidationError({'to_class': 'Target class must belong to target session.'})

        if self.to_section_id and self.to_section.school_class_id != self.to_class_id:
            raise ValidationError({'to_section': 'Target section must belong to target class.'})

    def __str__(self):
        return f"{self.student.admission_number}: {self.from_session.name} -> {self.to_session.name}"
