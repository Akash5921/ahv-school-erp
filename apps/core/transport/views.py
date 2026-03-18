import csv
from datetime import timedelta

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

from .forms import DriverForm, RouteForm, RouteStopForm, StudentTransportForm, VehicleForm
from .models import Driver, Route, RouteStop, StudentTransport, Vehicle
from .services import (
    assign_student_transport,
    deactivate_student_transport,
    driver_allocation_report,
    insurance_expiry_report,
    route_wise_students,
    transport_fee_pending_report,
    vehicle_occupancy_report,
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
def transport_driver_list(request):
    school = request.user.school

    if request.method == 'POST':
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save(commit=False)
            driver.school = school
            driver.save()
            log_audit_event(
                request=request,
                action='transport.driver_saved',
                school=school,
                target=driver,
                details=f"Driver={driver.name}",
            )
            messages.success(request, 'Driver saved successfully.')
            return redirect('transport_driver_list_core')
    else:
        form = DriverForm()

    rows = Driver.objects.filter(school=school).order_by('name')
    return render(request, 'transport_core/driver_list.html', {
        'rows': rows,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def transport_driver_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Driver, pk=pk, school=school)

    if request.method == 'POST':
        form = DriverForm(request.POST, instance=row)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='transport.driver_updated',
                school=school,
                target=row,
                details=f"Driver={row.name}",
            )
            messages.success(request, 'Driver updated successfully.')
            return redirect('transport_driver_list_core')
    else:
        form = DriverForm(instance=row)

    return render(request, 'transport_core/driver_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def transport_driver_deactivate(request, pk):
    row = get_object_or_404(Driver, pk=pk, school=request.user.school)
    try:
        row.delete()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='transport.driver_deactivated',
            school=request.user.school,
            target=row,
            details=f"Driver={row.name}",
        )
        messages.success(request, 'Driver deactivated successfully.')
    return redirect('transport_driver_list_core')


@login_required
@role_required('schooladmin')
def transport_vehicle_list(request):
    school = request.user.school

    if request.method == 'POST':
        form = VehicleForm(request.POST, school=school)
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='transport.vehicle_saved',
                school=school,
                target=row,
                details=f"Vehicle={row.vehicle_number}",
            )
            messages.success(request, 'Vehicle saved successfully.')
            return redirect('transport_vehicle_list_core')
    else:
        form = VehicleForm(school=school)

    rows = Vehicle.objects.filter(school=school).select_related('assigned_driver').order_by('vehicle_number')
    return render(request, 'transport_core/vehicle_list.html', {
        'rows': rows,
        'form': form,
    })


@login_required
@role_required('schooladmin')
def transport_vehicle_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Vehicle, pk=pk, school=school)

    if request.method == 'POST':
        form = VehicleForm(request.POST, instance=row, school=school)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='transport.vehicle_updated',
                school=school,
                target=row,
                details=f"Vehicle={row.vehicle_number}",
            )
            messages.success(request, 'Vehicle updated successfully.')
            return redirect('transport_vehicle_list_core')
    else:
        form = VehicleForm(instance=row, school=school)

    return render(request, 'transport_core/vehicle_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def transport_vehicle_deactivate(request, pk):
    row = get_object_or_404(Vehicle, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='transport.vehicle_deactivated',
        school=request.user.school,
        target=row,
        details=f"Vehicle={row.vehicle_number}",
    )
    messages.success(request, 'Vehicle deactivated successfully.')
    return redirect('transport_vehicle_list_core')


@login_required
@role_required('schooladmin')
def transport_route_list(request):
    school = request.user.school
    route_form = RouteForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'add_route' else None,
        school=school,
    )
    stop_form = RouteStopForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'add_stop' else None,
        school=school,
    )

    if request.method == 'POST' and request.POST.get('action') == 'add_route':
        if route_form.is_valid():
            row = route_form.save(commit=False)
            row.school = school
            row.save()
            log_audit_event(
                request=request,
                action='transport.route_saved',
                school=school,
                target=row,
                details=f"Route={row.route_name}",
            )
            messages.success(request, 'Route saved successfully.')
            return redirect('transport_route_list_core')

    if request.method == 'POST' and request.POST.get('action') == 'add_stop':
        if stop_form.is_valid():
            row = stop_form.save()
            log_audit_event(
                request=request,
                action='transport.route_stop_saved',
                school=school,
                target=row,
                details=f"Route={row.route_id}, Stop={row.stop_name}",
            )
            messages.success(request, 'Route stop added successfully.')
            return redirect('transport_route_list_core')

    routes = Route.objects.filter(school=school).select_related('vehicle', 'vehicle__assigned_driver').order_by('route_name')
    stops = RouteStop.objects.filter(route__school=school).select_related('route').order_by('route__route_name', 'stop_order')
    return render(request, 'transport_core/route_list.html', {
        'routes': routes,
        'stops': stops,
        'route_form': route_form,
        'stop_form': stop_form,
    })


@login_required
@role_required('schooladmin')
def transport_route_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Route, pk=pk, school=school)

    if request.method == 'POST':
        form = RouteForm(request.POST, instance=row, school=school)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='transport.route_updated',
                school=school,
                target=row,
                details=f"Route={row.route_name}",
            )
            messages.success(request, 'Route updated successfully.')
            return redirect('transport_route_list_core')
    else:
        form = RouteForm(instance=row, school=school)

    return render(request, 'transport_core/route_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def transport_route_deactivate(request, pk):
    row = get_object_or_404(Route, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='transport.route_deactivated',
        school=request.user.school,
        target=row,
        details=f"Route={row.route_name}",
    )
    messages.success(request, 'Route deactivated successfully.')
    return redirect('transport_route_list_core')


@login_required
@role_required('schooladmin')
@require_POST
def transport_stop_delete(request, pk):
    row = get_object_or_404(RouteStop, pk=pk, route__school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='transport.route_stop_deleted',
        school=request.user.school,
        target=row,
        details=f"Route={row.route_id}, Stop={row.stop_name}",
    )
    messages.success(request, 'Route stop removed successfully.')
    return redirect('transport_route_list_core')


@login_required
@role_required('schooladmin')
def transport_student_allocation_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    form = StudentTransportForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'assign' else None,
        school=school,
        default_session=selected_session,
    )

    if request.method == 'POST' and request.POST.get('action') == 'assign':
        if form.is_valid():
            try:
                allocation = assign_student_transport(
                    school=school,
                    session=form.cleaned_data['session'],
                    student=form.cleaned_data['student'],
                    route=form.cleaned_data['route'],
                    stop_name=form.cleaned_data['stop_name'],
                    pickup_time=form.cleaned_data['pickup_time'],
                    drop_time=form.cleaned_data['drop_time'],
                    transport_fee=form.cleaned_data['transport_fee'],
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='transport.student_allocation_saved',
                    school=school,
                    target=allocation,
                    details=f"Student={allocation.student_id}, Route={allocation.route_id}",
                )
                messages.success(request, 'Student transport allocation saved successfully.')
                return redirect(f"{reverse('transport_student_allocation_list_core')}?session={allocation.session_id}")

    if request.method == 'POST' and request.POST.get('action') == 'deactivate':
        allocation = get_object_or_404(
            StudentTransport,
            pk=request.POST.get('allocation_id'),
            school=school,
        )
        try:
            deactivate_student_transport(allocation=allocation)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            log_audit_event(
                request=request,
                action='transport.student_allocation_deactivated',
                school=school,
                target=allocation,
                details=f"Student={allocation.student_id}",
            )
            messages.success(request, 'Student transport allocation deactivated.')
        return redirect('transport_student_allocation_list_core')

    rows = StudentTransport.objects.filter(school=school).select_related(
        'session',
        'student',
        'route',
        'route__vehicle',
    )
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'transport_core/student_allocation_list.html', {
        'rows': rows.order_by('student__admission_number'),
        'sessions': sessions,
        'selected_session': selected_session,
        'form': form,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def transport_report_route(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    rows = route_wise_students(school=school, session=selected_session) if selected_session else []

    export = request.GET.get('export')
    table_rows = [
        [
            row.route.route_name,
            row.student.admission_number,
            row.student.full_name,
            row.stop_name,
            row.route.vehicle.vehicle_number,
            row.route.vehicle.assigned_driver.name if row.route.vehicle.assigned_driver_id else '-',
            row.transport_fee,
        ]
        for row in rows
    ]
    headers = ['Route', 'Admission No', 'Student', 'Stop', 'Vehicle', 'Driver', 'Fee']
    if export == 'csv':
        return _export_csv_response('transport_route_report.csv', headers, table_rows)
    if export == 'pdf':
        return _export_pdf_response('transport_route_report.pdf', 'Transport Route Report', headers, table_rows)

    return render(request, 'transport_core/report_route.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def transport_report_vehicle(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    rows = vehicle_occupancy_report(school=school, session=selected_session) if selected_session else []

    export = request.GET.get('export')
    table_rows = [
        [
            row['vehicle'].vehicle_number,
            row['vehicle'].get_vehicle_type_display(),
            row['capacity'],
            row['occupied'],
            row['available'],
            row['occupancy_percent'],
        ]
        for row in rows
    ]
    headers = ['Vehicle', 'Type', 'Capacity', 'Occupied', 'Available', 'Occupancy %']
    if export == 'csv':
        return _export_csv_response('transport_vehicle_report.csv', headers, table_rows)
    if export == 'pdf':
        return _export_pdf_response('transport_vehicle_report.pdf', 'Transport Vehicle Report', headers, table_rows)

    return render(request, 'transport_core/report_vehicle.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def transport_report_driver(request):
    school = request.user.school
    rows = driver_allocation_report(school=school)

    export = request.GET.get('export')
    table_rows = [
        [
            row['driver'].name,
            row['driver'].license_number,
            row['vehicle_count'],
            row['route_count'],
            ', '.join(vehicle.vehicle_number for vehicle in row['vehicles']) or '-',
        ]
        for row in rows
    ]
    headers = ['Driver', 'License', 'Vehicles', 'Routes', 'Vehicle Numbers']
    if export == 'csv':
        return _export_csv_response('transport_driver_report.csv', headers, table_rows)
    if export == 'pdf':
        return _export_pdf_response('transport_driver_report.pdf', 'Driver Allocation Report', headers, table_rows)

    return render(request, 'transport_core/report_driver.html', {
        'rows': rows,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def transport_report_insurance(request):
    school = request.user.school
    days = request.GET.get('days')
    try:
        days_value = int(days) if days else 30
    except (TypeError, ValueError):
        days_value = 30
    if days_value <= 0:
        days_value = 30

    rows = insurance_expiry_report(school=school, days=days_value)

    export = request.GET.get('export')
    table_rows = [
        [
            row.vehicle_number,
            row.get_vehicle_type_display(),
            row.insurance_expiry,
            row.fitness_expiry or '-',
            row.assigned_driver.name if row.assigned_driver_id else '-',
        ]
        for row in rows
    ]
    headers = ['Vehicle', 'Type', 'Insurance Expiry', 'Fitness Expiry', 'Driver']
    if export == 'csv':
        return _export_csv_response('transport_insurance_alerts.csv', headers, table_rows)
    if export == 'pdf':
        return _export_pdf_response('transport_insurance_alerts.pdf', 'Insurance Expiry Alerts', headers, table_rows)

    return render(request, 'transport_core/report_insurance.html', {
        'rows': rows,
        'days': days_value,
        'horizon': timezone.localdate() + timedelta(days=days_value),
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def transport_report_fee_pending(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    rows = transport_fee_pending_report(school=school, session=selected_session) if selected_session else []

    export = request.GET.get('export')
    table_rows = [
        [
            row['student'].admission_number,
            row['student'].full_name,
            row['total'],
            row['paid'],
            row['pending'],
        ]
        for row in rows
    ]
    headers = ['Admission No', 'Student', 'Total Fee', 'Paid', 'Pending']
    if export == 'csv':
        return _export_csv_response('transport_fee_pending.csv', headers, table_rows)
    if export == 'pdf':
        return _export_pdf_response('transport_fee_pending.pdf', 'Transport Fee Pending Report', headers, table_rows)

    return render(request, 'transport_core/report_fee_pending.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })
