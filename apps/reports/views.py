from __future__ import annotations

from collections import OrderedDict

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render

from .academic_reports import (
    class_strength_report,
    failures_report,
    grade_distribution_report,
    student_result_report,
    subject_performance_report,
    top_performers_report,
)
from .attendance_reports import (
    below_threshold_alert_report,
    daily_attendance_report,
    monthly_class_attendance_report,
    staff_attendance_report,
    student_attendance_percentage_report,
)
from .exports import export_response
from .filters import build_report_filters
from .finance_reports import (
    concession_report,
    expense_summary,
    fee_collection_report,
    installment_collection_report,
    monthly_income_summary,
    pending_dues_report,
    profit_loss_summary,
    refund_report,
)
from .inventory_reports import (
    asset_report,
    library_overdue_report,
    low_stock_report,
    purchase_report,
    route_student_list_report,
    transport_fee_collection_report,
    vehicle_occupancy_summary_report,
)
from .payroll_reports import (
    advance_salary_report,
    annual_salary_summary,
    department_salary_expense_report,
    monthly_payroll_report,
    salary_hold_report,
)


REPORT_DEFINITIONS = [
    {
        'slug': 'class-strength',
        'title': 'Class Strength Report',
        'category': 'Academic',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': class_strength_report,
    },
    {
        'slug': 'subject-performance',
        'title': 'Subject-wise Performance',
        'category': 'Academic',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': subject_performance_report,
    },
    {
        'slug': 'student-results',
        'title': 'Student Result Report',
        'category': 'Academic',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': student_result_report,
    },
    {
        'slug': 'top-performers',
        'title': 'Top Performers',
        'category': 'Academic',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': top_performers_report,
    },
    {
        'slug': 'failures',
        'title': 'Failures List',
        'category': 'Academic',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': failures_report,
    },
    {
        'slug': 'grade-distribution',
        'title': 'Grade Distribution',
        'category': 'Academic',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': grade_distribution_report,
    },
    {
        'slug': 'daily-attendance',
        'title': 'Daily Attendance',
        'category': 'Attendance',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': daily_attendance_report,
    },
    {
        'slug': 'monthly-class-attendance',
        'title': 'Monthly Class Attendance',
        'category': 'Attendance',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': monthly_class_attendance_report,
    },
    {
        'slug': 'student-attendance-percentage',
        'title': 'Student Attendance Percentage',
        'category': 'Attendance',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': student_attendance_percentage_report,
    },
    {
        'slug': 'below-threshold',
        'title': 'Below 75% Alerts',
        'category': 'Attendance',
        'roles': {'schooladmin', 'principal', 'teacher'},
        'builder': below_threshold_alert_report,
    },
    {
        'slug': 'staff-attendance',
        'title': 'Staff Attendance',
        'category': 'Attendance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': staff_attendance_report,
    },
    {
        'slug': 'fee-collection',
        'title': 'Fee Collection',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': fee_collection_report,
    },
    {
        'slug': 'installment-collection',
        'title': 'Installment-wise Collection',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': installment_collection_report,
    },
    {
        'slug': 'pending-dues',
        'title': 'Pending Dues',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': pending_dues_report,
    },
    {
        'slug': 'concessions',
        'title': 'Concession Report',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': concession_report,
    },
    {
        'slug': 'refunds',
        'title': 'Refund Report',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': refund_report,
    },
    {
        'slug': 'monthly-income',
        'title': 'Monthly Income Summary',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': monthly_income_summary,
    },
    {
        'slug': 'expenses',
        'title': 'Expense Summary',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': expense_summary,
    },
    {
        'slug': 'profit-loss',
        'title': 'Profit & Loss',
        'category': 'Finance',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': profit_loss_summary,
    },
    {
        'slug': 'monthly-payroll',
        'title': 'Monthly Payroll',
        'category': 'Payroll',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': monthly_payroll_report,
    },
    {
        'slug': 'department-salary-expense',
        'title': 'Department Salary Expense',
        'category': 'Payroll',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': department_salary_expense_report,
    },
    {
        'slug': 'advance-salary',
        'title': 'Advance Salary',
        'category': 'Payroll',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': advance_salary_report,
    },
    {
        'slug': 'salary-hold',
        'title': 'Salary Hold',
        'category': 'Payroll',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': salary_hold_report,
    },
    {
        'slug': 'annual-salary',
        'title': 'Annual Salary Summary',
        'category': 'Payroll',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': annual_salary_summary,
    },
    {
        'slug': 'route-students',
        'title': 'Route-wise Student List',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': route_student_list_report,
    },
    {
        'slug': 'vehicle-occupancy',
        'title': 'Vehicle Occupancy',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': vehicle_occupancy_summary_report,
    },
    {
        'slug': 'transport-fee-collection',
        'title': 'Transport Fee Collection',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': transport_fee_collection_report,
    },
    {
        'slug': 'assets',
        'title': 'Asset Report',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': asset_report,
    },
    {
        'slug': 'low-stock',
        'title': 'Low Stock',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': low_stock_report,
    },
    {
        'slug': 'purchases',
        'title': 'Purchase Report',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': purchase_report,
    },
    {
        'slug': 'library-overdue',
        'title': 'Library Overdue',
        'category': 'Transport & Inventory',
        'roles': {'schooladmin', 'principal', 'accountant'},
        'builder': library_overdue_report,
    },
]

REPORT_LOOKUP = {row['slug']: row for row in REPORT_DEFINITIONS}


def _allowed(report_definition, role):
    return role in report_definition['roles']


def _base_query_string(request):
    query = request.GET.copy()
    query.pop('page', None)
    query.pop('export', None)
    return query.urlencode()


@login_required
def report_index(request):
    if request.user.role not in {'schooladmin', 'principal', 'accountant', 'teacher'}:
        return render(request, 'reports/forbidden.html', status=403)

    grouped = OrderedDict()
    for row in REPORT_DEFINITIONS:
        if not _allowed(row, request.user.role):
            continue
        grouped.setdefault(row['category'], []).append(row)

    return render(request, 'reports/index.html', {
        'report_groups': grouped,
    })


@login_required
def report_detail(request, slug):
    report_definition = REPORT_LOOKUP.get(slug)
    if not report_definition:
        raise Http404('Report not found.')

    if not _allowed(report_definition, request.user.role):
        return render(request, 'reports/forbidden.html', status=403)

    if not getattr(request.user, 'school_id', None):
        return render(request, 'reports/forbidden.html', status=403)

    filters = build_report_filters(request, request.user.school)
    report = report_definition['builder'](filters)

    if filters.export_format:
        if filters.read_only:
            return render(request, 'reports/forbidden.html', {
                'message': 'Locked sessions allow view-only access. Export is disabled.',
            }, status=403)
        response = export_response(report, filters.export_format)
        if response is not None:
            return response

    paginator = Paginator(report['rows'], 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    query_string = _base_query_string(request)

    return render(request, 'reports/detail.html', {
        'report_definition': report_definition,
        'report': report,
        'page_obj': page_obj,
        'display_rows': page_obj.object_list,
        'filters': filters,
        'query_string': query_string,
        'export_pdf_query': f"{query_string}&export=pdf" if query_string else 'export=pdf',
        'export_xlsx_query': f"{query_string}&export=xlsx" if query_string else 'export=xlsx',
    })
