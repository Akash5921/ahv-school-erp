import csv

from PIL import Image, ImageDraw
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.students.models import image_to_pdf_bytes
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    AssetForm,
    BookForm,
    BookIssueForm,
    BookReturnForm,
    PurchaseEntryForm,
    StockItemForm,
    VendorForm,
)
from .models import Asset, Book, BookIssue, Purchase, StockItem, Vendor
from .services import (
    issue_book,
    low_stock_items,
    record_purchase,
    return_book,
    vendor_purchase_totals,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('session') or request.POST.get('filter_session')
    selected_session = None
    if session_id and str(session_id).isdigit():
        selected_session = sessions.filter(id=int(session_id)).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()
    return sessions, selected_session


def _export_csv_response(filename, headers, rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def _export_pdf_response(filename, title, headers, rows):
    width = 1240
    per_page = 40
    pages = []
    all_rows = list(rows)
    if not all_rows:
        all_rows = [['No data available']]
        headers = []

    for start in range(0, len(all_rows), per_page):
        chunk = all_rows[start:start + per_page]
        height = 220 + (len(chunk) + 1) * 34
        if height < 700:
            height = 700
        page = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(page)
        draw.rectangle((20, 20, width - 20, height - 20), outline='black', width=2)
        draw.text((40, 40), title, fill='black')
        y = 90
        if headers:
            draw.text((40, y), ' | '.join(headers), fill='black')
            y += 30
            draw.line((40, y, width - 40, y), fill='black')
            y += 15
        for row in chunk:
            draw.text((40, y), ' | '.join(str(col) for col in row), fill='black')
            y += 30
        pages.append(page)

    pdf_bytes = image_to_pdf_bytes(pages)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@role_required('schooladmin')
def inventory_asset_list(request):
    school = request.user.school
    if request.method == 'POST':
        form = AssetForm(request.POST, school=school)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='inventory.asset_saved',
                school=school,
                target=row,
                details=f"Asset={row.asset_code}",
            )
            messages.success(request, 'Asset saved successfully.')
            return redirect('inventory_asset_list_core')
    else:
        form = AssetForm(school=school)

    rows = Asset.objects.filter(school=school).select_related('assigned_to', 'assigned_to__user').order_by('asset_name')
    return render(request, 'inventory_core/asset_list.html', {
        'rows': rows,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def inventory_asset_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Asset, pk=pk, school=school)

    if request.method == 'POST':
        form = AssetForm(request.POST, instance=row, school=school)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='inventory.asset_updated',
                school=school,
                target=row,
                details=f"Asset={row.asset_code}",
            )
            messages.success(request, 'Asset updated successfully.')
            return redirect('inventory_asset_list_core')
    else:
        form = AssetForm(instance=row, school=school)

    return render(request, 'inventory_core/asset_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def inventory_asset_deactivate(request, pk):
    row = get_object_or_404(Asset, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='inventory.asset_deactivated',
        school=request.user.school,
        target=row,
        details=f"Asset={row.asset_code}",
    )
    messages.success(request, 'Asset deactivated successfully.')
    return redirect('inventory_asset_list_core')


@login_required
@role_required('schooladmin')
def inventory_stock_list(request):
    school = request.user.school
    if request.method == 'POST':
        form = StockItemForm(request.POST)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='inventory.stock_saved',
                school=school,
                target=row,
                details=f"Stock={row.item_code}",
            )
            messages.success(request, 'Stock item saved successfully.')
            return redirect('inventory_stock_list_core')
    else:
        form = StockItemForm()

    rows = StockItem.objects.filter(school=school).order_by('item_name')
    return render(request, 'inventory_core/stock_list.html', {
        'rows': rows,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def inventory_stock_update(request, pk):
    school = request.user.school
    row = get_object_or_404(StockItem, pk=pk, school=school)

    if request.method == 'POST':
        form = StockItemForm(request.POST, instance=row)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='inventory.stock_updated',
                school=school,
                target=row,
                details=f"Stock={row.item_code}",
            )
            messages.success(request, 'Stock item updated successfully.')
            return redirect('inventory_stock_list_core')
    else:
        form = StockItemForm(instance=row)

    return render(request, 'inventory_core/stock_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def inventory_stock_deactivate(request, pk):
    row = get_object_or_404(StockItem, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='inventory.stock_deactivated',
        school=request.user.school,
        target=row,
        details=f"Stock={row.item_code}",
    )
    messages.success(request, 'Stock item deactivated successfully.')
    return redirect('inventory_stock_list_core')


@login_required
@role_required('schooladmin')
def inventory_vendor_list(request):
    school = request.user.school
    if request.method == 'POST':
        form = VendorForm(request.POST)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='inventory.vendor_saved',
                school=school,
                target=row,
                details=f"Vendor={row.vendor_name}",
            )
            messages.success(request, 'Vendor saved successfully.')
            return redirect('inventory_vendor_list_core')
    else:
        form = VendorForm()

    rows = Vendor.objects.filter(school=school).order_by('vendor_name')
    return render(request, 'inventory_core/vendor_list.html', {
        'rows': rows,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def inventory_vendor_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Vendor, pk=pk, school=school)

    if request.method == 'POST':
        form = VendorForm(request.POST, instance=row)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='inventory.vendor_updated',
                school=school,
                target=row,
                details=f"Vendor={row.vendor_name}",
            )
            messages.success(request, 'Vendor updated successfully.')
            return redirect('inventory_vendor_list_core')
    else:
        form = VendorForm(instance=row)

    return render(request, 'inventory_core/vendor_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def inventory_vendor_deactivate(request, pk):
    row = get_object_or_404(Vendor, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='inventory.vendor_deactivated',
        school=request.user.school,
        target=row,
        details=f"Vendor={row.vendor_name}",
    )
    messages.success(request, 'Vendor deactivated successfully.')
    return redirect('inventory_vendor_list_core')


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_purchase_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    form = PurchaseEntryForm(request.POST or None, school=school, default_session=selected_session)
    if request.method == 'POST' and form.is_valid():
        try:
            purchase, _ = record_purchase(
                school=school,
                session=form.cleaned_data['session'],
                vendor=form.cleaned_data['vendor'],
                purchase_date=form.cleaned_data['purchase_date'],
                invoice_number=form.cleaned_data['invoice_number'],
                items=[{
                    'stock_item': form.cleaned_data['stock_item'],
                    'quantity': form.cleaned_data['quantity'],
                    'unit_price': form.cleaned_data['unit_price'],
                }],
                created_by=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            log_audit_event(
                request=request,
                action='inventory.purchase_recorded',
                school=school,
                target=purchase,
                details=f"Invoice={purchase.invoice_number}, Amount={purchase.total_amount}",
            )
            messages.success(request, 'Purchase recorded successfully.')
            return redirect(f"{reverse('inventory_purchase_list_core')}?session={purchase.session_id}")

    rows = Purchase.objects.filter(school=school).select_related('session', 'vendor', 'created_by')
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'inventory_core/purchase_list.html', {
        'rows': rows.order_by('-purchase_date', '-id')[:200],
        'form': form,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def inventory_book_list(request):
    school = request.user.school
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='inventory.book_saved',
                school=school,
                target=row,
                details=f"Book={row.title}",
            )
            messages.success(request, 'Book saved successfully.')
            return redirect('inventory_book_list_core')
    else:
        form = BookForm()

    rows = Book.objects.filter(school=school).order_by('title')
    return render(request, 'inventory_core/book_list.html', {
        'rows': rows,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def inventory_book_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Book, pk=pk, school=school)

    if request.method == 'POST':
        form = BookForm(request.POST, instance=row)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='inventory.book_updated',
                school=school,
                target=row,
                details=f"Book={row.title}",
            )
            messages.success(request, 'Book updated successfully.')
            return redirect('inventory_book_list_core')
    else:
        form = BookForm(instance=row)

    return render(request, 'inventory_core/book_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def inventory_book_deactivate(request, pk):
    row = get_object_or_404(Book, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='inventory.book_deactivated',
        school=request.user.school,
        target=row,
        details=f"Book={row.title}",
    )
    messages.success(request, 'Book deactivated successfully.')
    return redirect('inventory_book_list_core')


@login_required
@role_required('schooladmin')
def inventory_book_issue_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    issue_form = BookIssueForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'issue' else None,
        school=school,
        default_session=selected_session,
    )
    return_form = BookReturnForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'return' else None
    )

    if request.method == 'POST' and request.POST.get('action') == 'issue':
        if issue_form.is_valid():
            try:
                issue = issue_book(
                    school=school,
                    session=issue_form.cleaned_data['session'],
                    book=issue_form.cleaned_data['book'],
                    issued_student=issue_form.cleaned_data['issued_student'],
                    issued_staff=issue_form.cleaned_data['issued_staff'],
                    issue_date=issue_form.cleaned_data['issue_date'],
                    due_date=issue_form.cleaned_data['due_date'],
                    issued_by=request.user,
                )
            except ValidationError as exc:
                issue_form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='inventory.book_issued',
                    school=school,
                    target=issue,
                    details=f"Book={issue.book_id}, Session={issue.session_id}",
                )
                messages.success(request, 'Book issued successfully.')
                return redirect(f"{reverse('inventory_book_issue_list_core')}?session={issue.session_id}")

    if request.method == 'POST' and request.POST.get('action') == 'return':
        issue = get_object_or_404(BookIssue, pk=request.POST.get('issue_id'), school=school)
        if return_form.is_valid():
            try:
                issue, _ = return_book(
                    issue=issue,
                    return_date=return_form.cleaned_data['return_date'],
                    fine_per_day=return_form.cleaned_data['fine_per_day'],
                    returned_by=request.user,
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='inventory.book_returned',
                    school=school,
                    target=issue,
                    details=f"Issue={issue.id}, Fine={issue.fine_amount}",
                )
                messages.success(request, 'Book returned successfully.')
        return redirect('inventory_book_issue_list_core')

    rows = BookIssue.objects.filter(school=school).select_related(
        'session',
        'book',
        'issued_student',
        'issued_staff',
        'issued_staff__user',
    )
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'inventory_core/book_issue_list.html', {
        'rows': rows.order_by('-issue_date', '-id'),
        'sessions': sessions,
        'selected_session': selected_session,
        'issue_form': issue_form,
        'return_form': return_form,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_report_assets(request):
    rows = Asset.objects.filter(school=request.user.school).select_related('assigned_to', 'assigned_to__user').order_by('asset_name')
    export = request.GET.get('export')
    headers = ['Asset Code', 'Asset', 'Category', 'Condition', 'Location', 'Assigned To', 'Active']
    data = [
        [
            row.asset_code,
            row.asset_name,
            row.category,
            row.get_condition_display(),
            row.location or '-',
            row.assigned_to.user.get_full_name() if row.assigned_to_id else '-',
            row.is_active,
        ]
        for row in rows
    ]
    if export == 'csv':
        return _export_csv_response('inventory_assets.csv', headers, data)
    if export == 'pdf':
        return _export_pdf_response('inventory_assets.pdf', 'Asset Report', headers, data)
    return render(request, 'inventory_core/report_assets.html', {'rows': rows})


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_report_low_stock(request):
    rows = low_stock_items(school=request.user.school)
    export = request.GET.get('export')
    headers = ['Item Code', 'Item', 'Category', 'Available', 'Threshold']
    data = [
        [row.item_code, row.item_name, row.category, row.quantity_available, row.minimum_threshold]
        for row in rows
    ]
    if export == 'csv':
        return _export_csv_response('inventory_low_stock.csv', headers, data)
    if export == 'pdf':
        return _export_pdf_response('inventory_low_stock.pdf', 'Low Stock Alert Report', headers, data)
    return render(request, 'inventory_core/report_low_stock.html', {'rows': rows})


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_report_purchases(request):
    sessions, selected_session = _resolve_selected_session(request, request.user.school)
    rows = Purchase.objects.filter(school=request.user.school).select_related('session', 'vendor')
    if selected_session:
        rows = rows.filter(session=selected_session)
    rows = rows.order_by('-purchase_date', '-id')

    export = request.GET.get('export')
    headers = ['Date', 'Invoice', 'Session', 'Vendor', 'Amount']
    data = [[row.purchase_date, row.invoice_number, row.session.name, row.vendor.vendor_name, row.total_amount] for row in rows]
    if export == 'csv':
        return _export_csv_response('inventory_purchases.csv', headers, data)
    if export == 'pdf':
        return _export_pdf_response('inventory_purchases.pdf', 'Purchase Report', headers, data)

    return render(request, 'inventory_core/report_purchases.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_report_vendor(request):
    sessions, selected_session = _resolve_selected_session(request, request.user.school)
    totals = vendor_purchase_totals(school=request.user.school, session=selected_session)

    export = request.GET.get('export')
    headers = ['Vendor', 'Total Purchase']
    data = [[row['vendor__vendor_name'], row['total']] for row in totals]
    if export == 'csv':
        return _export_csv_response('inventory_vendor_totals.csv', headers, data)
    if export == 'pdf':
        return _export_pdf_response('inventory_vendor_totals.pdf', 'Vendor Purchase Report', headers, data)

    return render(request, 'inventory_core/report_vendor.html', {
        'rows': totals,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_report_library(request):
    sessions, selected_session = _resolve_selected_session(request, request.user.school)
    rows = BookIssue.objects.filter(school=request.user.school).select_related('session', 'book', 'issued_student', 'issued_staff', 'issued_staff__user')
    if selected_session:
        rows = rows.filter(session=selected_session)
    rows = rows.order_by('-issue_date', '-id')

    export = request.GET.get('export')
    headers = ['Book', 'Issued To', 'Issue Date', 'Due Date', 'Return Date', 'Fine']
    data = [[row.book.title, row.issued_to_display, row.issue_date, row.due_date, row.return_date or '-', row.fine_amount] for row in rows]
    if export == 'csv':
        return _export_csv_response('inventory_library_issues.csv', headers, data)
    if export == 'pdf':
        return _export_pdf_response('inventory_library_issues.pdf', 'Library Issue Report', headers, data)

    return render(request, 'inventory_core/report_library.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def inventory_report_overdue(request):
    sessions, selected_session = _resolve_selected_session(request, request.user.school)
    today = timezone.localdate()
    rows = BookIssue.objects.filter(
        school=request.user.school,
        return_date__isnull=True,
        due_date__lt=today,
    ).select_related('session', 'book', 'issued_student', 'issued_staff', 'issued_staff__user')
    if selected_session:
        rows = rows.filter(session=selected_session)
    rows = rows.order_by('due_date', 'id')
    rows = list(rows)
    for row in rows:
        row.days_overdue = (today - row.due_date).days

    export = request.GET.get('export')
    headers = ['Book', 'Issued To', 'Session', 'Issue Date', 'Due Date', 'Days Overdue']
    data = [[row.book.title, row.issued_to_display, row.session.name, row.issue_date, row.due_date, row.days_overdue] for row in rows]
    if export == 'csv':
        return _export_csv_response('inventory_overdue_books.csv', headers, data)
    if export == 'pdf':
        return _export_pdf_response('inventory_overdue_books.pdf', 'Overdue Book Report', headers, data)

    return render(request, 'inventory_core/report_overdue.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
        'today': today,
    })
