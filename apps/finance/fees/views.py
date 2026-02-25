from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.finance.accounts.models import Ledger
from apps.finance.fees.forms import (
    FeeCollectionForm,
    FeeInstallmentForm,
    FeeStructureForm,
    StudentFeeForm,
    bind_school_fee_collection_form,
    bind_school_fee_structure_form,
    bind_school_student_fee_form,
)
from apps.finance.fees.models import FeeInstallment, FeePayment, FeeStructure, StudentFee
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required


def _receipt_number(school, payment_id):
    date_code = timezone.now().strftime('%Y%m%d')
    return f"RCP-{school.id}-{date_code}-{payment_id:06d}"


@login_required
@role_required('schooladmin')
def fee_structure_list(request):
    school = request.user.school
    fee_structures = FeeStructure.objects.filter(
        school=school
    ).select_related('academic_session', 'school_class').order_by(
        '-academic_session__start_date', 'school_class__order', 'name'
    )
    error = None

    if request.method == 'POST':
        form = FeeStructureForm(request.POST)
        bind_school_fee_structure_form(form, school)
        if form.is_valid():
            fee_structure = form.save(commit=False)
            fee_structure.school = school
            fee_structure.save()
            log_audit_event(
                request=request,
                action='fee.structure_created',
                school=school,
                target=fee_structure,
                details=f"Class={fee_structure.school_class_id}, Session={fee_structure.academic_session_id}, Name={fee_structure.name}",
            )
            return redirect('fee_structure_list')
        error = 'Please correct fee structure details.'
    else:
        form = FeeStructureForm()
        bind_school_fee_structure_form(form, school)

    return render(request, 'fees/fee_structure_list.html', {
        'fee_structures': fee_structures,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def fee_installment_manage(request, fee_structure_id):
    school = request.user.school
    fee_structure = get_object_or_404(FeeStructure, id=fee_structure_id, school=school)
    installments = FeeInstallment.objects.filter(
        fee_structure=fee_structure
    ).order_by('due_date', 'id')
    error = None

    if request.method == 'POST':
        form = FeeInstallmentForm(request.POST)
        if form.is_valid():
            installment = form.save(commit=False)
            installment.fee_structure = fee_structure
            try:
                installment.save()
            except IntegrityError:
                error = 'Installment title already exists for this fee structure.'
            else:
                log_audit_event(
                    request=request,
                    action='fee.installment_created',
                    school=school,
                    target=installment,
                    details=f"Structure={fee_structure.id}, Title={installment.title}, Amount={installment.amount}",
                )
                return redirect('fee_installment_manage', fee_structure_id=fee_structure.id)
        elif not error:
            error = 'Please correct installment details.'
    else:
        form = FeeInstallmentForm()

    return render(request, 'fees/fee_installment_manage.html', {
        'fee_structure': fee_structure,
        'installments': installments,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def student_fee_manage(request):
    school = request.user.school
    student_fees = StudentFee.objects.filter(
        student__school=school
    ).select_related(
        'student',
        'fee_structure',
        'fee_structure__school_class',
        'fee_structure__academic_session'
    ).order_by(
        'student__first_name',
        'student__last_name',
        '-fee_structure__academic_session__start_date'
    )
    error = None

    if request.method == 'POST':
        form = StudentFeeForm(request.POST)
        bind_school_student_fee_form(form, school)
        if form.is_valid():
            cleaned = form.cleaned_data
            student_fee, _ = StudentFee.objects.update_or_create(
                student=cleaned['student'],
                fee_structure=cleaned['fee_structure'],
                defaults={
                    'total_amount': cleaned['total_amount'],
                    'concession_amount': cleaned['concession_amount'],
                    'concession_note': cleaned['concession_note'],
                }
            )
            log_audit_event(
                request=request,
                action='fee.student_fee_saved',
                school=school,
                target=student_fee,
                details=f"Student={student_fee.student_id}, FeeStructure={student_fee.fee_structure_id}",
            )
            return redirect('student_fee_manage')
        error = 'Please correct student fee details.'
    else:
        form = StudentFeeForm()
        bind_school_student_fee_form(form, school)

    return render(request, 'fees/student_fee_manage.html', {
        'student_fees': student_fees,
        'form': form,
        'error': error,
    })


@login_required
@role_required('accountant')
def collect_fee(request):
    school = request.user.school
    error = None
    current_session = school.current_session

    if request.method == 'POST':
        form = FeeCollectionForm(request.POST)
        bind_school_fee_collection_form(form, school)

        if not current_session:
            error = 'No active academic session set for this school.'
        elif form.is_valid():
            student_fee = form.cleaned_data['student_fee']
            amount = Decimal(form.cleaned_data['amount'])
            note = form.cleaned_data['note']

            if student_fee.fee_structure.academic_session_id != current_session.id:
                error = 'Selected fee record does not belong to the active academic session.'
            elif amount > student_fee.due_amount:
                error = f'Amount exceeds due amount ({student_fee.due_amount}).'
            else:
                with transaction.atomic():
                    student_fee = StudentFee.objects.select_for_update().get(pk=student_fee.pk)
                    if amount > student_fee.due_amount:
                        error = f'Amount exceeds due amount ({student_fee.due_amount}).'
                    else:
                        fee_payment = FeePayment.objects.create(
                            student=student_fee.student,
                            student_fee=student_fee,
                            school=school,
                            amount=amount,
                            note=note
                        )
                        fee_payment.receipt_number = _receipt_number(school, fee_payment.id)
                        fee_payment.save(update_fields=['receipt_number'])

                        student_fee.paid_amount = student_fee.paid_amount + amount
                        student_fee.save(update_fields=['paid_amount'])

                        Ledger.objects.create(
                            school=school,
                            academic_session=current_session,
                            entry_type='income',
                            amount=amount,
                            description=f"Fee collected from {student_fee.student.name} ({fee_payment.receipt_number})",
                            transaction_date=timezone.now().date()
                        )

                        log_audit_event(
                            request=request,
                            action='fee.collected',
                            school=school,
                            target=fee_payment,
                            details=f"StudentFee={student_fee.id}, Amount={amount}, Receipt={fee_payment.receipt_number}",
                        )
                        return redirect('fee_receipt', payment_id=fee_payment.id)
        elif not error:
            error = 'Please correct fee payment details.'
    else:
        form = FeeCollectionForm()
        bind_school_fee_collection_form(form, school)

    student_fee_rows = form.fields['student_fee'].queryset

    return render(request, 'fees/collect_fee.html', {
        'form': form,
        'student_fee_rows': student_fee_rows,
        'current_session': current_session,
        'recent_payments': FeePayment.objects.filter(
            school=school
        ).select_related('student').order_by('-date', '-id')[:10],
        'error': error,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def dues_report(request):
    school = request.user.school
    current_session = school.current_session
    query = request.GET.get('q', '').strip()

    dues_queryset = StudentFee.objects.filter(
        student__school=school
    ).select_related(
        'student',
        'fee_structure',
        'fee_structure__academic_session',
        'fee_structure__school_class'
    )

    if current_session:
        dues_queryset = dues_queryset.filter(
            fee_structure__academic_session=current_session
        )

    if query:
        dues_queryset = dues_queryset.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
        )

    due_rows = [row for row in dues_queryset if row.due_amount > 0]

    return render(request, 'fees/dues_report.html', {
        'due_rows': due_rows,
        'query': query,
        'current_session': current_session,
    })


@login_required
@role_required(['schooladmin', 'accountant', 'parent'])
def fee_receipt(request, payment_id):
    school = request.user.school
    queryset = FeePayment.objects.select_related(
        'student',
        'student_fee',
        'student_fee__fee_structure',
        'student_fee__fee_structure__academic_session',
        'student_fee__fee_structure__school_class'
    )

    if request.user.role == 'parent':
        queryset = queryset.filter(
            school=school,
            student__parent_user=request.user
        )
    else:
        queryset = queryset.filter(school=school)

    payment = get_object_or_404(queryset, id=payment_id)
    return render(request, 'fees/fee_receipt.html', {
        'payment': payment,
    })
