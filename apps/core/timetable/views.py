from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import Period, SchoolClass, Section
from apps.core.hr.models import Staff
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import TeacherTimetableFilterForm, TimetableEntryForm, TimetableSelectionForm
from .models import DAY_CHOICES, TimetableEntry
from .services import (
    build_class_timetable_grid,
    build_teacher_timetable_grid,
    generate_class_timetable_pdf,
    generate_teacher_timetable_pdf,
    teacher_substitutions_for_week,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_session(request, school):
    session_id = request.GET.get('session') or request.POST.get('session')
    sessions = _school_sessions(school)

    selected_session = None
    if session_id:
        selected_session = sessions.filter(id=session_id).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


def _parse_date(raw_value, fallback=None):
    if not raw_value:
        return fallback or timezone.localdate()
    try:
        return date.fromisoformat(raw_value)
    except (TypeError, ValueError):
        return fallback or timezone.localdate()


@login_required
@role_required('schooladmin')
def timetable_class_grid(request):
    school = request.user.school
    sessions, selected_session = _resolve_session(request, school)

    initial_data = {
        'session': selected_session,
        'view_date': timezone.localdate(),
    }
    selection_form = TimetableSelectionForm(request.GET or None, school=school, initial=initial_data)

    selected_class = None
    selected_section = None
    view_date = timezone.localdate()

    if selection_form.is_valid():
        cleaned = selection_form.cleaned_data
        selected_session = cleaned.get('session') or selected_session
        selected_class = cleaned.get('school_class')
        selected_section = cleaned.get('section')
        view_date = cleaned.get('view_date') or view_date

    periods = Period.objects.none()
    rows = []
    if selected_session:
        periods = Period.objects.filter(
            school=school,
            session=selected_session,
            is_active=True,
        ).order_by('period_number')

        if selected_class and selected_section:
            if selected_section.school_class_id != selected_class.id:
                messages.error(request, 'Selected section does not belong to selected class.')
            else:
                rows = build_class_timetable_grid(
                    school=school,
                    session=selected_session,
                    school_class=selected_class,
                    section=selected_section,
                    periods=periods,
                    view_date=view_date,
                )

    return render(request, 'timetable_core/class_grid.html', {
        'selection_form': selection_form,
        'rows': rows,
        'periods': periods,
        'selected_session': selected_session,
        'selected_class': selected_class,
        'selected_section': selected_section,
        'view_date': view_date,
        'day_choices': DAY_CHOICES,
    })


@login_required
@role_required('schooladmin')
def timetable_cell_edit(request, class_id, section_id, day_of_week, period_id):
    school = request.user.school
    sessions, selected_session = _resolve_session(request, school)

    if not selected_session:
        messages.error(request, 'Select an academic session first.')
        return redirect('timetable_class_grid')

    school_class = get_object_or_404(SchoolClass, id=class_id, school=school, session=selected_session)
    section = get_object_or_404(Section, id=section_id, school_class=school_class)
    period = get_object_or_404(Period, id=period_id, school=school, session=selected_session)

    if day_of_week not in dict(DAY_CHOICES):
        messages.error(request, 'Invalid day selected.')
        return redirect('timetable_class_grid')

    entry = TimetableEntry.objects.filter(
        school=school,
        session=selected_session,
        school_class=school_class,
        section=section,
        day_of_week=day_of_week,
        period=period,
        is_active=True,
    ).first()

    view_date = _parse_date(request.GET.get('view_date') or request.POST.get('view_date'))

    if request.method == 'POST':
        form = TimetableEntryForm(
            request.POST,
            instance=entry,
            school=school,
            session=selected_session,
            school_class=school_class,
            section=section,
            day_of_week=day_of_week,
            period=period,
        )
        if form.is_valid():
            timetable_entry = form.save(commit=False)
            timetable_entry.school = school
            timetable_entry.session = selected_session
            timetable_entry.school_class = school_class
            timetable_entry.section = section
            timetable_entry.day_of_week = day_of_week
            timetable_entry.period = period
            timetable_entry.save()

            log_audit_event(
                request=request,
                action='timetable.entry_saved',
                school=school,
                target=timetable_entry,
                details=(
                    f"Session={selected_session.id}, Class={school_class.id}, Section={section.id}, "
                    f"Day={day_of_week}, Period={period.id}, Subject={timetable_entry.subject_id}, "
                    f"Teacher={timetable_entry.teacher_id}"
                ),
            )
            messages.success(request, 'Timetable slot saved successfully.')
            query = (
                f"session={selected_session.id}&school_class={school_class.id}&section={section.id}"
                f"&view_date={view_date.isoformat()}"
            )
            return redirect(f"{reverse('timetable_class_grid')}?{query}")
    else:
        form = TimetableEntryForm(
            instance=entry,
            school=school,
            session=selected_session,
            school_class=school_class,
            section=section,
            day_of_week=day_of_week,
            period=period,
        )

    return render(request, 'timetable_core/cell_form.html', {
        'form': form,
        'sessions': sessions,
        'selected_session': selected_session,
        'school_class': school_class,
        'section': section,
        'period': period,
        'day_of_week': day_of_week,
        'day_label': dict(DAY_CHOICES)[day_of_week],
        'entry': entry,
        'view_date': view_date,
    })


@login_required
@role_required('schooladmin')
@require_POST
def timetable_cell_deactivate(request, class_id, section_id, day_of_week, period_id):
    school = request.user.school
    _, selected_session = _resolve_session(request, school)

    if not selected_session:
        messages.error(request, 'Session is required.')
        return redirect('timetable_class_grid')

    school_class = get_object_or_404(SchoolClass, id=class_id, school=school, session=selected_session)
    section = get_object_or_404(Section, id=section_id, school_class=school_class)
    period = get_object_or_404(Period, id=period_id, school=school, session=selected_session)

    entry = get_object_or_404(
        TimetableEntry,
        school=school,
        session=selected_session,
        school_class=school_class,
        section=section,
        day_of_week=day_of_week,
        period=period,
        is_active=True,
    )
    entry.delete()

    log_audit_event(
        request=request,
        action='timetable.entry_deactivated',
        school=school,
        target=entry,
        details=f"Entry={entry.id}",
    )
    messages.success(request, 'Timetable slot deactivated successfully.')

    view_date = _parse_date(request.POST.get('view_date'))
    query = (
        f"session={selected_session.id}&school_class={school_class.id}&section={section.id}&view_date={view_date.isoformat()}"
    )
    return redirect(f"{reverse('timetable_class_grid')}?{query}")


@login_required
@role_required('schooladmin')
def timetable_class_pdf(request, class_id, section_id):
    school = request.user.school
    _, selected_session = _resolve_session(request, school)

    if not selected_session:
        messages.error(request, 'Session is required.')
        return redirect('timetable_class_grid')

    school_class = get_object_or_404(SchoolClass, id=class_id, school=school, session=selected_session)
    section = get_object_or_404(Section, id=section_id, school_class=school_class)

    periods = Period.objects.filter(
        school=school,
        session=selected_session,
        is_active=True,
    ).order_by('period_number')

    view_date = _parse_date(request.GET.get('view_date'))

    pdf_bytes = generate_class_timetable_pdf(
        school=school,
        session=selected_session,
        school_class=school_class,
        section=section,
        periods=periods,
        view_date=view_date,
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="class_timetable_{school_class.name}_{section.name}_{selected_session.name}.pdf"'
    )
    return response


@login_required
@role_required(['schooladmin', 'teacher'])
def timetable_teacher_view(request):
    school = request.user.school
    sessions, selected_session = _resolve_session(request, school)
    allow_teacher_selection = request.user.role == 'schooladmin'

    initial = {
        'session': selected_session,
        'anchor_date': timezone.localdate(),
    }
    if not allow_teacher_selection:
        initial['teacher'] = Staff.objects.filter(user=request.user, school=school, is_active=True).first()

    filter_form = TeacherTimetableFilterForm(
        request.GET or None,
        school=school,
        allow_teacher_selection=allow_teacher_selection,
        initial=initial,
    )

    selected_teacher = None
    anchor_date = timezone.localdate()

    if filter_form.is_valid():
        cleaned = filter_form.cleaned_data
        selected_session = cleaned.get('session') or selected_session
        selected_teacher = cleaned.get('teacher')
        anchor_date = cleaned.get('anchor_date') or anchor_date

    if not allow_teacher_selection:
        selected_teacher = Staff.objects.filter(user=request.user, school=school, is_active=True).first()

    periods = Period.objects.none()
    rows = []
    substitutions_as_substitute = []
    substitutions_as_original = []

    if selected_session and selected_teacher:
        periods = Period.objects.filter(
            school=school,
            session=selected_session,
            is_active=True,
        ).order_by('period_number')

        rows = build_teacher_timetable_grid(
            school=school,
            session=selected_session,
            teacher=selected_teacher,
            periods=periods,
        )

        substitutions_as_substitute, substitutions_as_original = teacher_substitutions_for_week(
            school=school,
            session=selected_session,
            teacher=selected_teacher,
            anchor_date=anchor_date,
        )

    return render(request, 'timetable_core/teacher_view.html', {
        'filter_form': filter_form,
        'rows': rows,
        'periods': periods,
        'selected_session': selected_session,
        'selected_teacher': selected_teacher,
        'anchor_date': anchor_date,
        'substitutions_as_substitute': substitutions_as_substitute,
        'substitutions_as_original': substitutions_as_original,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def timetable_teacher_pdf(request):
    school = request.user.school
    _, selected_session = _resolve_session(request, school)

    if not selected_session:
        messages.error(request, 'Session is required.')
        return redirect('timetable_teacher_view')

    if request.user.role == 'schooladmin':
        teacher_id = request.GET.get('teacher')
        if not teacher_id or not teacher_id.isdigit():
            messages.error(request, 'Teacher is required for export.')
            return redirect('timetable_teacher_view')
        selected_teacher = get_object_or_404(
            Staff,
            id=int(teacher_id),
            school=school,
            is_active=True,
            user__role='teacher',
        )
    else:
        selected_teacher = get_object_or_404(
            Staff,
            user=request.user,
            school=school,
            is_active=True,
            user__role='teacher',
        )

    periods = Period.objects.filter(
        school=school,
        session=selected_session,
        is_active=True,
    ).order_by('period_number')

    pdf_bytes = generate_teacher_timetable_pdf(
        school=school,
        session=selected_session,
        teacher=selected_teacher,
        periods=periods,
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="teacher_timetable_{selected_teacher.employee_id}_{selected_session.name}.pdf"'
    )
    return response
