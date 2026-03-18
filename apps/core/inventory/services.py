from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.core.fees.models import LedgerEntry

from .models import Book, BookIssue, Purchase, PurchaseItem, StockItem


def _to_decimal(value) -> Decimal:
    return Decimal(str(value or '0'))


def _quantize(value) -> Decimal:
    return _to_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _ledger_create(*, school, session, transaction_type, reference_model, reference_id, amount, date, created_by=None, description=''):
    entry, _ = LedgerEntry.objects.get_or_create(
        school=school,
        transaction_type=transaction_type,
        reference_model=reference_model,
        reference_id=str(reference_id),
        defaults={
            'session': session,
            'amount': _quantize(amount),
            'date': date,
            'description': (description or '')[:255],
            'created_by': created_by,
        },
    )
    return entry


@transaction.atomic
def record_purchase(
    *,
    school,
    session,
    vendor,
    purchase_date,
    invoice_number,
    items,
    created_by=None,
):
    if session.school_id != school.id:
        raise ValidationError('Session does not belong to selected school.')
    if vendor.school_id != school.id:
        raise ValidationError('Vendor does not belong to selected school.')

    items = list(items or [])
    if not items:
        raise ValidationError('At least one purchase item is required.')

    purchase = Purchase.objects.create(
        school=school,
        session=session,
        vendor=vendor,
        purchase_date=purchase_date or timezone.localdate(),
        invoice_number=(invoice_number or '').strip(),
        created_by=created_by,
        total_amount=Decimal('0.00'),
    )

    total = Decimal('0.00')
    for item_row in items:
        stock_item = item_row['stock_item']
        quantity = int(item_row['quantity'])
        unit_price = _quantize(item_row['unit_price'])

        if quantity <= 0:
            raise ValidationError('Purchase quantity must be greater than zero.')
        if unit_price <= 0:
            raise ValidationError('Unit price must be greater than zero.')
        if stock_item.school_id != school.id:
            raise ValidationError('Stock item does not belong to selected school.')
        if not stock_item.is_active:
            raise ValidationError('Inactive stock item cannot be purchased.')

        stock_lock = StockItem.objects.select_for_update().get(pk=stock_item.id)
        stock_lock.quantity_available += quantity
        stock_lock.full_clean()
        stock_lock.save(update_fields=['quantity_available', 'updated_at'])

        purchase_item = PurchaseItem(
            purchase=purchase,
            stock_item=stock_item,
            quantity=quantity,
            unit_price=unit_price,
        )
        purchase_item.full_clean()
        purchase_item.save()

        total += _quantize(quantity * unit_price)

    purchase.total_amount = _quantize(total)
    purchase.full_clean()
    purchase.save(update_fields=['total_amount', 'updated_at'])

    ledger_entry = _ledger_create(
        school=school,
        session=session,
        transaction_type=LedgerEntry.TYPE_EXPENSE,
        reference_model='Purchase',
        reference_id=purchase.id,
        amount=purchase.total_amount,
        date=purchase.purchase_date,
        created_by=created_by,
        description=f"Inventory purchase invoice {purchase.invoice_number}",
    )

    return purchase, ledger_entry


@transaction.atomic
def issue_book(
    *,
    school,
    session,
    book: Book,
    issued_student=None,
    issued_staff=None,
    issue_date=None,
    due_date=None,
    issued_by=None,
):
    if session.school_id != school.id:
        raise ValidationError('Session does not belong to selected school.')
    if book.school_id != school.id:
        raise ValidationError('Book does not belong to selected school.')
    if not book.is_active:
        raise ValidationError('Inactive book cannot be issued.')

    has_student = issued_student is not None
    has_staff = issued_staff is not None
    if has_student == has_staff:
        raise ValidationError('Select either student or staff recipient.')

    if issued_student and (issued_student.school_id != school.id or issued_student.session_id != session.id):
        raise ValidationError('Student does not belong to selected school-session.')
    if issued_staff and issued_staff.school_id != school.id:
        raise ValidationError('Staff does not belong to selected school.')

    issue_date = issue_date or timezone.localdate()
    due_date = due_date or issue_date
    if due_date < issue_date:
        raise ValidationError('Due date cannot be earlier than issue date.')

    locked_book = Book.objects.select_for_update().get(pk=book.id)
    if locked_book.available_copies <= 0:
        raise ValidationError('No available copies for selected book.')

    issue = BookIssue.objects.create(
        school=school,
        session=session,
        book=locked_book,
        issued_student=issued_student,
        issued_staff=issued_staff,
        issue_date=issue_date,
        due_date=due_date,
        issued_by=issued_by,
        is_active=True,
    )

    locked_book.available_copies -= 1
    locked_book.full_clean()
    locked_book.save(update_fields=['available_copies', 'updated_at'])
    return issue


@transaction.atomic
def return_book(*, issue: BookIssue, return_date=None, fine_per_day=Decimal('5.00'), returned_by=None):
    if issue.return_date:
        raise ValidationError('Book issue is already closed.')

    return_date = return_date or timezone.localdate()
    if return_date < issue.issue_date:
        raise ValidationError('Return date cannot be earlier than issue date.')

    days_late = 0
    if return_date > issue.due_date:
        days_late = (return_date - issue.due_date).days
    fine = _quantize(_to_decimal(days_late) * _to_decimal(fine_per_day))

    issue.return_date = return_date
    issue.fine_amount = fine
    issue.returned_by = returned_by
    issue.is_active = False
    issue.full_clean()
    issue.save(update_fields=['return_date', 'fine_amount', 'returned_by', 'is_active', 'updated_at'])

    locked_book = Book.objects.select_for_update().get(pk=issue.book_id)
    locked_book.available_copies += 1
    if locked_book.available_copies > locked_book.total_copies:
        locked_book.available_copies = locked_book.total_copies
    locked_book.full_clean()
    locked_book.save(update_fields=['available_copies', 'updated_at'])

    fine_ledger = None
    if fine > 0:
        fine_ledger = _ledger_create(
            school=issue.school,
            session=issue.session,
            transaction_type=LedgerEntry.TYPE_INCOME,
            reference_model='BookIssue',
            reference_id=f'{issue.id}:fine',
            amount=fine,
            date=return_date,
            created_by=returned_by,
            description=f"Library fine for issue #{issue.id}",
        )

    return issue, fine_ledger


def low_stock_items(*, school):
    return list(
        StockItem.objects.filter(
            school=school,
            is_active=True,
            quantity_available__lt=F('minimum_threshold'),
        ).order_by('item_name')
    )


def vendor_purchase_totals(*, school, session=None):
    rows = Purchase.objects.filter(school=school)
    if session:
        rows = rows.filter(session=session)
    return list(
        rows.values('vendor__vendor_name').annotate(total=Sum('total_amount')).order_by('-total', 'vendor__vendor_name')
    )
