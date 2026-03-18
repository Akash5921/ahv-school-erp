from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum

from apps.core.hr.models import Payroll, SalaryAdvance


def _report(title, columns, rows, summary):
    return {
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
    }


def _money(value):
    return Decimal(str(value or '0')).quantize(Decimal('0.01'))


def monthly_payroll_report(filters):
    payrolls = Payroll.objects.filter(
        school=filters.school,
        month=filters.month,
        year=filters.year,
    ).select_related('staff', 'staff__user', 'staff__designation')
    if filters.session:
        payrolls = payrolls.filter(session=filters.session)
    if filters.staff:
        payrolls = payrolls.filter(staff=filters.staff)

    rows = [[
        row.staff.employee_id,
        row.staff.full_name,
        row.staff.department or '-',
        row.gross_salary,
        row.total_deductions,
        row.net_salary,
        'Yes' if row.is_paid else 'No',
        'Yes' if row.is_on_hold else 'No',
    ] for row in payrolls.order_by('staff__employee_id')]
    return _report(
        'Monthly Payroll Report',
        ['Employee ID', 'Staff', 'Department', 'Gross', 'Deductions', 'Net', 'Paid', 'On Hold'],
        rows,
        [('Payroll Rows', len(rows)), ('Net Total', sum((row[5] for row in rows), Decimal('0.00')))],
    )


def department_salary_expense_report(filters):
    payrolls = Payroll.objects.filter(
        school=filters.school,
        year=filters.year,
    )
    if filters.session:
        payrolls = payrolls.filter(session=filters.session)
    if filters.month:
        payrolls = payrolls.filter(month=filters.month)

    grouped = payrolls.values('staff__department').annotate(
        total=Sum('net_salary'),
        staff_count=Count('staff_id', distinct=True),
    ).order_by('staff__department')
    rows = [[row['staff__department'] or 'Unassigned', _money(row['total']), row['staff_count']] for row in grouped]
    return _report(
        'Department-wise Salary Expense Report',
        ['Department', 'Net Salary Total', 'Staff'],
        rows,
        [('Departments', len(rows))],
    )


def advance_salary_report(filters):
    advances = SalaryAdvance.objects.filter(
        school=filters.school,
        request_date__range=(filters.date_from, filters.date_to),
    ).select_related('staff', 'staff__user', 'approved_by')
    if filters.session:
        advances = advances.filter(session=filters.session)
    if filters.staff:
        advances = advances.filter(staff=filters.staff)

    rows = [[
        row.request_date,
        row.staff.employee_id,
        row.staff.full_name,
        row.amount,
        row.remaining_balance,
        row.get_status_display(),
    ] for row in advances.order_by('-request_date', '-id')]
    return _report(
        'Advance Salary Report',
        ['Request Date', 'Employee ID', 'Staff', 'Amount', 'Remaining Balance', 'Status'],
        rows,
        [('Advance Total', sum((row[3] for row in rows), Decimal('0.00')))],
    )


def salary_hold_report(filters):
    payrolls = Payroll.objects.filter(
        school=filters.school,
        is_on_hold=True,
    ).select_related('staff', 'staff__user')
    if filters.session:
        payrolls = payrolls.filter(session=filters.session)
    if filters.year:
        payrolls = payrolls.filter(year=filters.year)
    if filters.month:
        payrolls = payrolls.filter(month=filters.month)

    rows = [[
        row.staff.employee_id,
        row.staff.full_name,
        f"{row.month:02d}/{row.year}",
        row.net_salary,
        row.hold_reason or '-',
    ] for row in payrolls.order_by('-year', '-month', 'staff__employee_id')]
    return _report(
        'Salary Hold Report',
        ['Employee ID', 'Staff', 'Payroll Period', 'Net Salary', 'Hold Reason'],
        rows,
        [('Held Payrolls', len(rows))],
    )


def annual_salary_summary(filters):
    payrolls = Payroll.objects.filter(
        school=filters.school,
        year=filters.year,
    )
    if filters.session:
        payrolls = payrolls.filter(session=filters.session)
    if filters.staff:
        payrolls = payrolls.filter(staff=filters.staff)

    grouped = payrolls.values(
        'staff__employee_id',
        'staff__user__first_name',
        'staff__user__last_name',
    ).annotate(
        gross_total=Sum('gross_salary'),
        deduction_total=Sum('total_deductions'),
        net_total=Sum('net_salary'),
        payroll_count=Count('id'),
    ).order_by('staff__employee_id')

    rows = [[
        row['staff__employee_id'],
        f"{row['staff__user__first_name']} {row['staff__user__last_name']}".strip() or row['staff__employee_id'],
        _money(row['gross_total']),
        _money(row['deduction_total']),
        _money(row['net_total']),
        row['payroll_count'],
    ] for row in grouped]
    return _report(
        'Annual Salary Summary',
        ['Employee ID', 'Staff', 'Gross Total', 'Deduction Total', 'Net Total', 'Payrolls'],
        rows,
        [('Annual Net Total', sum((row[4] for row in rows), Decimal('0.00')))],
    )
