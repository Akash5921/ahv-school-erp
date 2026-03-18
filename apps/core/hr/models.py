from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


def _ensure_session_editable(session, message='This academic session is locked.'):
    if session and session.is_locked:
        raise ValidationError(message)


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
        if self.session_id:
            _ensure_session_editable(self.session)

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
        _ensure_session_editable(self.session)
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
        if self.session_id:
            _ensure_session_editable(self.session)

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
        _ensure_session_editable(self.session)
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
            _ensure_session_editable(self.session)
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
        if self.session_id:
            _ensure_session_editable(self.session)

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
        _ensure_session_editable(self.session)
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
    hra = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    da = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    transport_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    other_allowances = models.JSONField(default=dict, blank=True)
    pf_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    esi_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    professional_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    other_deductions = models.JSONField(default=dict, blank=True)
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

        non_negative_fields = [
            ('hra', self.hra),
            ('da', self.da),
            ('transport_allowance', self.transport_allowance),
            ('pf_deduction', self.pf_deduction),
            ('esi_deduction', self.esi_deduction),
            ('professional_tax', self.professional_tax),
        ]
        for field_name, value in non_negative_fields:
            if value < 0:
                raise ValidationError({field_name: 'Value cannot be negative.'})

        if not isinstance(self.other_allowances, dict):
            raise ValidationError({'other_allowances': 'Other allowances must be a JSON object.'})

        if not isinstance(self.other_deductions, dict):
            raise ValidationError({'other_deductions': 'Other deductions must be a JSON object.'})

        if self.pk:
            previous = SalaryStructure.objects.filter(pk=self.pk).first()
            if previous:
                immutable_fields = [
                    'school_id',
                    'staff_id',
                    'basic_salary',
                    'hra',
                    'da',
                    'transport_allowance',
                    'other_allowances',
                    'pf_deduction',
                    'esi_deduction',
                    'professional_tax',
                    'other_deductions',
                    'effective_from',
                ]
                if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
                    raise ValidationError('Salary structure records are immutable. Create a new effective record.')

    @property
    def allowance_total(self):
        other_allowance_sum = sum(Decimal(str(v)) for v in self.other_allowances.values())
        return self.basic_salary + self.hra + self.da + self.transport_allowance + other_allowance_sum

    @property
    def deduction_total(self):
        other_deduction_sum = sum(Decimal(str(v)) for v in self.other_deductions.values())
        return self.pf_deduction + self.esi_deduction + self.professional_tax + other_deduction_sum

    @property
    def net_salary(self):
        return self.allowance_total - self.deduction_total

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


class SalaryAdvance(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_ADJUSTED = 'adjusted'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_ADJUSTED, 'Adjusted'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='salary_advances',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='salary_advances',
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='salary_advances',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    request_date = models.DateField(default=timezone.localdate)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_salary_advances',
    )
    remaining_balance = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-request_date', '-id']
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='salary_advance_amount_gt_zero',
            ),
            models.CheckConstraint(
                condition=Q(remaining_balance__gte=0),
                name='salary_advance_remaining_non_negative',
            ),
            models.CheckConstraint(
                condition=Q(remaining_balance__lte=F('amount')),
                name='salary_advance_remaining_not_above_amount',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'staff', 'status'], name='core_hr_saladv_scope_idx'),
        ]

    def clean(self):
        super().clean()

        if self.staff_id and self.staff.school_id != self.school_id:
            raise ValidationError({'staff': 'Staff must belong to selected school.'})

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.session_id:
            _ensure_session_editable(self.session)

        if self.amount <= 0:
            raise ValidationError({'amount': 'Advance amount must be greater than zero.'})

        if self.remaining_balance < 0:
            raise ValidationError({'remaining_balance': 'Remaining balance cannot be negative.'})

        if self.remaining_balance > self.amount:
            raise ValidationError({'remaining_balance': 'Remaining balance cannot exceed amount.'})

        if self.status in {self.STATUS_APPROVED, self.STATUS_REJECTED, self.STATUS_ADJUSTED} and not self.approved_by_id:
            raise ValidationError({'approved_by': 'Approver is required for this status.'})

    def delete(self, *args, **kwargs):
        raise ValidationError('Salary advance records cannot be deleted.')

    def __str__(self):
        return f"{self.staff.employee_id} - {self.amount} ({self.status})"


class Payroll(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='payrolls',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='payrolls',
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='payrolls',
    )
    month = models.PositiveSmallIntegerField()
    year = models.PositiveIntegerField()
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2)
    attendance_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    leave_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    advance_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    total_working_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    present_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    absent_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    processed_on = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payrolls',
    )
    is_locked = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    paid_on = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paid_payrolls',
    )
    is_on_hold = models.BooleanField(default=False)
    hold_reason = models.CharField(max_length=255, blank=True)
    attendance_snapshot = models.JSONField(default=dict, blank=True)
    salary_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', '-month', 'staff__employee_id']
        constraints = [
            models.UniqueConstraint(
                fields=['staff', 'month', 'year'],
                name='unique_payroll_per_staff_month_year',
            ),
            models.CheckConstraint(
                condition=Q(month__gte=1) & Q(month__lte=12),
                name='payroll_month_range',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'year', 'month'], name='core_hr_payroll_period_idx'),
            models.Index(fields=['school', 'is_locked', 'is_paid'], name='core_hr_payroll_lock_paid_idx'),
        ]

    def clean(self):
        super().clean()

        if self.staff_id and self.staff.school_id != self.school_id:
            raise ValidationError({'staff': 'Staff must belong to selected school.'})

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.session_id:
            _ensure_session_editable(self.session)

        non_negative_fields = [
            ('gross_salary', self.gross_salary),
            ('attendance_deduction', self.attendance_deduction),
            ('leave_deduction', self.leave_deduction),
            ('advance_deduction', self.advance_deduction),
            ('total_deductions', self.total_deductions),
            ('net_salary', self.net_salary),
            ('total_working_days', self.total_working_days),
            ('present_days', self.present_days),
            ('absent_days', self.absent_days),
        ]
        for field_name, value in non_negative_fields:
            if value < 0:
                raise ValidationError({field_name: 'Value cannot be negative.'})

        if self.present_days > self.total_working_days:
            raise ValidationError({'present_days': 'Present days cannot exceed total working days.'})

        if self.absent_days > self.total_working_days:
            raise ValidationError({'absent_days': 'Absent days cannot exceed total working days.'})

        if self.total_deductions > self.gross_salary:
            raise ValidationError({'total_deductions': 'Total deductions cannot exceed gross salary.'})

        if self.is_paid and self.is_on_hold:
            raise ValidationError({'is_paid': 'Payroll on hold cannot be marked paid.'})

        if self.is_paid and not self.paid_on:
            raise ValidationError({'paid_on': 'Payment timestamp is required when marked paid.'})

        if self.is_on_hold and not self.hold_reason.strip():
            raise ValidationError({'hold_reason': 'Hold reason is required when payroll is on hold.'})

        if self.pk:
            previous = Payroll.objects.filter(pk=self.pk).first()
            if previous and previous.is_locked:
                protected_fields = [
                    'school_id',
                    'session_id',
                    'staff_id',
                    'month',
                    'year',
                    'gross_salary',
                    'attendance_deduction',
                    'leave_deduction',
                    'advance_deduction',
                    'total_deductions',
                    'net_salary',
                    'total_working_days',
                    'present_days',
                    'absent_days',
                    'attendance_snapshot',
                    'salary_snapshot',
                ]
                if any(getattr(previous, field) != getattr(self, field) for field in protected_fields):
                    raise ValidationError('Locked payroll cannot be edited.')

    def delete(self, *args, **kwargs):
        raise ValidationError('Payroll records cannot be deleted.')

    def __str__(self):
        return f"{self.staff.employee_id} - {self.month:02d}/{self.year}"


class PayrollAdvanceAdjustment(models.Model):
    payroll = models.ForeignKey(
        Payroll,
        on_delete=models.CASCADE,
        related_name='advance_adjustments',
    )
    salary_advance = models.ForeignKey(
        SalaryAdvance,
        on_delete=models.PROTECT,
        related_name='payroll_adjustments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['payroll', 'salary_advance'],
                name='unique_payroll_advance_adjustment',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='payroll_advance_adjustment_amount_gt_zero',
            ),
        ]

    def clean(self):
        super().clean()
        if self.payroll_id:
            _ensure_session_editable(self.payroll.session)

        if self.amount <= 0:
            raise ValidationError({'amount': 'Adjustment amount must be greater than zero.'})

        if self.salary_advance_id and self.payroll_id:
            if self.salary_advance.school_id != self.payroll.school_id:
                raise ValidationError({'salary_advance': 'Advance school mismatch with payroll.'})
            if self.salary_advance.staff_id != self.payroll.staff_id:
                raise ValidationError({'salary_advance': 'Advance staff mismatch with payroll.'})
            if self.salary_advance.session_id != self.payroll.session_id:
                raise ValidationError({'salary_advance': 'Advance session mismatch with payroll.'})

    def delete(self, *args, **kwargs):
        raise ValidationError('Payroll advance adjustment records cannot be deleted.')

    def __str__(self):
        return f"Payroll {self.payroll_id} - Advance {self.salary_advance_id}"
