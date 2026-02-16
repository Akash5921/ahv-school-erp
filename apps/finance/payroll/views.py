from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone

from apps.finance.payroll.models import SalaryPayment, SalaryStructure
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required


@login_required
@role_required('accountant')
def pay_salary(request):
    school = request.user.school
    salary_structures = SalaryStructure.objects.filter(
        school=school,
        staff__is_active=True
    ).select_related('staff')
    error = None

    if request.method == 'POST':
        salary_structure_id = request.POST.get('salary_structure')
        amount_raw = request.POST.get('amount', '')
        month = request.POST.get('month', '').strip()

        current_session = school.current_session
        if not current_session:
            error = 'No active academic session set for this school.'
        else:
            salary_structure = get_object_or_404(
                SalaryStructure,
                id=salary_structure_id,
                school=school
            )

            if not month:
                month = timezone.now().strftime('%B %Y')

            if amount_raw:
                try:
                    amount_paid = Decimal(amount_raw)
                except InvalidOperation:
                    amount_paid = Decimal('0')
            else:
                amount_paid = salary_structure.monthly_salary

            if amount_paid <= 0:
                error = 'Salary amount must be greater than zero.'
            else:
                payment = SalaryPayment.objects.create(
                    salary_structure=salary_structure,
                    academic_session=current_session,
                    month=month,
                    amount_paid=amount_paid,
                )

                log_audit_event(
                    request=request,
                    action='salary.paid',
                    school=school,
                    target=payment,
                    details=f"Staff={salary_structure.staff.id}, Amount={amount_paid}, Month={month}",
                )
                return redirect('accountant_dashboard')

    return render(request, 'payroll/pay_salary.html', {
        'salary_structures': salary_structures,
        'error': error,
    })
