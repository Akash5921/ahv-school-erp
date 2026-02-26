from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


class Designation(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='designations',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                name='unique_designation_name_per_school',
            ),
        ]

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return self.name


class Staff(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_RESIGNED = 'resigned'
    STATUS_TERMINATED = 'terminated'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_RESIGNED, 'Resigned'),
        (STATUS_TERMINATED, 'Terminated'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='staff_profiles',
    )
    objects = SchoolManager()

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='staff_profile',
    )
    employee_id = models.CharField(max_length=50)
    joining_date = models.DateField()
    designation = models.ForeignKey(
        Designation,
        on_delete=models.PROTECT,
        related_name='staff_members',
    )
    department = models.CharField(max_length=120, blank=True)
    qualification = models.CharField(max_length=255, blank=True)
    experience_years = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal('0.0'),
    )
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    photo = models.ImageField(upload_to='hr/staff/photos/', null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['employee_id', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'employee_id'],
                name='unique_employee_id_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.user_id:
            if self.user.school_id != self.school_id:
                raise ValidationError({'user': 'User must belong to the selected school.'})
            if self.user.role in {'superadmin', 'parent'}:
                raise ValidationError({'user': 'Selected user role cannot be linked as staff.'})

        if self.designation_id and self.designation.school_id != self.school_id:
            raise ValidationError({'designation': 'Designation must belong to the same school.'})

        if self.experience_years is not None and self.experience_years < 0:
            raise ValidationError({'experience_years': 'Experience cannot be negative.'})

        if self.status != self.STATUS_ACTIVE and self.is_active:
            raise ValidationError({'is_active': 'Inactive status cannot be marked active.'})

    def delete(self, *args, **kwargs):
        if self.is_active or self.status == self.STATUS_ACTIVE:
            self.is_active = False
            self.status = self.STATUS_TERMINATED
            self.save(update_fields=['is_active', 'status'])

    @property
    def full_name(self):
        return self.user.get_full_name().strip() or self.user.username

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"


class TeacherSubjectAssignment(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='teacher_subject_assignments',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='teacher_subject_assignments',
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='subject_assignments',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='teacher_subject_assignments',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='teacher_subject_assignments',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['school_class__display_order', 'subject__name', 'teacher__employee_id']
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'school_class', 'subject', 'session'],
                name='unique_teacher_subject_assignment',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.school_id and self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.teacher_id and self.teacher.school_id != self.school_id:
            raise ValidationError({'teacher': 'Teacher must belong to selected school.'})
        if self.teacher_id and not self.teacher.is_active:
            raise ValidationError({'teacher': 'Only active staff can be assigned.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.subject_id and self.subject.school_id != self.school_id:
            raise ValidationError({'subject': 'Subject must belong to selected school.'})

        if self.school_class_id and self.subject_id:
            if not ClassSubject.objects.filter(
                school_class=self.school_class,
                subject=self.subject,
            ).exists():
                raise ValidationError({'subject': 'Subject is not mapped with selected class.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.teacher} - {self.school_class.name} - {self.subject.code}"


class ClassTeacher(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments',
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments',
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['school_class__display_order', 'section__name', '-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'session', 'school_class', 'section'],
                name='unique_teacher_class_section_session',
            ),
            models.UniqueConstraint(
                fields=['school', 'session', 'section'],
                condition=Q(is_active=True),
                name='unique_active_class_teacher_per_section',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.school_id and self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.teacher_id and self.teacher.school_id != self.school_id:
            raise ValidationError({'teacher': 'Teacher must belong to selected school.'})
        if self.teacher_id and not self.teacher.is_active:
            raise ValidationError({'teacher': 'Only active staff can be class teacher.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.section_id and self.section.school_class_id != self.school_class_id:
            raise ValidationError({'section': 'Section must belong to selected class.'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_active and self.school_id and self.session_id and self.section_id:
                ClassTeacher.objects.filter(
                    school_id=self.school_id,
                    session_id=self.session_id,
                    section_id=self.section_id,
                    is_active=True,
                ).exclude(pk=self.pk).update(is_active=False)

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.school_class.name}-{self.section.name}: {self.teacher.full_name}"


class StaffAttendance(models.Model):
    STATUS_PRESENT = 'present'
    STATUS_HALF_DAY = 'half-day'
    STATUS_LEAVE = 'leave'
    STATUS_CHOICES = (
        (STATUS_PRESENT, 'Present'),
        (STATUS_HALF_DAY, 'Half-Day'),
        (STATUS_LEAVE, 'Leave'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='staff_attendances',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='staff_attendances',
        null=True,
        blank=True,
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='attendance_records',
    )
    date = models.DateField()
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_info = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marked_staff_attendance',
    )
    is_locked = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'staff__employee_id']
        constraints = [
            models.UniqueConstraint(
                fields=['staff', 'date'],
                name='unique_staff_attendance_per_day',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'date', 'status']),
        ]

    def clean(self):
        super().clean()

        if self.staff_id and self.staff.school_id != self.school_id:
            raise ValidationError({'staff': 'Staff must belong to selected school.'})

        if self.session_id:
            if self.session.school_id != self.school_id:
                raise ValidationError({'session': 'Session must belong to selected school.'})
            if self.date and (self.date < self.session.start_date or self.date > self.session.end_date):
                raise ValidationError({'date': 'Attendance date must be within selected session range.'})

        if self.status == self.STATUS_LEAVE:
            return

        if self.check_out_time and not self.check_in_time:
            raise ValidationError({'check_in_time': 'Check-in is required when check-out is provided.'})

        if self.check_in_time and self.check_out_time and self.check_out_time <= self.check_in_time:
            raise ValidationError({'check_out_time': 'Check-out must be after check-in.'})

    def __str__(self):
        return f"{self.staff.employee_id} - {self.date}"


class LeaveRequest(models.Model):
    TYPE_CASUAL = 'casual'
    TYPE_SICK = 'sick'
    TYPE_PAID = 'paid'
    LEAVE_TYPE_CHOICES = (
        (TYPE_CASUAL, 'Casual'),
        (TYPE_SICK, 'Sick'),
        (TYPE_PAID, 'Paid'),
    )

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='leave_requests',
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='leave_requests',
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leave_requests',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', 'start_date']),
        ]

    def clean(self):
        super().clean()

        if self.staff_id and self.staff.school_id != self.school_id:
            raise ValidationError({'staff': 'Staff must belong to selected school.'})

        if self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be after or equal to start date.'})

        overlap = LeaveRequest.objects.filter(
            staff_id=self.staff_id,
            status__in=[self.STATUS_PENDING, self.STATUS_APPROVED],
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk)

        if overlap.exists():
            raise ValidationError('Leave request overlaps with an existing leave period.')

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.staff.employee_id} {self.start_date} to {self.end_date}"


class Substitution(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='substitutions',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='substitutions',
    )
    date = models.DateField()
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='substitutions',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='substitutions',
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='substitutions',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='substitutions',
    )
    original_teacher = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='substitutions_from',
    )
    substitute_teacher = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='substitutions_to',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'period__period_number']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'date', 'period', 'school_class', 'section', 'subject'],
                condition=Q(is_active=True),
                name='unique_active_substitution_slot',
            ),
            models.UniqueConstraint(
                fields=['school', 'session', 'date', 'period', 'substitute_teacher'],
                condition=Q(is_active=True),
                name='unique_substitute_teacher_per_period',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'date']),
        ]

    def clean(self):
        super().clean()

        if self.original_teacher_id and self.original_teacher.school_id != self.school_id:
            raise ValidationError({'original_teacher': 'Teacher must belong to selected school.'})
        if self.substitute_teacher_id and self.substitute_teacher.school_id != self.school_id:
            raise ValidationError({'substitute_teacher': 'Teacher must belong to selected school.'})

        if self.original_teacher_id and self.substitute_teacher_id and self.original_teacher_id == self.substitute_teacher_id:
            raise ValidationError({'substitute_teacher': 'Original and substitute teacher cannot be same.'})

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.section_id and self.section.school_class_id != self.school_class_id:
            raise ValidationError({'section': 'Section must belong to selected class.'})

        if self.subject_id and self.subject.school_id != self.school_id:
            raise ValidationError({'subject': 'Subject must belong to selected school.'})

        if self.school_class_id and self.subject_id and not ClassSubject.objects.filter(
            school_class=self.school_class,
            subject=self.subject,
        ).exists():
            raise ValidationError({'subject': 'Subject is not mapped to selected class.'})

        if self.period_id:
            if self.period.school_id != self.school_id:
                raise ValidationError({'period': 'Period must belong to selected school.'})
            if self.session_id and self.period.session_id != self.session_id:
                raise ValidationError({'period': 'Period must belong to selected session.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.date} P{self.period.period_number} - {self.substitute_teacher.employee_id}"


class SalaryStructure(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='salary_structures',
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='salary_structures',
    )
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.JSONField(default=dict, blank=True)
    deductions = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_from', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['staff'],
                condition=Q(is_active=True),
                name='unique_active_salary_structure_per_staff',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'staff', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.staff_id and self.staff.school_id != self.school_id:
            raise ValidationError({'staff': 'Staff must belong to selected school.'})

        if self.basic_salary <= 0:
            raise ValidationError({'basic_salary': 'Basic salary must be greater than zero.'})

        if not isinstance(self.allowances, dict):
            raise ValidationError({'allowances': 'Allowances must be a JSON object.'})

        if not isinstance(self.deductions, dict):
            raise ValidationError({'deductions': 'Deductions must be a JSON object.'})

    @property
    def net_salary(self):
        allowance_total = sum(Decimal(str(v)) for v in self.allowances.values())
        deduction_total = sum(Decimal(str(v)) for v in self.deductions.values())
        return self.basic_salary + allowance_total - deduction_total

    def __str__(self):
        return f"{self.staff.employee_id} - {self.basic_salary}"


class SalaryHistory(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='salary_histories',
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='salary_histories',
    )
    old_salary = models.DecimalField(max_digits=12, decimal_places=2)
    new_salary = models.DecimalField(max_digits=12, decimal_places=2)
    changed_on = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salary_changes_made',
    )
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-changed_on']
        indexes = [
            models.Index(fields=['school', 'staff', 'changed_on']),
        ]

    def clean(self):
        super().clean()

        if self.staff_id and self.staff.school_id != self.school_id:
            raise ValidationError({'staff': 'Staff must belong to selected school.'})

    def __str__(self):
        return f"{self.staff.employee_id}: {self.old_salary} -> {self.new_salary}"
