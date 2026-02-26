
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PIL import Image, ImageDraw
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.students.models import Student, image_to_pdf_bytes

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


def _to_decimal(value) -> Decimal:
    return Decimal(str(value or '0'))


def _quantize(value: Decimal) -> Decimal:
    return _to_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _sum_amount(queryset, field_name='amount') -> Decimal:
    value = queryset.aggregate(total=Sum(field_name)).get('total')
    return _to_decimal(value)


def _carry_forward_fee_type(school):
    fee_type, _ = FeeType.objects.get_or_create(
        school=school,
        name='Carry Forward Due',
        defaults={
            'category': FeeType.CATEGORY_OTHER,
            'is_active': True,
        },
    )
    if not fee_type.is_active:
        fee_type.is_active = True
        fee_type.save(update_fields=['is_active'])
    return fee_type


@transaction.atomic
def recalculate_student_fee_concessions(*, student: Student, session: AcademicSession):
    fees = list(
        StudentFee.objects.filter(
            school=student.school,
            session=session,
            student=student,
            is_active=True,
            is_carry_forward=False,
        ).order_by('fee_type__name', 'id')
    )
    if not fees:
        return []

    concessions = list(
        StudentConcession.objects.filter(
            school=student.school,
            session=session,
            student=student,
            is_active=True,
        ).select_related('fee_type').order_by('id')
    )

    discount_map = {fee.id: Decimal('0.00') for fee in fees}

    for concession in concessions:
        if concession.fee_type_id:
            targets = [fee for fee in fees if fee.fee_type_id == concession.fee_type_id]
        else:
            targets = list(fees)

        if not targets:
            continue

        if concession.percentage is not None:
            rate = _to_decimal(concession.percentage) / Decimal('100')
            for fee in targets:
                discount_map[fee.id] += _quantize(_to_decimal(fee.total_amount) * rate)
            continue

        fixed_amount = _to_decimal(concession.fixed_amount)
        if concession.fee_type_id:
            discount_map[targets[0].id] += fixed_amount
            continue

        base_total = sum((_to_decimal(fee.total_amount) for fee in targets), Decimal('0.00'))
        if base_total <= 0:
            continue

        remaining = fixed_amount
        for index, fee in enumerate(targets, start=1):
            if index == len(targets):
                allocation = remaining
            else:
                allocation = _quantize((_to_decimal(fee.total_amount) / base_total) * fixed_amount)
                remaining -= allocation
            discount_map[fee.id] += allocation

    updated = []
    for fee in fees:
        total = _to_decimal(fee.total_amount)
        concession_value = discount_map.get(fee.id, Decimal('0.00'))
        if concession_value > total:
            concession_value = total
        if concession_value < 0:
            concession_value = Decimal('0.00')

        concession_value = _quantize(concession_value)
        final_value = _quantize(total - concession_value)

        if fee.concession_amount != concession_value or fee.final_amount != final_value:
            fee.concession_amount = concession_value
            fee.final_amount = final_value
            fee.save(update_fields=['concession_amount', 'final_amount', 'updated_at'])
        updated.append(fee)

    return updated


@transaction.atomic
def sync_student_fees_for_student(*, student: Student, previous_session: AcademicSession | None = None):
    if not (student.school_id and student.session_id):
        return []

    if not student.current_class_id:
        StudentFee.objects.filter(
            school=student.school,
            session=student.session,
            student=student,
            is_carry_forward=False,
        ).update(is_active=False)
        return []

    mappings = list(
        ClassFeeStructure.objects.filter(
            school=student.school,
            session=student.session,
            school_class=student.current_class,
            is_active=True,
            fee_type__is_active=True,
        ).select_related('fee_type')
    )

    active_fee_type_ids = []
    for mapping in mappings:
        active_fee_type_ids.append(mapping.fee_type_id)
        student_fee, created = StudentFee.objects.get_or_create(
            school=student.school,
            session=student.session,
            student=student,
            fee_type=mapping.fee_type,
            is_carry_forward=False,
            defaults={
                'assigned_class': student.current_class,
                'total_amount': _quantize(mapping.amount),
                'concession_amount': Decimal('0.00'),
                'final_amount': _quantize(mapping.amount),
                'is_active': True,
            },
        )

        if not created:
            updates = []
            mapping_amount = _quantize(mapping.amount)
            if student_fee.assigned_class_id != student.current_class_id:
                student_fee.assigned_class = student.current_class
                updates.append('assigned_class')
            if student_fee.total_amount != mapping_amount:
                student_fee.total_amount = mapping_amount
                updates.append('total_amount')
            if not student_fee.is_active:
                student_fee.is_active = True
                updates.append('is_active')
            if updates:
                student_fee.save(update_fields=updates + ['updated_at'])

    stale_rows = StudentFee.objects.filter(
        school=student.school,
        session=student.session,
        student=student,
        is_active=True,
        is_carry_forward=False,
    ).exclude(fee_type_id__in=active_fee_type_ids)
    if stale_rows.exists():
        stale_rows.update(is_active=False)

    recalculate_student_fee_concessions(student=student, session=student.session)

    if previous_session and previous_session.id != student.session_id:
        try:
            generate_carry_forward_due(
                student=student,
                from_session=previous_session,
                to_session=student.session,
            )
        except ValidationError:
            pass

    return list(
        StudentFee.objects.filter(
            school=student.school,
            session=student.session,
            student=student,
            is_active=True,
        ).select_related('fee_type').order_by('-is_carry_forward', 'fee_type__name')
    )


def _fee_due_amount(student_fee: StudentFee) -> Decimal:
    allocated = _sum_amount(
        FeePaymentAllocation.objects.filter(
            student_fee=student_fee,
            payment__is_reversed=False,
        ),
        field_name='amount',
    )
    due = _to_decimal(student_fee.final_amount) - allocated
    return due if due > 0 else Decimal('0.00')


def principal_outstanding(*, student: Student, session: AcademicSession) -> Decimal:
    fee_rows = StudentFee.objects.filter(
        school=student.school,
        session=session,
        student=student,
        is_active=True,
    )
    total_due = _sum_amount(fee_rows, field_name='final_amount')
    total_paid = _sum_amount(
        FeePaymentAllocation.objects.filter(
            student_fee__in=fee_rows,
            payment__is_reversed=False,
        ),
        field_name='amount',
    )
    balance = _quantize(total_due - total_paid)
    return balance if balance > 0 else Decimal('0.00')


def fine_due_for_installment(
    *,
    student: Student,
    session: AcademicSession,
    installment: Installment,
    as_of_date=None,
) -> Decimal:
    as_of_date = as_of_date or timezone.localdate()
    if as_of_date <= installment.due_date:
        return Decimal('0.00')

    if installment.school_id != student.school_id or installment.session_id != session.id:
        raise ValidationError('Installment does not belong to selected school-session scope.')

    days_late = (as_of_date - installment.due_date).days
    accrued = _quantize(_to_decimal(days_late) * _to_decimal(installment.fine_per_day))

    collected = _sum_amount(
        FeePayment.objects.filter(
            school=student.school,
            session=session,
            student=student,
            installment=installment,
            is_reversed=False,
        ),
        field_name='fine_amount',
    )
    pending = _quantize(accrued - collected)
    return pending if pending > 0 else Decimal('0.00')


def total_pending_fine(*, student: Student, session: AcademicSession, as_of_date=None) -> Decimal:
    as_of_date = as_of_date or timezone.localdate()
    installments = Installment.objects.filter(
        school=student.school,
        session=session,
        is_active=True,
        due_date__lt=as_of_date,
    ).order_by('due_date', 'id')

    total = Decimal('0.00')
    for installment in installments:
        total += fine_due_for_installment(
            student=student,
            session=session,
            installment=installment,
            as_of_date=as_of_date,
        )
    return _quantize(total)


def student_outstanding_summary(*, student: Student, session: AcademicSession, as_of_date=None):
    principal_due = principal_outstanding(student=student, session=session)
    fine_due = total_pending_fine(student=student, session=session, as_of_date=as_of_date)
    return {
        'principal_due': principal_due,
        'fine_due': fine_due,
        'total_due': _quantize(principal_due + fine_due),
    }


def _receipt_number(payment: FeePayment) -> str:
    date_part = payment.payment_date.strftime('%Y%m%d')
    return f"RCP-{payment.school_id}-{payment.session_id}-{date_part}-{payment.id:06d}"


def _ledger_create(*, school, session, transaction_type, reference_model, reference_id, amount, date, created_by=None, description='', related_entry=None):
    entry, _ = LedgerEntry.objects.get_or_create(
        school=school,
        transaction_type=transaction_type,
        reference_model=reference_model,
        reference_id=str(reference_id),
        defaults={
            'session': session,
            'amount': _quantize(amount),
            'date': date,
            'description': description[:255],
            'created_by': created_by,
            'related_entry': related_entry,
        },
    )
    return entry


@transaction.atomic
def collect_fee_payment(
    *,
    school,
    session: AcademicSession,
    student: Student,
    installment: Installment,
    amount_paid,
    payment_mode,
    received_by,
    payment_date=None,
    reference_number='',
):
    payment_date = payment_date or timezone.localdate()

    if session.school_id != school.id:
        raise ValidationError('Session does not belong to selected school.')
    if student.school_id != school.id or student.session_id != session.id:
        raise ValidationError('Student does not belong to selected school-session.')
    if installment.school_id != school.id or installment.session_id != session.id:
        raise ValidationError('Installment does not belong to selected school-session.')

    principal_amount = _quantize(_to_decimal(amount_paid))
    if principal_amount <= 0:
        raise ValidationError('Payment amount must be greater than zero.')

    summary = student_outstanding_summary(student=student, session=session, as_of_date=payment_date)
    if principal_amount > summary['principal_due']:
        raise ValidationError(f"Payment exceeds outstanding principal amount ({summary['principal_due']}).")

    fine_amount = fine_due_for_installment(
        student=student,
        session=session,
        installment=installment,
        as_of_date=payment_date,
    )

    payment = FeePayment.objects.create(
        school=school,
        session=session,
        student=student,
        installment=installment,
        amount_paid=principal_amount,
        fine_amount=fine_amount,
        payment_date=payment_date,
        payment_mode=payment_mode,
        reference_number=(reference_number or '')[:120],
        received_by=received_by,
    )

    remaining = principal_amount
    due_rows = list(
        StudentFee.objects.filter(
            school=school,
            session=session,
            student=student,
            is_active=True,
        ).order_by('-is_carry_forward', 'fee_type__name', 'id')
    )

    for fee_row in due_rows:
        if remaining <= 0:
            break

        due_amount = _fee_due_amount(fee_row)
        if due_amount <= 0:
            continue

        allocation = due_amount if due_amount <= remaining else remaining
        allocation = _quantize(allocation)
        FeePaymentAllocation.objects.create(
            payment=payment,
            student_fee=fee_row,
            amount=allocation,
        )
        remaining = _quantize(remaining - allocation)

    if remaining > 0:
        raise ValidationError('Could not allocate full payment amount to outstanding fee items.')

    receipt = FeeReceipt.objects.create(
        receipt_number=_receipt_number(payment),
        school=school,
        session=session,
        student=student,
        payment=payment,
    )

    ledger_entry = _ledger_create(
        school=school,
        session=session,
        transaction_type=LedgerEntry.TYPE_INCOME,
        reference_model='FeePayment',
        reference_id=payment.id,
        amount=payment.total_collected,
        date=payment.payment_date,
        created_by=received_by,
        description=f"Fee collected from {student.admission_number} via {payment.get_payment_mode_display()}",
    )

    return {
        'payment': payment,
        'receipt': receipt,
        'ledger_entry': ledger_entry,
    }


@transaction.atomic
def reverse_fee_payment(*, payment: FeePayment, reversed_by, reason: str):
    if payment.is_reversed:
        raise ValidationError('Payment is already reversed.')

    reversal_reason = (reason or '').strip()
    if not reversal_reason:
        raise ValidationError('Reversal reason is required.')

    payment.is_reversed = True
    payment.reversed_at = timezone.now()
    payment.reversed_by = reversed_by
    payment.reversal_reason = reversal_reason[:255]
    payment.full_clean()
    payment.save(update_fields=['is_reversed', 'reversed_at', 'reversed_by', 'reversal_reason'])

    if hasattr(payment, 'receipt') and payment.receipt:
        receipt = payment.receipt
        if not receipt.is_cancelled:
            receipt.is_cancelled = True
            receipt.save(update_fields=['is_cancelled'])

    source_ledger = LedgerEntry.objects.filter(
        school=payment.school,
        transaction_type=LedgerEntry.TYPE_INCOME,
        reference_model='FeePayment',
        reference_id=str(payment.id),
    ).first()
    if source_ledger and not source_ledger.is_reversed:
        source_ledger.is_reversed = True
        source_ledger.save(update_fields=['is_reversed'])

    reversal_ledger = _ledger_create(
        school=payment.school,
        session=payment.session,
        transaction_type=LedgerEntry.TYPE_REVERSAL,
        reference_model='FeePayment',
        reference_id=payment.id,
        amount=payment.total_collected,
        date=timezone.localdate(),
        created_by=reversed_by,
        description=f"Payment reversal for receipt {payment.receipt.receipt_number if hasattr(payment, 'receipt') else payment.id}",
        related_entry=source_ledger,
    )

    return {
        'payment': payment,
        'reversal_ledger': reversal_ledger,
    }


@transaction.atomic
def create_fee_refund(*, payment: FeePayment, refund_amount, reason, approved_by, refund_date=None):
    if payment.is_reversed:
        raise ValidationError('Cannot refund a reversed payment.')

    reason = (reason or '').strip()
    if not reason:
        raise ValidationError('Refund reason is required.')

    refund_amount = _quantize(_to_decimal(refund_amount))
    if refund_amount <= 0:
        raise ValidationError('Refund amount must be greater than zero.')

    refunded_total = _sum_amount(
        FeeRefund.objects.filter(
            payment=payment,
            is_reversed=False,
        ),
        field_name='refund_amount',
    )

    refundable = _quantize(payment.total_collected - refunded_total)
    if refund_amount > refundable:
        raise ValidationError(f"Refund exceeds refundable balance ({refundable}).")

    refund = FeeRefund.objects.create(
        school=payment.school,
        session=payment.session,
        student=payment.student,
        payment=payment,
        refund_amount=refund_amount,
        reason=reason[:255],
        approved_by=approved_by,
        refund_date=refund_date or timezone.localdate(),
    )

    ledger_entry = _ledger_create(
        school=payment.school,
        session=payment.session,
        transaction_type=LedgerEntry.TYPE_REFUND,
        reference_model='FeeRefund',
        reference_id=refund.id,
        amount=refund.refund_amount,
        date=refund.refund_date,
        created_by=approved_by,
        description=f"Refund for payment #{payment.id}",
    )

    return {
        'refund': refund,
        'ledger_entry': ledger_entry,
    }


@transaction.atomic
def reverse_fee_refund(*, refund: FeeRefund, reversed_by, reason: str):
    if refund.is_reversed:
        raise ValidationError('Refund is already reversed.')

    reason = (reason or '').strip()
    if not reason:
        raise ValidationError('Reversal reason is required.')

    refund.is_reversed = True
    refund.reversed_at = timezone.now()
    refund.reversed_by = reversed_by
    refund.reversal_reason = reason[:255]
    refund.full_clean()
    refund.save(update_fields=['is_reversed', 'reversed_at', 'reversed_by', 'reversal_reason'])

    source_ledger = LedgerEntry.objects.filter(
        school=refund.school,
        transaction_type=LedgerEntry.TYPE_REFUND,
        reference_model='FeeRefund',
        reference_id=str(refund.id),
    ).first()
    if source_ledger and not source_ledger.is_reversed:
        source_ledger.is_reversed = True
        source_ledger.save(update_fields=['is_reversed'])

    reversal_ledger = _ledger_create(
        school=refund.school,
        session=refund.session,
        transaction_type=LedgerEntry.TYPE_REVERSAL,
        reference_model='FeeRefund',
        reference_id=refund.id,
        amount=refund.refund_amount,
        date=timezone.localdate(),
        created_by=reversed_by,
        description=f"Refund reversal for refund #{refund.id}",
        related_entry=source_ledger,
    )

    return {
        'refund': refund,
        'reversal_ledger': reversal_ledger,
    }


@transaction.atomic
def generate_carry_forward_due(*, student: Student, from_session: AcademicSession, to_session: AcademicSession):
    if student.school_id != from_session.school_id or student.school_id != to_session.school_id:
        raise ValidationError('Carry forward sessions must belong to student school.')

    if from_session.id == to_session.id:
        raise ValidationError('From session and to session must be different.')

    if student.session_id != to_session.id:
        raise ValidationError('Student must be assigned to target session before carry forward.')

    summary = student_outstanding_summary(
        student=student,
        session=from_session,
        as_of_date=from_session.end_date,
    )
    carry_amount = _quantize(summary['principal_due'] + summary['fine_due'])
    if carry_amount <= 0:
        raise ValidationError('No outstanding dues found to carry forward.')

    due, _ = CarryForwardDue.objects.update_or_create(
        school=student.school,
        student=student,
        from_session=from_session,
        to_session=to_session,
        defaults={
            'amount': carry_amount,
            'is_active': True,
        },
    )

    fee_type = _carry_forward_fee_type(student.school)
    student_fee, _ = StudentFee.objects.update_or_create(
        school=student.school,
        session=to_session,
        student=student,
        fee_type=fee_type,
        is_carry_forward=True,
        defaults={
            'assigned_class': student.current_class,
            'total_amount': carry_amount,
            'concession_amount': Decimal('0.00'),
            'final_amount': carry_amount,
            'is_active': True,
        },
    )

    return {
        'carry_forward_due': due,
        'student_fee': student_fee,
    }


@transaction.atomic
def sync_student_fees_for_scope(*, school, session: AcademicSession, school_class=None):
    students = Student.objects.filter(
        school=school,
        session=session,
        is_archived=False,
        current_class__isnull=False,
    )
    if school_class:
        students = students.filter(current_class=school_class)

    synced = 0
    for student in students.select_related('current_class'):
        sync_student_fees_for_student(student=student)
        synced += 1
    return synced


def build_fee_receipt_image(receipt: FeeReceipt):
    width = 1240
    height = 1754
    page = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(page)

    payment = receipt.payment
    student = receipt.student

    draw.rectangle((30, 30, width - 30, height - 30), outline='black', width=3)
    draw.text((60, 60), f"{receipt.school.name} - Fee Receipt", fill='black')
    draw.text((60, 110), f"Receipt No: {receipt.receipt_number}", fill='black')
    draw.text((60, 150), f"Generated On: {receipt.generated_at.strftime('%Y-%m-%d %H:%M')}", fill='black')
    draw.text((60, 190), f"Session: {receipt.session.name}", fill='black')
    draw.text((60, 230), f"Student: {student.full_name} ({student.admission_number})", fill='black')
    draw.text((60, 270), f"Installment: {payment.installment.name}", fill='black')
    draw.text((60, 310), f"Payment Date: {payment.payment_date}", fill='black')
    draw.text((60, 350), f"Mode: {payment.get_payment_mode_display()}", fill='black')
    draw.text((60, 390), f"Reference: {payment.reference_number or '-'}", fill='black')

    y = 470
    draw.text((60, y), 'Fee Type', fill='black')
    draw.text((860, y), 'Amount', fill='black')
    draw.line((60, y + 26, width - 60, y + 26), fill='black')
    y += 50

    allocations = payment.allocations.select_related('student_fee__fee_type').order_by('id')
    for allocation in allocations:
        fee_name = allocation.student_fee.fee_type.name if allocation.student_fee_id else 'Carry Forward Due'
        draw.text((60, y), fee_name, fill='black')
        draw.text((860, y), str(_quantize(allocation.amount)), fill='black')
        y += 36

    y += 20
    draw.line((60, y, width - 60, y), fill='black')
    y += 30

    draw.text((60, y), f"Principal Paid: {payment.amount_paid}", fill='black')
    y += 36
    draw.text((60, y), f"Fine Collected: {payment.fine_amount}", fill='black')
    y += 36
    draw.text((60, y), f"Total Collected: {payment.total_collected}", fill='black')
    y += 70

    if payment.is_reversed:
        draw.text((60, y), f"STATUS: REVERSED ({payment.reversal_reason})", fill='black')

    return page


def generate_fee_receipt_pdf(receipt: FeeReceipt) -> bytes:
    image = build_fee_receipt_image(receipt)
    return image_to_pdf_bytes([image])
