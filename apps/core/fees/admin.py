from django.contrib import admin

from .models import (
    CarryForwardDue,
    ClassFeeStructure,
    FeePayment,
    FeePaymentAllocation,
    FeeReceipt,
    FeeRefund,
    FeeType,
    Installment,
    LedgerEntry,
    StudentConcession,
    StudentFee,
)


@admin.register(FeeType)
class FeeTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'school', 'is_active')
    list_filter = ('school', 'category', 'is_active')
    search_fields = ('name',)


@admin.register(ClassFeeStructure)
class ClassFeeStructureAdmin(admin.ModelAdmin):
    list_display = ('school_class', 'fee_type', 'amount', 'session', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('school_class__name', 'fee_type__name')


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'session', 'due_date', 'fine_per_day', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('name',)


@admin.register(StudentFee)
class StudentFeeAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'fee_type',
        'session',
        'total_amount',
        'concession_amount',
        'final_amount',
        'is_carry_forward',
        'is_active',
    )
    list_filter = ('school', 'session', 'is_active', 'is_carry_forward')
    search_fields = ('student__admission_number', 'student__first_name', 'fee_type__name')


@admin.register(StudentConcession)
class StudentConcessionAdmin(admin.ModelAdmin):
    list_display = ('student', 'fee_type', 'percentage', 'fixed_amount', 'approved_by', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('student__admission_number', 'reason')


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'student',
        'session',
        'installment',
        'amount_paid',
        'fine_amount',
        'payment_date',
        'payment_mode',
        'is_reversed',
    )
    list_filter = ('school', 'session', 'payment_mode', 'is_reversed')
    search_fields = ('student__admission_number', 'reference_number')


@admin.register(FeePaymentAllocation)
class FeePaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ('payment', 'student_fee', 'carry_forward_due', 'amount')
    list_filter = ('payment__school', 'payment__session')


@admin.register(FeeReceipt)
class FeeReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'student', 'payment', 'session', 'is_cancelled', 'generated_at')
    list_filter = ('school', 'session', 'is_cancelled')
    search_fields = ('receipt_number', 'student__admission_number')


@admin.register(FeeRefund)
class FeeRefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'payment', 'refund_amount', 'refund_date', 'is_reversed')
    list_filter = ('school', 'session', 'is_reversed')
    search_fields = ('student__admission_number', 'reason')


@admin.register(CarryForwardDue)
class CarryForwardDueAdmin(admin.ModelAdmin):
    list_display = ('student', 'from_session', 'to_session', 'amount', 'settled_amount', 'is_active')
    list_filter = ('school', 'from_session', 'to_session', 'is_active')
    search_fields = ('student__admission_number',)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('date', 'transaction_type', 'amount', 'reference_model', 'reference_id', 'is_reversed')
    list_filter = ('school', 'session', 'transaction_type', 'is_reversed')
    search_fields = ('reference_model', 'reference_id', 'description')
