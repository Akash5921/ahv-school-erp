from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from apps.academics.students.models import Student
from apps.finance.fees.models import FeePayment
from apps.finance.accounts.models import Ledger


@login_required
def collect_fee(request):

    if request.user.role != 'accountant':
        return render(request, 'reports/forbidden.html')

    students = Student.objects.filter(school=request.user.school)

    if request.method == 'POST':
        student_id = request.POST.get('student')
        amount = request.POST.get('amount')
        note = request.POST.get('note')

        student = Student.objects.get(id=student_id)

        # Save fee payment
        FeePayment.objects.create(
            student=student,
            school=request.user.school,
            amount=amount,
            note=note
        )

        # Auto create ledger entry
        Ledger.objects.create(
            school=request.user.school,
            entry_type='income',
            amount=amount,
            description=f"Fee collected from {student.name}"
        )

        return redirect('accountant_dashboard')

    return render(request, 'fees/collect_fee.html', {
        'students': students
    })
