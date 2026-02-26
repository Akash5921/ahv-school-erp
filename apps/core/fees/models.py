
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.utils.managers import SchoolManager


class FinancialRecordModel(models.Model):
    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError('Financial records cannot be deleted. Use reversal workflow.')


class FeeType(models.Model):
    CATEGORY_ACADEMIC = 'academic'
    CATEGORY_TRANSPORT = 'transport'
    CATEGORY_OTHER = 'other'
    CATEGORY_CHOICES = (
        (CATEGORY_ACADEMIC, 'Academic'),
        (CATEGORY_TRANSPORT, 'Transport'),
        (CATEGORY_OTHER, 'Other'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='fee_types_core',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_ACADEMIC)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                name='unique_fee_type_name_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'category', 'is_active']),
        ]

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({'name': 'Fee type name is required.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.name} ({self.school.code})"


class ClassFeeStructure(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='class_fee_structures',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='class_fee_structures',
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='fee_structures',
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        related_name='class_fee_structures',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['school_class__display_order', 'fee_type__name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school_class', 'fee_type', 'session'],
                name='unique_class_fee_type_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
            models.Index(fields=['school', 'session', 'school_class']),
        ]

    def clean(self):
        super().clean()
        if self.amount is None or self.amount < 0:
            raise ValidationError({'amount': 'Amount must be zero or greater.'})

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.school_class_id:
            if self.school_class.school_id != self.school_id:
                raise ValidationError({'school_class': 'Class must belong to selected school.'})
            if self.session_id and self.school_class.session_id != self.session_id:
                raise ValidationError({'school_class': 'Class must belong to selected session.'})

        if self.fee_type_id and self.fee_type.school_id != self.school_id:
            raise ValidationError({'fee_type': 'Fee type must belong to selected school.'})

        if not self.pk:
            return

        previous = ClassFeeStructure.objects.filter(pk=self.pk).first()
        if not previous:
            return

        students_assigned = StudentSessionRecord.objects.filter(
            school=previous.school,
            session=previous.session,
            school_class=previous.school_class,
            student__is_archived=False,
        ).exists()
        if not students_assigned:
            return

        protected_fields = [
            'school_id',
            'session_id',
            'school_class_id',
            'fee_type_id',
            'amount',
        ]
        if any(getattr(previous, field) != getattr(self, field) for field in protected_fields):
            raise ValidationError('Fee structure cannot be edited after students are assigned for this class-session.')

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.school_class.name} - {self.fee_type.name} ({self.session.name})"

class Installment(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='fee_installments',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='fee_installments',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=100)
    due_date = models.DateField()
    fine_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    split_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'name'],
                name='unique_installment_name_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'due_date', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({'name': 'Installment name is required.'})

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.fine_per_day is None or self.fine_per_day < 0:
            raise ValidationError({'fine_per_day': 'Fine per day cannot be negative.'})

        if self.split_percentage is not None:
            if self.split_percentage <= 0 or self.split_percentage > 100:
                raise ValidationError({'split_percentage': 'Split percentage must be between 0 and 100.'})

        if self.fixed_amount is not None and self.fixed_amount < 0:
            raise ValidationError({'fixed_amount': 'Fixed amount cannot be negative.'})

        if self.split_percentage is not None and self.fixed_amount is not None:
            raise ValidationError('Use either split percentage or fixed amount, not both.')

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.name} ({self.session.name})"


class StudentFee(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_fees_core',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_fees_core',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='student_fees',
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        related_name='student_fees',
    )
    assigned_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_fees',
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    concession_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    final_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_carry_forward = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['student__admission_number', 'fee_type__name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'student', 'fee_type', 'is_carry_forward'],
                name='unique_student_fee_type_per_session_scope',
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0) & Q(concession_amount__gte=0) & Q(final_amount__gte=0),
                name='student_fee_non_negative_amounts',
            ),
            models.CheckConstraint(
                condition=Q(concession_amount__lte=F('total_amount')),
                name='student_fee_concession_not_above_total',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'student', 'is_active']),
            models.Index(fields=['school', 'session', 'fee_type']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})

        if self.fee_type_id and self.fee_type.school_id != self.school_id:
            raise ValidationError({'fee_type': 'Fee type must belong to selected school.'})

        if self.assigned_class_id:
            if self.assigned_class.school_id != self.school_id:
                raise ValidationError({'assigned_class': 'Assigned class must belong to selected school.'})
            if self.assigned_class.session_id != self.session_id:
                raise ValidationError({'assigned_class': 'Assigned class must belong to selected session.'})

        if self.total_amount is None or self.total_amount < 0:
            raise ValidationError({'total_amount': 'Total amount cannot be negative.'})
        if self.concession_amount is None or self.concession_amount < 0:
            raise ValidationError({'concession_amount': 'Concession amount cannot be negative.'})
        if self.concession_amount > self.total_amount:
            raise ValidationError({'concession_amount': 'Concession amount cannot exceed total amount.'})

    def save(self, *args, **kwargs):
        final_amount = Decimal(self.total_amount) - Decimal(self.concession_amount)
        if final_amount < 0:
            final_amount = Decimal('0.00')
        self.final_amount = final_amount
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.student.admission_number} - {self.fee_type.name} ({self.session.name})"

class StudentConcession(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_concessions',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_concessions',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='concessions',
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='student_concessions',
    )
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_student_concessions',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'session', 'student', 'is_active']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})

        if self.fee_type_id and self.fee_type.school_id != self.school_id:
            raise ValidationError({'fee_type': 'Fee type must belong to selected school.'})

        has_percentage = self.percentage is not None
        has_fixed = self.fixed_amount is not None
        if has_percentage == has_fixed:
            raise ValidationError('Provide either percentage or fixed amount.')

        if has_percentage and (self.percentage <= 0 or self.percentage > 100):
            raise ValidationError({'percentage': 'Percentage must be between 0 and 100.'})
        if has_fixed and self.fixed_amount <= 0:
            raise ValidationError({'fixed_amount': 'Fixed amount must be greater than zero.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])

    def __str__(self):
        target = self.fee_type.name if self.fee_type_id else 'All Fee Types'
        return f"{self.student.admission_number} - {target}"


class CarryForwardDue(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='carry_forward_dues',
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='carry_forward_dues',
    )
    from_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.PROTECT,
        related_name='carry_forward_from_session',
    )
    to_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.PROTECT,
        related_name='carry_forward_to_session',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    settled_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'from_session', 'to_session'],
                name='unique_carry_forward_due_per_transition',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0) & Q(settled_amount__gte=0),
                name='carry_forward_due_positive_values',
            ),
            models.CheckConstraint(
                condition=Q(settled_amount__lte=F('amount')),
                name='carry_forward_settled_not_above_amount',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'to_session', 'is_active']),
            models.Index(fields=['school', 'student', 'is_active']),
        ]

    @property
    def outstanding_amount(self):
        amount = Decimal(self.amount) - Decimal(self.settled_amount)
        return amount if amount > 0 else Decimal('0.00')

    def clean(self):
        super().clean()

        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError({'student': 'Student must belong to selected school.'})

        if self.from_session_id and self.from_session.school_id != self.school_id:
            raise ValidationError({'from_session': 'From session must belong to selected school.'})

        if self.to_session_id and self.to_session.school_id != self.school_id:
            raise ValidationError({'to_session': 'To session must belong to selected school.'})

        if self.from_session_id and self.to_session_id and self.from_session_id == self.to_session_id:
            raise ValidationError('From session and to session must be different.')

        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': 'Carry forward amount must be greater than zero.'})

        if self.settled_amount is None or self.settled_amount < 0:
            raise ValidationError({'settled_amount': 'Settled amount cannot be negative.'})

        if self.settled_amount > self.amount:
            raise ValidationError({'settled_amount': 'Settled amount cannot exceed total carry forward amount.'})

    def delete(self, *args, **kwargs):
        raise ValidationError('Carry forward dues cannot be deleted.')

    def __str__(self):
        return f"{self.student.admission_number}: {self.from_session.name} -> {self.to_session.name}"

class FeePayment(FinancialRecordModel):
    MODE_CASH = 'cash'
    MODE_ONLINE = 'online'
    MODE_CHEQUE = 'cheque'
    MODE_UPI = 'upi'
    MODE_CARD = 'card'
    PAYMENT_MODE_CHOICES = (
        (MODE_CASH, 'Cash'),
        (MODE_ONLINE, 'Online'),
        (MODE_CHEQUE, 'Cheque'),
        (MODE_UPI, 'UPI'),
        (MODE_CARD, 'Card'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='fee_payments',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='fee_payments',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='fee_payments',
    )
    installment = models.ForeignKey(
        Installment,
        on_delete=models.PROTECT,
        related_name='fee_payments',
    )
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    fine_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_date = models.DateField(default=timezone.localdate)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES, default=MODE_CASH)
    reference_number = models.CharField(max_length=120, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_fee_payments',
    )
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_fee_payments',
    )
    reversal_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-id']
        indexes = [
            models.Index(fields=['school', 'session', 'student', 'payment_date']),
            models.Index(fields=['school', 'session', 'installment']),
            models.Index(fields=['school', 'is_reversed']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})

        if self.installment_id:
            if self.installment.school_id != self.school_id:
                raise ValidationError({'installment': 'Installment must belong to selected school.'})
            if self.installment.session_id != self.session_id:
                raise ValidationError({'installment': 'Installment must belong to selected session.'})

        if self.amount_paid is None or self.amount_paid <= 0:
            raise ValidationError({'amount_paid': 'Payment amount must be greater than zero.'})

        if self.fine_amount is None or self.fine_amount < 0:
            raise ValidationError({'fine_amount': 'Fine amount cannot be negative.'})

        if self.is_reversed:
            if not self.reversed_at:
                raise ValidationError({'reversed_at': 'Reversal timestamp is required for reversed payment.'})
            if not self.reversed_by_id:
                raise ValidationError({'reversed_by': 'Reversal actor is required for reversed payment.'})
            if not self.reversal_reason.strip():
                raise ValidationError({'reversal_reason': 'Reversal reason is required.'})

        if not self.pk:
            return

        previous = FeePayment.objects.filter(pk=self.pk).first()
        if not previous:
            return

        immutable_fields = [
            'school_id',
            'session_id',
            'student_id',
            'installment_id',
            'amount_paid',
            'fine_amount',
            'payment_date',
            'payment_mode',
            'reference_number',
            'received_by_id',
        ]
        if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
            raise ValidationError('Fee payments are immutable. Reverse and re-enter instead of editing.')

        if previous.is_reversed and not self.is_reversed:
            raise ValidationError('Reversed payment cannot be reverted.')

    @property
    def total_collected(self):
        return Decimal(self.amount_paid) + Decimal(self.fine_amount)

    def __str__(self):
        return f"Payment #{self.id} - {self.student.admission_number}"


class FeePaymentAllocation(FinancialRecordModel):
    payment = models.ForeignKey(
        FeePayment,
        on_delete=models.CASCADE,
        related_name='allocations',
    )
    student_fee = models.ForeignKey(
        StudentFee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment_allocations',
    )
    carry_forward_due = models.ForeignKey(
        CarryForwardDue,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment_allocations',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(student_fee__isnull=False) & Q(carry_forward_due__isnull=True))
                    | (Q(student_fee__isnull=True) & Q(carry_forward_due__isnull=False))
                ),
                name='fee_allocation_exactly_one_target',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='fee_allocation_amount_positive',
            ),
        ]

    def clean(self):
        super().clean()

        has_student_fee = self.student_fee_id is not None
        has_carry_due = self.carry_forward_due_id is not None
        if has_student_fee == has_carry_due:
            raise ValidationError('Allocation must target either student fee or carry forward due.')

        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': 'Allocation amount must be greater than zero.'})

        if self.student_fee_id:
            if self.student_fee.school_id != self.payment.school_id:
                raise ValidationError({'student_fee': 'Student fee must belong to payment school.'})
            if self.student_fee.session_id != self.payment.session_id:
                raise ValidationError({'student_fee': 'Student fee must belong to payment session.'})
            if self.student_fee.student_id != self.payment.student_id:
                raise ValidationError({'student_fee': 'Student fee must belong to payment student.'})

        if self.carry_forward_due_id:
            if self.carry_forward_due.school_id != self.payment.school_id:
                raise ValidationError({'carry_forward_due': 'Carry forward due must belong to payment school.'})
            if self.carry_forward_due.to_session_id != self.payment.session_id:
                raise ValidationError({'carry_forward_due': 'Carry forward due must belong to payment session.'})
            if self.carry_forward_due.student_id != self.payment.student_id:
                raise ValidationError({'carry_forward_due': 'Carry forward due must belong to payment student.'})

    def __str__(self):
        return f"Allocation #{self.id} - Payment #{self.payment_id}"

class FeeReceipt(FinancialRecordModel):
    receipt_number = models.CharField(max_length=50, unique=True)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='fee_receipts',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='fee_receipts',
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='fee_receipts',
    )
    payment = models.OneToOneField(
        FeePayment,
        on_delete=models.PROTECT,
        related_name='receipt',
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    is_cancelled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['school', 'session', 'generated_at']),
            models.Index(fields=['school', 'receipt_number']),
        ]

    def clean(self):
        super().clean()

        if self.payment_id:
            if self.payment.school_id != self.school_id:
                raise ValidationError({'payment': 'Payment school mismatch.'})
            if self.payment.session_id != self.session_id:
                raise ValidationError({'payment': 'Payment session mismatch.'})
            if self.payment.student_id != self.student_id:
                raise ValidationError({'payment': 'Payment student mismatch.'})

    def __str__(self):
        return self.receipt_number


class FeeRefund(FinancialRecordModel):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='fee_refunds',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='fee_refunds',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='fee_refunds',
    )
    payment = models.ForeignKey(
        FeePayment,
        on_delete=models.PROTECT,
        related_name='refunds',
    )
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_fee_refunds',
    )
    refund_date = models.DateField(default=timezone.localdate)
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_fee_refunds',
    )
    reversal_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-refund_date', '-id']
        indexes = [
            models.Index(fields=['school', 'session', 'student', 'refund_date']),
            models.Index(fields=['school', 'is_reversed']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})

        if self.payment_id:
            if self.payment.school_id != self.school_id:
                raise ValidationError({'payment': 'Payment school mismatch.'})
            if self.payment.session_id != self.session_id:
                raise ValidationError({'payment': 'Payment session mismatch.'})
            if self.payment.student_id != self.student_id:
                raise ValidationError({'payment': 'Payment student mismatch.'})

        if self.refund_amount is None or self.refund_amount <= 0:
            raise ValidationError({'refund_amount': 'Refund amount must be greater than zero.'})

        if not self.reason.strip():
            raise ValidationError({'reason': 'Refund reason is required.'})

        if self.is_reversed:
            if not self.reversed_at:
                raise ValidationError({'reversed_at': 'Reversal timestamp is required.'})
            if not self.reversed_by_id:
                raise ValidationError({'reversed_by': 'Reversal actor is required.'})
            if not self.reversal_reason.strip():
                raise ValidationError({'reversal_reason': 'Reversal reason is required.'})

        if not self.pk:
            return

        previous = FeeRefund.objects.filter(pk=self.pk).first()
        if not previous:
            return

        immutable_fields = [
            'school_id',
            'session_id',
            'student_id',
            'payment_id',
            'refund_amount',
            'reason',
            'approved_by_id',
            'refund_date',
        ]
        if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
            raise ValidationError('Fee refunds are immutable. Reverse and re-enter instead of editing.')

        if previous.is_reversed and not self.is_reversed:
            raise ValidationError('Reversed refund cannot be reverted.')

    def __str__(self):
        return f"Refund #{self.id} - Payment #{self.payment_id}"

class LedgerEntry(FinancialRecordModel):
    TYPE_INCOME = 'income'
    TYPE_EXPENSE = 'expense'
    TYPE_REFUND = 'refund'
    TYPE_REVERSAL = 'reversal'
    TRANSACTION_TYPE_CHOICES = (
        (TYPE_INCOME, 'Income'),
        (TYPE_EXPENSE, 'Expense'),
        (TYPE_REFUND, 'Refund'),
        (TYPE_REVERSAL, 'Reversal'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='ledger_entries_core',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='ledger_entries_core',
    )
    objects = SchoolManager()

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    reference_model = models.CharField(max_length=100)
    reference_id = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255, blank=True)
    related_entry = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversal_entries',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ledger_entries_created',
    )
    is_reversed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'transaction_type', 'reference_model', 'reference_id'],
                name='unique_ledger_entry_per_reference',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='ledger_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'date']),
            models.Index(fields=['school', 'session', 'transaction_type']),
        ]

    def clean(self):
        super().clean()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if not self.reference_model:
            raise ValidationError({'reference_model': 'Reference model is required.'})
        if not self.reference_id:
            raise ValidationError({'reference_id': 'Reference id is required.'})

        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': 'Ledger amount must be greater than zero.'})

    def __str__(self):
        return f"{self.transaction_type} {self.amount} ({self.reference_model}:{self.reference_id})"
