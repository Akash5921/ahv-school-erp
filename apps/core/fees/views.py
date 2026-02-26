
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.students.models import Student
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    CarryForwardForm,
    ClassFeeStructureForm,
    FeePaymentCollectionForm,
    FeePaymentReverseForm,
    FeeRefundForm,
    FeeRefundReverseForm,
    FeeTypeForm,
    InstallmentForm,
    StudentConcessionForm,
    StudentFeeSyncForm,
)
from .models import (
    ClassFeeStructure,
    FeePayment,
    FeeReceipt,
    FeeRefund,
    FeeType,
    Installment,
    LedgerEntry,
    StudentConcession,
    StudentFee,
)
from .services import (
    collect_fee_payment,
    create_fee_refund,
    generate_carry_forward_due,
    generate_fee_receipt_pdf,
    recalculate_student_fee_concessions,
    reverse_fee_payment,
    reverse_fee_refund,
    student_outstanding_summary,
    sync_student_fees_for_scope,
    sync_student_fees_for_student,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('session')

    selected_session = None
    if session_id and str(session_id).isdigit():
        selected_session = sessions.filter(id=int(session_id)).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


@login_required
@role_required('schooladmin')
def fee_type_list(request):
    school = request.user.school

    if request.method == 'POST':
        form = FeeTypeForm(request.POST)
        if form.is_valid():
            fee_type = form.save(commit=False)
            fee_type.school = school
            fee_type.save()
            log_audit_event(
                request=request,
                action='fees.fee_type_created',
                school=school,
                target=fee_type,
                details=f"Name={fee_type.name}, Category={fee_type.category}",
            )
            messages.success(request, 'Fee type saved successfully.')
            return redirect('fee_type_list_core')
    else:
        form = FeeTypeForm()

    fee_types = FeeType.objects.filter(school=school).order_by('name')
    return render(request, 'fees_core/fee_type_list.html', {
        'fee_types': fee_types,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def fee_type_update(request, pk):
    school = request.user.school
    fee_type = get_object_or_404(FeeType, pk=pk, school=school)

    if request.method == 'POST':
        form = FeeTypeForm(request.POST, instance=fee_type)
        if form.is_valid():
            fee_type = form.save()
            log_audit_event(
                request=request,
                action='fees.fee_type_updated',
                school=school,
                target=fee_type,
                details=f"Name={fee_type.name}",
            )
            messages.success(request, 'Fee type updated successfully.')
            return redirect('fee_type_list_core')
    else:
        form = FeeTypeForm(instance=fee_type)

    return render(request, 'fees_core/fee_type_form.html', {
        'form': form,
        'fee_type': fee_type,
    })


@login_required
@role_required('schooladmin')
@require_POST
def fee_type_deactivate(request, pk):
    fee_type = get_object_or_404(FeeType, pk=pk, school=request.user.school)
    fee_type.delete()
    log_audit_event(
        request=request,
        action='fees.fee_type_deactivated',
        school=request.user.school,
        target=fee_type,
        details=f"Name={fee_type.name}",
    )
    messages.success(request, 'Fee type deactivated.')
    return redirect('fee_type_list_core')


@login_required
@role_required('schooladmin')
def class_fee_structure_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = ClassFeeStructureForm(request.POST, school=school, default_session=selected_session)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            try:
                row.save()
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='fees.class_fee_structure_saved',
                    school=school,
                    target=row,
                    details=f"Class={row.school_class_id}, FeeType={row.fee_type_id}, Amount={row.amount}",
                )
                messages.success(request, 'Class fee structure saved successfully.')
                return redirect(f"{reverse('class_fee_structure_list_core')}?session={row.session_id}")
    else:
        form = ClassFeeStructureForm(school=school, default_session=selected_session)

    rows = ClassFeeStructure.objects.filter(school=school).select_related('session', 'school_class', 'fee_type')
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'fees_core/class_fee_structure_list.html', {
        'rows': rows.order_by('school_class__display_order', 'fee_type__name'),
        'form': form,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def class_fee_structure_update(request, pk):
    school = request.user.school
    row = get_object_or_404(ClassFeeStructure, pk=pk, school=school)

    if request.method == 'POST':
        form = ClassFeeStructureForm(request.POST, instance=row, school=school, default_session=row.session)
        if form.is_valid():
            try:
                row = form.save()
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='fees.class_fee_structure_updated',
                    school=school,
                    target=row,
                    details=f"Class={row.school_class_id}, FeeType={row.fee_type_id}, Amount={row.amount}",
                )
                messages.success(request, 'Class fee structure updated successfully.')
                return redirect(f"{reverse('class_fee_structure_list_core')}?session={row.session_id}")
    else:
        form = ClassFeeStructureForm(instance=row, school=school, default_session=row.session)

    return render(request, 'fees_core/class_fee_structure_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def class_fee_structure_deactivate(request, pk):
    row = get_object_or_404(ClassFeeStructure, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='fees.class_fee_structure_deactivated',
        school=request.user.school,
        target=row,
        details=f"Class={row.school_class_id}, FeeType={row.fee_type_id}",
    )
    messages.success(request, 'Class fee structure deactivated.')
    return redirect(f"{reverse('class_fee_structure_list_core')}?session={row.session_id}")


@login_required
@role_required('schooladmin')
def installment_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = InstallmentForm(request.POST, school=school, default_session=selected_session)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='fees.installment_saved',
                school=school,
                target=row,
                details=f"Name={row.name}, DueDate={row.due_date}",
            )
            messages.success(request, 'Installment saved successfully.')
            return redirect(f"{reverse('installment_list_core')}?session={row.session_id}")
    else:
        form = InstallmentForm(school=school, default_session=selected_session)

    rows = Installment.objects.filter(school=school)
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'fees_core/installment_list.html', {
        'rows': rows.order_by('due_date', 'id'),
        'form': form,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def installment_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Installment, pk=pk, school=school)

    if request.method == 'POST':
        form = InstallmentForm(request.POST, instance=row, school=school, default_session=row.session)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='fees.installment_updated',
                school=school,
                target=row,
                details=f"Name={row.name}, DueDate={row.due_date}",
            )
            messages.success(request, 'Installment updated successfully.')
            return redirect(f"{reverse('installment_list_core')}?session={row.session_id}")
    else:
        form = InstallmentForm(instance=row, school=school, default_session=row.session)

    return render(request, 'fees_core/installment_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def installment_deactivate(request, pk):
    row = get_object_or_404(Installment, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='fees.installment_deactivated',
        school=request.user.school,
        target=row,
        details=f"Name={row.name}",
    )
    messages.success(request, 'Installment deactivated.')
    return redirect(f"{reverse('installment_list_core')}?session={row.session_id}")


@login_required
@role_required(['schooladmin', 'accountant'])
def student_fee_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    fees = StudentFee.objects.filter(
        school=school,
    ).select_related('student', 'fee_type', 'session', 'assigned_class')
    if selected_session:
        fees = fees.filter(session=selected_session)

    student_id = request.GET.get('student')
    class_id = request.GET.get('class')
    if student_id and str(student_id).isdigit():
        fees = fees.filter(student_id=int(student_id))
    if class_id and str(class_id).isdigit():
        fees = fees.filter(assigned_class_id=int(class_id))

    sync_form = StudentFeeSyncForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'sync_scope' else None,
        school=school,
        default_session=selected_session,
    )

    if request.method == 'POST' and request.POST.get('action') == 'sync_scope':
        if sync_form.is_valid():
            synced = sync_student_fees_for_scope(
                school=school,
                session=sync_form.cleaned_data['session'],
                school_class=sync_form.cleaned_data['school_class'],
            )
            messages.success(request, f'Fee assignments synced for {synced} students.')
            query = f"session={sync_form.cleaned_data['session'].id}"
            return redirect(f"{reverse('student_fee_list_core')}?{query}")

    return render(request, 'fees_core/student_fee_list.html', {
        'fees': fees.order_by('student__admission_number', '-is_carry_forward', 'fee_type__name'),
        'sessions': sessions,
        'selected_session': selected_session,
        'selected_student_id': int(student_id) if str(student_id).isdigit() else None,
        'selected_class_id': int(class_id) if str(class_id).isdigit() else None,
        'sync_form': sync_form,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
@require_POST
def student_fee_sync_single(request, student_id):
    target = get_object_or_404(Student, pk=student_id, school=request.user.school)
    sync_student_fees_for_student(student=target)
    messages.success(request, f'Fee assignment synced for {target.admission_number}.')

    log_audit_event(
        request=request,
        action='fees.student_fee_synced_single',
        school=request.user.school,
        target=target,
        details=f"Student={target.admission_number}",
    )

    return redirect('student_fee_list_core')

@login_required
@role_required('schooladmin')
def concession_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = StudentConcessionForm(request.POST, school=school, default_session=selected_session)
        if form.is_valid():
            concession = form.save(commit=False)
            concession.school = school
            concession.approved_by = request.user
            concession.save()
            recalculate_student_fee_concessions(
                student=concession.student,
                session=concession.session,
            )
            log_audit_event(
                request=request,
                action='fees.concession_saved',
                school=school,
                target=concession,
                details=f"Student={concession.student_id}, FeeType={concession.fee_type_id or 'all'}",
            )
            messages.success(request, 'Concession saved and student fee recalculated.')
            return redirect(f"{reverse('concession_list_core')}?session={concession.session_id}")
    else:
        form = StudentConcessionForm(school=school, default_session=selected_session)

    rows = StudentConcession.objects.filter(school=school).select_related('student', 'session', 'fee_type', 'approved_by')
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'fees_core/concession_list.html', {
        'rows': rows.order_by('-created_at'),
        'form': form,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def concession_update(request, pk):
    school = request.user.school
    row = get_object_or_404(StudentConcession, pk=pk, school=school)

    if request.method == 'POST':
        form = StudentConcessionForm(request.POST, instance=row, school=school, default_session=row.session)
        if form.is_valid():
            row = form.save(commit=False)
            row.approved_by = request.user
            row.save()
            recalculate_student_fee_concessions(student=row.student, session=row.session)
            log_audit_event(
                request=request,
                action='fees.concession_updated',
                school=school,
                target=row,
                details=f"Student={row.student_id}, FeeType={row.fee_type_id or 'all'}",
            )
            messages.success(request, 'Concession updated successfully.')
            return redirect(f"{reverse('concession_list_core')}?session={row.session_id}")
    else:
        form = StudentConcessionForm(instance=row, school=school, default_session=row.session)

    return render(request, 'fees_core/concession_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def concession_deactivate(request, pk):
    row = get_object_or_404(StudentConcession, pk=pk, school=request.user.school)
    row.delete()
    recalculate_student_fee_concessions(student=row.student, session=row.session)
    log_audit_event(
        request=request,
        action='fees.concession_deactivated',
        school=request.user.school,
        target=row,
        details=f"Student={row.student_id}",
    )
    messages.success(request, 'Concession deactivated.')
    return redirect(f"{reverse('concession_list_core')}?session={row.session_id}")


@login_required
@role_required(['schooladmin', 'accountant'])
def payment_manage(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    collection_form = FeePaymentCollectionForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'collect' else None,
        school=school,
        default_session=selected_session,
    )

    reverse_form = FeePaymentReverseForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'reverse' else None
    )

    if request.method == 'POST' and request.POST.get('action') == 'collect':
        if collection_form.is_valid():
            try:
                result = collect_fee_payment(
                    school=school,
                    session=collection_form.cleaned_data['session'],
                    student=collection_form.cleaned_data['student'],
                    installment=collection_form.cleaned_data['installment'],
                    amount_paid=collection_form.cleaned_data['amount_paid'],
                    payment_mode=collection_form.cleaned_data['payment_mode'],
                    received_by=request.user,
                    payment_date=collection_form.cleaned_data['payment_date'],
                    reference_number=collection_form.cleaned_data['reference_number'],
                )
            except ValidationError as exc:
                collection_form.add_error(None, '; '.join(exc.messages))
            else:
                payment = result['payment']
                log_audit_event(
                    request=request,
                    action='fees.payment_collected',
                    school=school,
                    target=payment,
                    details=f"Student={payment.student_id}, Amount={payment.amount_paid}, Fine={payment.fine_amount}",
                )
                messages.success(request, 'Payment collected successfully.')
                return redirect('fee_receipt_detail_core', receipt_id=result['receipt'].id)

    if request.method == 'POST' and request.POST.get('action') == 'reverse':
        payment_id = request.POST.get('payment_id')
        payment = get_object_or_404(FeePayment, pk=payment_id, school=school)
        if reverse_form.is_valid():
            try:
                reverse_fee_payment(
                    payment=payment,
                    reversed_by=request.user,
                    reason=reverse_form.cleaned_data['reason'],
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='fees.payment_reversed',
                    school=school,
                    target=payment,
                    details=f"PaymentId={payment.id}",
                )
                messages.success(request, 'Payment reversed successfully.')
                return redirect('payment_manage_core')

    payments = FeePayment.objects.filter(school=school).select_related('student', 'installment', 'session', 'receipt')
    if selected_session:
        payments = payments.filter(session=selected_session)

    return render(request, 'fees_core/payment_manage.html', {
        'collection_form': collection_form,
        'reverse_form': reverse_form,
        'payments': payments.order_by('-payment_date', '-id')[:200],
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def fee_receipt_detail(request, receipt_id):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related('payment', 'student', 'session', 'school'),
        pk=receipt_id,
        school=request.user.school,
    )
    return render(request, 'fees_core/receipt_detail.html', {
        'receipt': receipt,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def fee_receipt_pdf(request, receipt_id):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related('payment', 'student', 'session', 'school'),
        pk=receipt_id,
        school=request.user.school,
    )
    pdf_bytes = generate_fee_receipt_pdf(receipt)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{receipt.receipt_number}.pdf"'
    return response


@login_required
@role_required(['schooladmin', 'accountant'])
def refund_list(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    form = FeeRefundForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'create_refund' else None,
        school=school,
        default_session=selected_session,
    )
    reverse_form = FeeRefundReverseForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'reverse_refund' else None
    )

    if request.method == 'POST' and request.POST.get('action') == 'create_refund':
        if form.is_valid():
            payment = form.cleaned_data['payment']
            try:
                result = create_fee_refund(
                    payment=payment,
                    refund_amount=form.cleaned_data['refund_amount'],
                    reason=form.cleaned_data['reason'],
                    approved_by=request.user,
                    refund_date=form.cleaned_data['refund_date'],
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                refund = result['refund']
                log_audit_event(
                    request=request,
                    action='fees.refund_created',
                    school=school,
                    target=refund,
                    details=f"Payment={refund.payment_id}, Amount={refund.refund_amount}",
                )
                messages.success(request, 'Refund recorded successfully.')
                return redirect('refund_list_core')

    if request.method == 'POST' and request.POST.get('action') == 'reverse_refund':
        refund_id = request.POST.get('refund_id')
        refund = get_object_or_404(FeeRefund, pk=refund_id, school=school)
        if reverse_form.is_valid():
            try:
                reverse_fee_refund(
                    refund=refund,
                    reversed_by=request.user,
                    reason=reverse_form.cleaned_data['reason'],
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='fees.refund_reversed',
                    school=school,
                    target=refund,
                    details=f"Refund={refund.id}",
                )
                messages.success(request, 'Refund reversed successfully.')
                return redirect('refund_list_core')

    refunds = FeeRefund.objects.filter(school=school).select_related('student', 'payment', 'approved_by')
    if selected_session:
        refunds = refunds.filter(session=selected_session)

    return render(request, 'fees_core/refund_list.html', {
        'rows': refunds.order_by('-refund_date', '-id')[:200],
        'form': form,
        'reverse_form': reverse_form,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def dues_report(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    if not selected_session:
        return render(request, 'fees_core/dues_report.html', {
            'rows': [],
            'sessions': sessions,
            'selected_session': None,
        })

    students = Student.objects.filter(
        school=school,
        session=selected_session,
        is_archived=False,
    ).order_by('admission_number')

    rows = []
    for student in students:
        summary = student_outstanding_summary(student=student, session=selected_session)
        if summary['total_due'] <= 0:
            continue
        rows.append({
            'student': student,
            'principal_due': summary['principal_due'],
            'fine_due': summary['fine_due'],
            'total_due': summary['total_due'],
        })

    return render(request, 'fees_core/dues_report.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def carry_forward_manage(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    form = CarryForwardForm(request.POST or None, school=school, default_session=selected_session)

    if request.method == 'POST' and form.is_valid():
        try:
            result = generate_carry_forward_due(
                student=form.cleaned_data['student'],
                from_session=form.cleaned_data['from_session'],
                to_session=form.cleaned_data['to_session'],
            )
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            due = result['carry_forward_due']
            log_audit_event(
                request=request,
                action='fees.carry_forward_created',
                school=school,
                target=due,
                details=f"Student={due.student_id}, Amount={due.amount}",
            )
            messages.success(request, 'Carry forward due generated and assigned to target session.')
            return redirect('carry_forward_manage_core')

    return render(request, 'fees_core/carry_forward.html', {
        'form': form,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def ledger_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    rows = LedgerEntry.objects.filter(school=school).select_related('session', 'created_by', 'related_entry')
    if selected_session:
        rows = rows.filter(session=selected_session)

    entry_type = request.GET.get('type')
    if entry_type:
        rows = rows.filter(transaction_type=entry_type)

    return render(request, 'fees_core/ledger_list.html', {
        'rows': rows.order_by('-date', '-id')[:500],
        'sessions': sessions,
        'selected_session': selected_session,
        'selected_type': entry_type,
        'type_choices': LedgerEntry.TRANSACTION_TYPE_CHOICES,
    })
