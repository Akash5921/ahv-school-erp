from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord, StudentSubject
from apps.core.utils.managers import SchoolManager


class ExamType(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='exam_types',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='exam_types',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=100)
    weightage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'name'],
                name='unique_exam_type_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.weightage is not None and self.weightage < 0:
            raise ValidationError({'weightage': 'Weightage cannot be negative.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.name} ({self.session.name})"


class Exam(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='exams',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='exams',
    )
    objects = SchoolManager()

    exam_type = models.ForeignKey(
        ExamType,
        on_delete=models.PROTECT,
        related_name='exams',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name='exams',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name='exams',
        null=True,
        blank=True,
    )
    start_date = models.DateField()
    end_date = models.DateField()
    total_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('100'))
    is_locked = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_exams_core',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'exam_type', 'school_class', 'section', 'start_date', 'end_date'],
                name='unique_exam_window_per_scope',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_locked']),
            models.Index(fields=['school', 'session', 'school_class', 'section']),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.exam_type_id:
            if self.exam_type.school_id != self.school_id:
                raise ValidationError({'exam_type': 'Exam type must belong to selected school.'})
            if self.session_id and self.exam_type.session_id != self.session_id:
                raise ValidationError({'exam_type': 'Exam type must belong to selected session.'})
            if not self.exam_type.is_active:
                raise ValidationError({'exam_type': 'Inactive exam type cannot be used.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})
            if not self.school_class.is_active:
                raise ValidationError({'school_class': 'Cannot create exam for inactive class.'})

        if self.section_id and self.section.school_class_id != self.school_class_id:
            raise ValidationError({'section': 'Section must belong to selected class.'})

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be after or equal to start date.'})

        if self.total_marks is not None and self.total_marks <= 0:
            raise ValidationError({'total_marks': 'Total marks must be greater than zero.'})

        if not self.pk:
            return

        previous = Exam.objects.filter(pk=self.pk).first()
        if not previous or not previous.is_locked:
            return

        protected_fields = [
            'school_id',
            'session_id',
            'exam_type_id',
            'school_class_id',
            'section_id',
            'start_date',
            'end_date',
            'total_marks',
        ]
        if any(getattr(previous, field) != getattr(self, field) for field in protected_fields):
            raise ValidationError('Locked exams cannot be edited.')

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        section = self.section.name if self.section_id else 'All'
        return f"{self.exam_type.name} - {self.school_class.name} ({section})"


class ExamSubject(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='exam_subjects',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name='exam_subjects',
    )
    max_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('100'))
    pass_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('33'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['subject__name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['exam', 'subject'],
                name='unique_exam_subject_mapping',
            ),
        ]

    def clean(self):
        super().clean()
        if self.exam_id and self.exam.is_locked:
            raise ValidationError('Cannot modify subjects for a locked exam.')

        if self.subject_id:
            if self.subject.school_id != self.exam.school_id:
                raise ValidationError({'subject': 'Subject must belong to same school as exam.'})
            if not self.subject.is_active:
                raise ValidationError({'subject': 'Inactive subject cannot be added to exam.'})

        if self.exam_id and self.subject_id and not ClassSubject.objects.filter(
            school_class=self.exam.school_class,
            subject=self.subject,
        ).exists():
            raise ValidationError({'subject': 'Subject is not mapped to selected class.'})

        if self.max_marks is not None and self.max_marks <= 0:
            raise ValidationError({'max_marks': 'Maximum marks must be greater than zero.'})
        if self.pass_marks is not None and self.pass_marks < 0:
            raise ValidationError({'pass_marks': 'Pass marks cannot be negative.'})
        if (
            self.max_marks is not None
            and self.pass_marks is not None
            and self.pass_marks > self.max_marks
        ):
            raise ValidationError({'pass_marks': 'Pass marks cannot exceed maximum marks.'})

    def delete(self, *args, **kwargs):
        if self.exam.student_marks.filter(subject=self.subject).exists():
            raise ValidationError('Cannot remove exam subject once marks are entered.')
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.exam} - {self.subject.code}"


class GradeScale(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='grade_scales_core',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='grade_scales_core',
    )
    objects = SchoolManager()

    grade_name = models.CharField(max_length=20)
    min_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    max_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', '-max_percentage', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'grade_name'],
                name='unique_grade_name_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.min_percentage < 0 or self.min_percentage > 100:
            raise ValidationError({'min_percentage': 'Min percentage must be between 0 and 100.'})
        if self.max_percentage < 0 or self.max_percentage > 100:
            raise ValidationError({'max_percentage': 'Max percentage must be between 0 and 100.'})
        if self.min_percentage > self.max_percentage:
            raise ValidationError({'max_percentage': 'Max percentage must be greater than or equal to min percentage.'})

        overlap = GradeScale.objects.filter(
            school=self.school,
            session=self.session,
            is_active=True,
            min_percentage__lte=self.max_percentage,
            max_percentage__gte=self.min_percentage,
        ).exclude(pk=self.pk)
        if overlap.exists():
            raise ValidationError('Grade percentage range overlaps with an existing grade scale.')

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.grade_name} ({self.min_percentage}-{self.max_percentage})"


class StudentMark(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_marks',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_marks',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exam_marks',
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='student_marks',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name='student_marks',
    )
    marks_obtained = models.DecimalField(max_digits=7, decimal_places=2)
    grade = models.CharField(max_length=20, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entered_student_marks',
    )
    is_locked = models.BooleanField(default=False)
    entered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['exam__start_date', 'subject__name', 'student__admission_number']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'exam', 'subject'],
                name='unique_student_exam_subject_mark',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'exam', 'subject']),
            models.Index(fields=['school', 'session', 'student']),
        ]

    def clean(self):
        super().clean()
        if self.exam_id:
            if self.exam.school_id != self.school_id:
                raise ValidationError({'exam': 'Exam must belong to selected school.'})
            if self.exam.session_id != self.session_id:
                raise ValidationError({'exam': 'Exam must belong to selected session.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})

        if self.subject_id:
            if self.subject.school_id != self.school_id:
                raise ValidationError({'subject': 'Subject must belong to selected school.'})

        if self.exam_id and self.exam.is_locked:
            raise ValidationError('Cannot enter or update marks after exam result is locked.')

        if self.marks_obtained is None or self.marks_obtained < 0:
            raise ValidationError({'marks_obtained': 'Marks cannot be negative.'})

        if self.exam_id and self.subject_id:
            exam_subject = ExamSubject.objects.filter(
                exam=self.exam,
                subject=self.subject,
                is_active=True,
            ).first()
            if not exam_subject:
                raise ValidationError({'subject': 'Subject is not configured for selected exam.'})
            if self.marks_obtained > exam_subject.max_marks:
                raise ValidationError({'marks_obtained': f"Marks cannot exceed {exam_subject.max_marks}."})

        if self.exam_id and self.student_id:
            student_scope = StudentSessionRecord.objects.filter(
                student=self.student,
                session=self.session,
                school_class=self.exam.school_class,
            )
            if self.exam.section_id:
                student_scope = student_scope.filter(section=self.exam.section)

            if not student_scope.exists():
                raise ValidationError({'student': 'Student does not belong to exam class-section for session.'})

        if self.student_id and self.subject_id:
            if not StudentSubject.objects.filter(
                student=self.student,
                session=self.session,
                subject=self.subject,
                is_active=True,
            ).exists():
                raise ValidationError({'subject': 'Subject is not linked to selected student in this session.'})

        if not self.pk:
            return

        previous = StudentMark.objects.filter(pk=self.pk).first()
        if not previous or not previous.is_locked:
            return

        if (
            previous.marks_obtained != self.marks_obtained
            or previous.remarks != self.remarks
            or previous.grade != self.grade
        ):
            raise ValidationError('Locked marks cannot be edited.')

    def __str__(self):
        return f"{self.student.admission_number} - {self.exam.id} - {self.subject.code}"


class ExamResultSummary(models.Model):
    STATUS_PASS = 'pass'
    STATUS_FAIL = 'fail'
    STATUS_CHOICES = (
        (STATUS_PASS, 'Pass'),
        (STATUS_FAIL, 'Fail'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='exam_result_summaries',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='exam_result_summaries',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exam_result_summaries',
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name='result_summaries',
    )
    total_marks = models.DecimalField(max_digits=9, decimal_places=2)
    percentage = models.DecimalField(max_digits=6, decimal_places=2)
    grade = models.CharField(max_length=20, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    result_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_FAIL)
    is_locked = models.BooleanField(default=False)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rank', '-percentage', 'student__admission_number']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'exam'],
                name='unique_exam_result_summary_per_student',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'exam']),
            models.Index(fields=['school', 'session', 'exam', 'rank']),
        ]

    def clean(self):
        super().clean()
        if self.exam_id:
            if self.exam.school_id != self.school_id:
                raise ValidationError({'exam': 'Exam must belong to selected school.'})
            if self.exam.session_id != self.session_id:
                raise ValidationError({'exam': 'Exam must belong to selected session.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})

        if self.rank is not None and self.rank <= 0:
            raise ValidationError({'rank': 'Rank must be greater than zero.'})

        if not self.pk:
            return

        previous = ExamResultSummary.objects.filter(pk=self.pk).first()
        if not previous or not previous.is_locked:
            return

        protected_fields = [
            'total_marks',
            'percentage',
            'grade',
            'rank',
            'attendance_percentage',
            'result_status',
        ]
        if any(getattr(previous, field) != getattr(self, field) for field in protected_fields):
            raise ValidationError('Locked result summaries cannot be edited.')

    def __str__(self):
        return f"{self.student.admission_number} - {self.exam.id} ({self.percentage}%)"
