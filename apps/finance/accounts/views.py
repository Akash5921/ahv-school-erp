from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum
from apps.core.users.decorators import role_required
from apps.finance.accounts.models import Ledger
from apps.core.academic_sessions.models import AcademicSession


@login_required
@role_required('accountant')
def accountant_dashboard(request):

    school = request.user.school

    # Get active academic session
    session = AcademicSession.objects.filter(
        school=school,
        is_active=True
    ).first()

    # If no active session exists
    if not session:
        return render(request, 'reports/forbidden.html')

    # TOTAL INCOME
    total_income = Ledger.objects.for_school(school).filter(
        academic_session=session,
        entry_type='income'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # TOTAL EXPENSE
    total_expense = Ledger.objects.for_school(school).filter(
        academic_session=session,
        entry_type='expense'
    ).aggregate(total=Sum('amount'))['total'] or 0

    balance = total_income - total_expense

    # MONTHLY INCOME
    monthly_income = Ledger.objects.for_school(school).filter(
        academic_session=session,
        entry_type='income'
    ).values('transaction_date__month') \
     .annotate(total=Sum('amount')) \
     .order_by('transaction_date__month')

    # MONTHLY EXPENSE
    monthly_expense = Ledger.objects.for_school(school).filter(
        academic_session=session,
        entry_type='expense'
    ).values('transaction_date__month') \
     .annotate(total=Sum('amount')) \
     .order_by('transaction_date__month')

    income_data = {
        item['transaction_date__month']: float(item['total'])
        for item in monthly_income
    }

    expense_data = {
        item['transaction_date__month']: float(item['total'])
        for item in monthly_expense
    }

    months = list(range(1, 13))

    income_list = [income_data.get(month, 0) for month in months]
    expense_list = [expense_data.get(month, 0) for month in months]

    return render(request, 'accounts/accountant_dashboard.html', {
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'income_list': income_list,
        'expense_list': expense_list
    })
