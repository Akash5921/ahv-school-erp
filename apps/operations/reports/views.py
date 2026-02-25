from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum

from apps.academics.students.models import Student
from apps.finance.accounts.models import Ledger
from apps.academics.staff.models import Staff
from apps.assets.inventory.models import InventoryItem, InventoryPurchase
from apps.operations.transport.models import Bus, StudentTransport
from apps.core.users.decorators import role_required


@login_required
@role_required(['schooladmin', 'accountant'])
def dashboard(request):
    school = request.user.school
    current_session = school.current_session

    total_students = Student.objects.filter(school=school).count()
    total_staff = Staff.objects.filter(school=school).count()
    total_buses = Bus.objects.filter(school=school).count()
    total_inventory_items = InventoryItem.objects.filter(school=school).count()

    total_income = Ledger.objects.filter(
        school=school,
        entry_type='income'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    total_expense = Ledger.objects.filter(
        school=school,
        entry_type='expense'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    if current_session:
        inventory_purchase_total = InventoryPurchase.objects.filter(
            item__school=school,
            academic_session=current_session
        ).aggregate(Sum('total_cost'))['total_cost__sum'] or 0

        transport_students = StudentTransport.objects.filter(
            student__school=school,
            academic_session=current_session
        ).count()
    else:
        inventory_purchase_total = 0
        transport_students = 0

    return render(request, 'reports/dashboard.html', {
        'total_students': total_students,
        'total_staff': total_staff,
        'total_buses': total_buses,
        'transport_students': transport_students,
        'total_inventory_items': total_inventory_items,
        'inventory_purchase_total': inventory_purchase_total,
        'total_income': total_income,
        'total_expense': total_expense,
        'current_session': current_session,
    })
