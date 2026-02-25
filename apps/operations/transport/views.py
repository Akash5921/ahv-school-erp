from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.academics.staff.models import Staff
from apps.academics.students.models import Student
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import BusForm, RouteForm, StudentTransportForm
from .models import Bus, Route, StudentTransport


@login_required
@role_required('schooladmin')
def bus_list(request):
    school = request.user.school
    buses = Bus.objects.filter(
        school=school
    ).select_related('driver').order_by('bus_number')
    error = None

    if request.method == 'POST':
        form = BusForm(request.POST)
        form.fields['driver'].queryset = Staff.objects.filter(
            school=school,
            staff_type='driver',
            is_active=True
        ).order_by('first_name', 'last_name')
        if form.is_valid():
            bus = form.save(commit=False)
            bus.school = school
            bus.save()
            log_audit_event(
                request=request,
                action='transport.bus_created',
                school=school,
                target=bus,
                details=f"Bus={bus.bus_number}",
            )
            return redirect('transport_bus_list')
        error = 'Please correct bus details.'
    else:
        form = BusForm()
        form.fields['driver'].queryset = Staff.objects.filter(
            school=school,
            staff_type='driver',
            is_active=True
        ).order_by('first_name', 'last_name')

    return render(request, 'transport/bus_list.html', {
        'buses': buses,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def bus_delete(request, pk):
    bus = get_object_or_404(Bus, pk=pk, school=request.user.school)
    if request.method == 'POST':
        log_audit_event(
            request=request,
            action='transport.bus_deleted',
            school=request.user.school,
            target=bus,
            details=f"Bus={bus.bus_number}",
        )
        bus.delete()
    return redirect('transport_bus_list')


@login_required
@role_required('schooladmin')
def route_list(request):
    school = request.user.school
    routes = Route.objects.filter(
        school=school
    ).order_by('name')
    error = None

    if request.method == 'POST':
        form = RouteForm(request.POST)
        if form.is_valid():
            route = form.save(commit=False)
            route.school = school
            route.save()
            log_audit_event(
                request=request,
                action='transport.route_created',
                school=school,
                target=route,
                details=f"Route={route.name}",
            )
            return redirect('transport_route_list')
        error = 'Please correct route details.'
    else:
        form = RouteForm()

    return render(request, 'transport/route_list.html', {
        'routes': routes,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def route_delete(request, pk):
    route = get_object_or_404(Route, pk=pk, school=request.user.school)
    if request.method == 'POST':
        log_audit_event(
            request=request,
            action='transport.route_deleted',
            school=request.user.school,
            target=route,
            details=f"Route={route.name}",
        )
        route.delete()
    return redirect('transport_route_list')


@login_required
@role_required('schooladmin')
def student_transport_manage(request):
    school = request.user.school
    current_session = school.current_session
    error = None

    assignments = StudentTransport.objects.filter(
        student__school=school,
        academic_session=current_session
    ).select_related(
        'student', 'bus', 'route'
    ).order_by('student__first_name', 'student__last_name') if current_session else []

    if request.method == 'POST':
        form = StudentTransportForm(request.POST)
        form.fields['student'].queryset = Student.objects.filter(
            school=school
        ).order_by('first_name', 'last_name')
        form.fields['bus'].queryset = Bus.objects.filter(
            school=school
        ).order_by('bus_number')
        form.fields['route'].queryset = Route.objects.filter(
            school=school
        ).order_by('name')

        if not current_session:
            error = 'No active academic session set for this school.'
        elif form.is_valid():
            student = form.cleaned_data['student']
            bus = form.cleaned_data['bus']
            route = form.cleaned_data['route']

            taken_seats = StudentTransport.objects.filter(
                bus=bus,
                academic_session=current_session
            ).exclude(student=student).count()

            if taken_seats >= bus.capacity:
                error = f"Bus {bus.bus_number} is full."
            else:
                assignment, _ = StudentTransport.objects.update_or_create(
                    student=student,
                    academic_session=current_session,
                    defaults={
                        'bus': bus,
                        'route': route,
                    }
                )
                log_audit_event(
                    request=request,
                    action='transport.student_assigned',
                    school=school,
                    target=assignment,
                    details=f"Student={student.id}, Bus={bus.id}, Route={route.id}",
                )
                return redirect('transport_student_manage')
        else:
            error = 'Please correct transport assignment details.'
    else:
        form = StudentTransportForm()
        form.fields['student'].queryset = Student.objects.filter(
            school=school
        ).order_by('first_name', 'last_name')
        form.fields['bus'].queryset = Bus.objects.filter(
            school=school
        ).order_by('bus_number')
        form.fields['route'].queryset = Route.objects.filter(
            school=school
        ).order_by('name')

    return render(request, 'transport/student_transport.html', {
        'form': form,
        'assignments': assignments,
        'current_session': current_session,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def student_transport_remove(request, pk):
    assignment = get_object_or_404(
        StudentTransport,
        pk=pk,
        student__school=request.user.school
    )
    if request.method == 'POST':
        log_audit_event(
            request=request,
            action='transport.student_assignment_removed',
            school=request.user.school,
            target=assignment,
            details=f"Student={assignment.student_id}",
        )
        assignment.delete()
    return redirect('transport_student_manage')
