from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.core.fees.models import FeePaymentAllocation, StudentFee
from apps.core.inventory.models import Asset, BookIssue, Purchase
from apps.core.inventory.services import low_stock_items
from apps.core.transport.models import StudentTransport
from apps.core.transport.services import route_wise_students, vehicle_occupancy_report


def _report(title, columns, rows, summary):
    return {
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
    }


def _money(value):
    return Decimal(str(value or '0')).quantize(Decimal('0.01'))


def route_student_list_report(filters):
    rows_qs = route_wise_students(
        school=filters.school,
        session=filters.session,
    ) if filters.session else []
    if filters.school_class:
        rows_qs = [row for row in rows_qs if row.student.current_class_id == filters.school_class.id]
    if filters.section:
        rows_qs = [row for row in rows_qs if row.student.current_section_id == filters.section.id]
    if filters.student:
        rows_qs = [row for row in rows_qs if row.student_id == filters.student.id]

    rows = [[
        row.route.route_name,
        row.student.admission_number,
        row.student.full_name,
        row.stop_name,
        row.route.vehicle.vehicle_number,
        row.transport_fee,
    ] for row in rows_qs]
    return _report(
        'Route-wise Student List',
        ['Route', 'Admission No', 'Student', 'Stop', 'Vehicle', 'Transport Fee'],
        rows,
        [('Allocations', len(rows))],
    )


def vehicle_occupancy_summary_report(filters):
    rows_qs = vehicle_occupancy_report(
        school=filters.school,
        session=filters.session,
    ) if filters.session else []
    rows = [[
        row['vehicle'].vehicle_number,
        row['capacity'],
        row['occupied'],
        row['available'],
        row['occupancy_percent'],
    ] for row in rows_qs]
    return _report(
        'Vehicle Occupancy Report',
        ['Vehicle', 'Capacity', 'Occupied', 'Available', 'Occupancy %'],
        rows,
        [('Vehicles', len(rows))],
    )


def transport_fee_collection_report(filters):
    fees = StudentFee.objects.filter(
        school=filters.school,
        fee_type__category='transport',
        is_active=True,
    ).select_related('student', 'student__current_class', 'student__current_section')
    if filters.session:
        fees = fees.filter(session=filters.session)
    if filters.school_class:
        fees = fees.filter(student__current_class=filters.school_class)
    if filters.section:
        fees = fees.filter(student__current_section=filters.section)
    if filters.student:
        fees = fees.filter(student=filters.student)

    rows = []
    for fee in fees.order_by('student__admission_number'):
        paid = _money(
            FeePaymentAllocation.objects.filter(
                student_fee=fee,
                payment__is_reversed=False,
            ).aggregate(total=Sum('amount')).get('total')
        )
        pending = _money(max(_money(fee.final_amount) - paid, Decimal('0.00')))
        rows.append([
            fee.student.admission_number,
            fee.student.full_name,
            fee.final_amount,
            paid,
            pending,
        ])
    return _report(
        'Transport Fee Collection Report',
        ['Admission No', 'Student', 'Transport Fee', 'Collected', 'Pending'],
        rows,
        [('Pending Total', sum((row[4] for row in rows), Decimal('0.00')))],
    )


def asset_report(filters):
    assets = Asset.objects.filter(
        school=filters.school,
        is_active=True,
    ).select_related('assigned_to', 'assigned_to__user').order_by('asset_name')
    rows = [[
        row.asset_code,
        row.asset_name,
        row.category,
        row.purchase_date or '-',
        row.purchase_cost,
        row.location or '-',
        row.get_condition_display(),
        row.assigned_to.full_name if row.assigned_to_id else '-',
    ] for row in assets]
    return _report(
        'Asset Report',
        ['Asset Code', 'Asset Name', 'Category', 'Purchase Date', 'Cost', 'Location', 'Condition', 'Assigned To'],
        rows,
        [('Assets', len(rows))],
    )


def low_stock_report(filters):
    rows_qs = low_stock_items(school=filters.school)
    rows = [[
        row.item_code,
        row.item_name,
        row.category,
        row.quantity_available,
        row.minimum_threshold,
        row.unit_price,
    ] for row in rows_qs]
    return _report(
        'Low Stock Report',
        ['Item Code', 'Item Name', 'Category', 'Available', 'Minimum Threshold', 'Unit Price'],
        rows,
        [('Low Stock Items', len(rows))],
    )


def purchase_report(filters):
    purchases = Purchase.objects.filter(
        school=filters.school,
        purchase_date__range=(filters.date_from, filters.date_to),
    ).select_related('vendor', 'created_by')
    if filters.session:
        purchases = purchases.filter(session=filters.session)

    rows = [[
        row.purchase_date,
        row.invoice_number,
        row.vendor.vendor_name,
        row.total_amount,
        row.created_by.username if row.created_by_id else '-',
    ] for row in purchases.order_by('-purchase_date', '-id')]
    return _report(
        'Purchase Report',
        ['Purchase Date', 'Invoice Number', 'Vendor', 'Total Amount', 'Created By'],
        rows,
        [('Purchase Total', sum((row[3] for row in rows), Decimal('0.00')))],
    )


def library_overdue_report(filters):
    issues = BookIssue.objects.filter(
        school=filters.school,
        return_date__isnull=True,
        due_date__lt=timezone.localdate(),
    ).select_related('book', 'issued_student', 'issued_staff', 'issued_staff__user').order_by('due_date')
    if filters.session:
        issues = issues.filter(session=filters.session)

    rows = [[
        row.book.title,
        row.issued_to_display,
        row.issue_date,
        row.due_date,
        row.fine_amount,
    ] for row in issues]
    return _report(
        'Library Overdue Report',
        ['Book', 'Issued To', 'Issue Date', 'Due Date', 'Fine Amount'],
        rows,
        [('Overdue Issues', len(rows))],
    )
