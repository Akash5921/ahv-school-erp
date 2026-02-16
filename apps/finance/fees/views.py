from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone

from apps.academics.students.models import Student
from apps.finance.fees.models import FeePayment
from apps.finance.accounts.models import Ledger
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required


@login_required
@role_required('accountant')
def collect_fee(request):
    school = request.user.school
    students = Student.objects.filter(school=school).order_by('first_name', 'last_name')
    error = None

    if request.method == 'POST':
        student_id = request.POST.get('student')
        amount_raw = request.POST.get('amount', '0')
        note = request.POST.get('note', '')

        current_session = school.current_session
        if not current_session:
            error = 'No active academic session set for this school.'
        else:
            student = get_object_or_404(
                Student,
                id=student_id,
                school=school
            )

            try:
                amount = Decimal(amount_raw)
            except InvalidOperation:
                amount = Decimal('0')

            if amount <= 0:
                error = 'Amount must be greater than zero.'
            else:
                fee_payment = FeePayment.objects.create(
                    student=student,
                    school=school,
                    amount=amount,
                    note=note
                )

                Ledger.objects.create(
                    school=school,
                    academic_session=current_session,
                    entry_type='income',
                    amount=amount,
                    description=f"Fee collected from {student.name}",
                    transaction_date=timezone.now().date()
                )

                log_audit_event(
                    request=request,
                    action='fee.collected',
                    school=school,
                    target=fee_payment,
                    details=f"Student={student.id}, Amount={amount}",
                )
                return redirect('accountant_dashboard')

    return render(request, 'fees/collect_fee.html', {
        'students': students,
        'error': error,
    })
