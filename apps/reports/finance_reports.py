from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.core.fees.models import FeePayment, FeeRefund, LedgerEntry, StudentConcession, StudentFee
from apps.core.fees.services import student_outstanding_summary

from .filters import scoped_students


def _report(title, columns, rows, summary):
    return {
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
    }


def _money(value):
    return Decimal(str(value or '0')).quantize(Decimal('0.01'))


def fee_collection_report(filters):
    entries = LedgerEntry.objects.filter(
        school=filters.school,
        transaction_type=LedgerEntry.TYPE_INCOME,
        reference_model='FeePayment',
        date__range=(filters.date_from, filters.date_to),
    )
    if filters.session:
        entries = entries.filter(session=filters.session)

    grouped = entries.values('date').annotate(total=Sum('amount'), entry_count=Count('id')).order_by('date')
    rows = [[row['date'], _money(row['total']), row['entry_count']] for row in grouped]
    return _report(
        'Fee Collection Report',
        ['Date', 'Collected Amount', 'Ledger Entries'],
        rows,
        [('Collected Total', sum((row[1] for row in rows), Decimal('0.00')))],
    )


def installment_collection_report(filters):
    payments = FeePayment.objects.filter(
        school=filters.school,
        payment_date__range=(filters.date_from, filters.date_to),
        is_reversed=False,
    ).select_related('installment')
    if filters.session:
        payments = payments.filter(session=filters.session)

    grouped = payments.values('installment__name').annotate(
        principal=Sum('amount_paid'),
        fine=Sum('fine_amount'),
        payment_count=Count('id'),
    ).order_by('installment__name')
    rows = [[
        row['installment__name'],
        _money(row['principal']),
        _money(row['fine']),
        _money(_money(row['principal']) + _money(row['fine'])),
        row['payment_count'],
    ] for row in grouped]
    return _report(
        'Installment-wise Collection Report',
        ['Installment', 'Principal', 'Fine', 'Total', 'Payments'],
        rows,
        [('Installments', len(rows))],
    )


def pending_dues_report(filters):
    students = scoped_students(filters)
    rows = []
    for student in students:
        if not filters.session:
            continue
        summary = student_outstanding_summary(student=student, session=filters.session)
        if summary['total_due'] <= 0:
            continue
        rows.append([
            student.admission_number,
            student.full_name,
            student.current_class.name if student.current_class_id else '-',
            student.current_section.name if student.current_section_id else '-',
            summary['principal_due'],
            summary['fine_due'],
            summary['total_due'],
        ])
    return _report(
        'Pending Dues Report',
        ['Admission No', 'Student', 'Class', 'Section', 'Principal Due', 'Fine Due', 'Total Due'],
        rows,
        [('Students With Dues', len(rows)), ('Total Pending', sum((row[6] for row in rows), Decimal('0.00')))],
    )


def concession_report(filters):
    concessions = StudentConcession.objects.filter(
        school=filters.school,
        is_active=True,
    ).select_related('student', 'fee_type', 'approved_by')
    if filters.session:
        concessions = concessions.filter(session=filters.session)
    if filters.student:
        concessions = concessions.filter(student=filters.student)
    if filters.school_class:
        concessions = concessions.filter(student__current_class=filters.school_class)
    if filters.section:
        concessions = concessions.filter(student__current_section=filters.section)

    rows = [[
        row.student.admission_number,
        row.student.full_name,
        row.fee_type.name if row.fee_type_id else 'All Fee Types',
        row.percentage if row.percentage is not None else '-',
        row.fixed_amount if row.fixed_amount is not None else '-',
        row.reason or '-',
    ] for row in concessions.order_by('-created_at')]
    return _report(
        'Concession Report',
        ['Admission No', 'Student', 'Fee Type', 'Percentage', 'Fixed Amount', 'Reason'],
        rows,
        [('Concessions', len(rows))],
    )


def refund_report(filters):
    refunds = FeeRefund.objects.filter(
        school=filters.school,
        refund_date__range=(filters.date_from, filters.date_to),
    ).select_related('student', 'payment')
    if filters.session:
        refunds = refunds.filter(session=filters.session)

    rows = [[
        row.refund_date,
        row.student.admission_number,
        row.student.full_name,
        row.payment_id,
        row.refund_amount,
        row.reason,
        'Reversed' if row.is_reversed else 'Active',
    ] for row in refunds.order_by('-refund_date', '-id')]
    return _report(
        'Refund Report',
        ['Date', 'Admission No', 'Student', 'Payment ID', 'Refund Amount', 'Reason', 'Status'],
        rows,
        [('Refund Total', sum((row[4] for row in rows), Decimal('0.00')))],
    )


def monthly_income_summary(filters):
    entries = LedgerEntry.objects.filter(
        school=filters.school,
        transaction_type=LedgerEntry.TYPE_INCOME,
    )
    if filters.session:
        entries = entries.filter(session=filters.session)

    grouped = entries.annotate(month_bucket=TruncMonth('date')).values('month_bucket').annotate(
        total=Sum('amount'),
    ).order_by('month_bucket')
    rows = [[row['month_bucket'].date().strftime('%b %Y'), _money(row['total'])] for row in grouped if row['month_bucket']]
    return _report(
        'Monthly Income Summary',
        ['Month', 'Income'],
        rows,
        [('Income Total', sum((row[1] for row in rows), Decimal('0.00')))],
    )


def expense_summary(filters):
    entries = LedgerEntry.objects.filter(
        school=filters.school,
        transaction_type__in=[LedgerEntry.TYPE_EXPENSE, LedgerEntry.TYPE_REFUND],
    )
    if filters.session:
        entries = entries.filter(session=filters.session)

    grouped = entries.values('reference_model').annotate(total=Sum('amount')).order_by('reference_model')
    rows = [[row['reference_model'], _money(row['total'])] for row in grouped]
    return _report(
        'Expense Summary',
        ['Reference Model', 'Amount'],
        rows,
        [('Expense Total', sum((row[1] for row in rows), Decimal('0.00')))],
    )


def profit_loss_summary(filters):
    income_entries = LedgerEntry.objects.filter(
        school=filters.school,
        transaction_type=LedgerEntry.TYPE_INCOME,
    )
    expense_entries = LedgerEntry.objects.filter(
        school=filters.school,
        transaction_type__in=[LedgerEntry.TYPE_EXPENSE, LedgerEntry.TYPE_REFUND],
    )
    if filters.session:
        income_entries = income_entries.filter(session=filters.session)
        expense_entries = expense_entries.filter(session=filters.session)

    income_lookup = {
        row['month_bucket'].date().strftime('%b %Y'): _money(row['total'])
        for row in income_entries.annotate(month_bucket=TruncMonth('date')).values('month_bucket').annotate(total=Sum('amount'))
        if row['month_bucket']
    }
    expense_lookup = {
        row['month_bucket'].date().strftime('%b %Y'): _money(row['total'])
        for row in expense_entries.annotate(month_bucket=TruncMonth('date')).values('month_bucket').annotate(total=Sum('amount'))
        if row['month_bucket']
    }
    months = sorted(set(income_lookup) | set(expense_lookup))
    rows = []
    for month in months:
        income = income_lookup.get(month, Decimal('0.00'))
        expense = expense_lookup.get(month, Decimal('0.00'))
        rows.append([month, income, expense, _money(income - expense)])
    return _report(
        'Profit & Loss Summary',
        ['Month', 'Income', 'Expense', 'Net'],
        rows,
        [('Net Total', sum((row[3] for row in rows), Decimal('0.00')))],
    )
