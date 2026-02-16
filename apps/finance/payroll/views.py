from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from apps.academics.staff.models import Staff
from apps.finance.payroll.models import SalaryPayment
from apps.finance.accounts.models import Ledger


@login_required
def pay_salary(request):

    if request.user.role != 'accountant':
        return render(request, 'reports/forbidden.html')

    staff_members = Staff.objects.filter(school=request.user.school)

    if request.method == 'POST':
        staff_id = request.POST.get('staff')
        amount = request.POST.get('amount')
        note = request.POST.get('note')

        staff = Staff.objects.get(id=staff_id)

        SalaryPayment.objects.create(
            staff=staff,
            school=request.user.school,
            amount=amount,
            note=note
        )

        # Auto ledger entry (expense)
        Ledger.objects.create(
            school=request.user.school,
            entry_type='expense',
            amount=amount,
            description=f"Salary paid to {staff.name}"
        )

        return redirect('accountant_dashboard')

    return render(request, 'payroll/pay_salary.html', {
        'staff_members': staff_members
    })
