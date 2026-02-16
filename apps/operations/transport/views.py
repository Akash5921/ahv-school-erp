from django.shortcuts import render
from django.db.models import Sum

from apps.academics.students.models import Student
from apps.academics.attendance.models import StudentAttendance
from apps.finance.accounts.models import Ledger
from apps.academics.staff.models import Staff


def dashboard(request):
    user = request.user
    school = user.school

    total_students = Student.objects.filter(school=school).count()
    total_staff = Staff.objects.filter(school=school).count()

    total_income = Ledger.objects.filter(
        school=school,
        entry_type='income'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    total_expense = Ledger.objects.filter(
        school=school,
        entry_type='expense'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    context = {
        'total_students': total_students,
        'total_staff': total_staff,
        'total_income': total_income,
        'total_expense': total_expense,
    }

    return render(request, 'reports/dashboard.html', context)
