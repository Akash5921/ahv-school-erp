from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import SessionCloseForm, SessionInitializationForm
from .models import PromotionRecord
from .services import (
    build_promotion_dashboard,
    close_session,
    initialize_new_session,
    unlock_session,
    bulk_promote_students,
)
from .validators import build_year_end_validation


def _pick(queryset, raw_value):
    if raw_value and str(raw_value).isdigit():
        return queryset.filter(id=int(raw_value)).first()
    return None


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date', '-id')


def _promotion_redirect(from_session, to_session, school_class=None, section=None):
    query = {
        'from_session': from_session.id if from_session else '',
        'to_session': to_session.id if to_session else '',
    }
    if school_class:
        query['school_class'] = school_class.id
    if section:
        query['section'] = section.id
    return f"{reverse('promotion_dashboard')}?{urlencode(query)}"


@login_required
@role_required('schooladmin')
def lifecycle_dashboard(request):
    school = request.user.school
    sessions = _school_sessions(school)
    selected_session = _pick(sessions, request.GET.get('session'))
    if not selected_session and school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()
    if not selected_session:
        selected_session = sessions.first()

    if request.method == 'POST':
        init_form = SessionInitializationForm(request.POST, school=school)
        if init_form.is_valid():
            try:
                result = initialize_new_session(
                    school=school,
                    name=init_form.cleaned_data['name'],
                    start_date=init_form.cleaned_data['start_date'],
                    end_date=init_form.cleaned_data['end_date'],
                    created_by=request.user,
                    source_session=init_form.cleaned_data.get('source_session'),
                    copy_academic_structure=init_form.cleaned_data.get('copy_academic_structure', False),
                    copy_fee_structure=init_form.cleaned_data.get('copy_fee_structure', False),
                    make_current=init_form.cleaned_data.get('make_current', False),
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                copied = result.get('copied') or {}
                copy_summary = ', '.join(
                    f"{label.replace('_', ' ')}: {value}"
                    for label, value in copied.items()
                    if value
                ) or 'No records copied.'
                messages.success(
                    request,
                    f"Session {result['session'].name} created. {copy_summary}",
                )
                log_audit_event(
                    request=request,
                    action='promotion.session_initialized',
                    school=school,
                    target=result['session'],
                    details=copy_summary,
                )
                return redirect(f"{reverse('promotion_lifecycle')}?session={result['session'].id}")
    else:
        init_form = SessionInitializationForm(school=school)

    close_form = SessionCloseForm(
        school=school,
        initial={'session': selected_session},
    )
    readiness = build_year_end_validation(school=school, session=selected_session) if selected_session else None

    return render(request, 'promotion_core/lifecycle_dashboard.html', {
        'sessions': sessions,
        'selected_session': selected_session,
        'init_form': init_form,
        'close_form': close_form,
        'readiness': readiness,
    })


@login_required
@role_required('schooladmin')
def promotion_dashboard(request):
    school = request.user.school
    sessions = _school_sessions(school)
    from_session = _pick(sessions, request.GET.get('from_session') or request.POST.get('from_session'))
    if not from_session and school.current_session_id:
        from_session = sessions.filter(id=school.current_session_id).first()
    if not from_session:
        from_session = sessions.first()

    to_sessions = sessions.exclude(id=getattr(from_session, 'id', None))
    to_session = _pick(to_sessions, request.GET.get('to_session') or request.POST.get('to_session'))
    if not to_session:
        to_session = to_sessions.order_by('start_date', 'id').first()

    classes = SchoolClass.objects.filter(
        school=school,
        session=from_session,
        is_active=True,
    ).order_by('display_order', 'name') if from_session else SchoolClass.objects.none()
    school_class = _pick(classes, request.GET.get('school_class') or request.POST.get('school_class'))

    sections = Section.objects.filter(
        school_class=school_class,
        is_active=True,
    ).order_by('name') if school_class else Section.objects.none()
    section = _pick(sections, request.GET.get('section') or request.POST.get('section'))

    dashboard = None
    if from_session and to_session:
        dashboard = build_promotion_dashboard(
            school=school,
            from_session=from_session,
            to_session=to_session,
            school_class=school_class,
            section=section,
        )

    if request.method == 'POST':
        if not from_session or not to_session:
            messages.error(request, 'Select both from and to sessions before promoting students.')
            return redirect('promotion_dashboard')

        actions = []
        for raw_id in request.POST.getlist('student_ids'):
            if not str(raw_id).isdigit():
                continue
            student_id = int(raw_id)
            status = request.POST.get(f'action_{student_id}') or ''
            if status == 'skip' or not status:
                continue
            to_class_id = request.POST.get(f'to_class_{student_id}') or ''
            to_section_id = request.POST.get(f'to_section_{student_id}') or ''
            actions.append({
                'student_id': student_id,
                'status': status,
                'to_class_id': int(to_class_id) if str(to_class_id).isdigit() else None,
                'to_section_id': int(to_section_id) if str(to_section_id).isdigit() else None,
                'remarks': request.POST.get(f'remarks_{student_id}', ''),
            })

        if not actions:
            messages.error(request, 'Choose at least one promotion action.')
            return redirect(_promotion_redirect(from_session, to_session, school_class, section))

        processed, errors = bulk_promote_students(
            school=school,
            from_session=from_session,
            to_session=to_session,
            actions=actions,
            promoted_by=request.user,
        )
        if processed:
            messages.success(request, f'{len(processed)} promotion records saved.')
            log_audit_event(
                request=request,
                action='promotion.bulk_processed',
                school=school,
                target=to_session,
                details=f"From={from_session.id}, To={to_session.id}, Count={len(processed)}",
            )
        if errors:
            messages.error(request, '; '.join(errors[:8]))

        return redirect(_promotion_redirect(from_session, to_session, school_class, section))

    return render(request, 'promotion_core/promotion_dashboard.html', {
        'sessions': sessions,
        'from_session': from_session,
        'to_session': to_session,
        'classes': classes,
        'selected_class': school_class,
        'sections': sections,
        'selected_section': section,
        'dashboard': dashboard,
        'status_choices': PromotionRecord.STATUS_CHOICES,
    })


@login_required
@role_required('schooladmin')
@require_POST
def session_close_view(request):
    school = request.user.school
    form = SessionCloseForm(request.POST, school=school)
    if not form.is_valid():
        messages.error(request, '; '.join(form.errors.get('__all__', ['Invalid close-session request.'])))
        return redirect('promotion_lifecycle')

    session = form.cleaned_data['session']
    next_session = form.cleaned_data.get('next_session')
    try:
        result = close_session(
            session=session,
            closed_by=request.user,
            next_session=next_session,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        next_session_text = next_session.name if next_session else 'None'
        messages.success(request, f"Session {session.name} closed. Next session: {next_session_text}.")
        log_audit_event(
            request=request,
            action='promotion.session_closed',
            school=school,
            target=session,
            details=(
                f"Attendance={result['attendance_locked']}, Exams={result['exam_locked']}, "
                f"Marks={result['marks_locked']}, Results={result['summaries_locked']}, "
                f"Payroll={result['payroll_locked']}, Next={getattr(next_session, 'id', '')}"
            ),
        )
    return redirect(f"{reverse('promotion_lifecycle')}?session={session.id}")


@login_required
@role_required('superadmin')
@require_POST
def session_unlock_view(request, pk):
    session = get_object_or_404(
        AcademicSession.objects.select_related('school'),
        pk=pk,
    )
    try:
        unlock_session(
            session=session,
            unlocked_by=request.user,
            allow_override=True,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'Session {session.name} unlocked.')
        log_audit_event(
            request=request,
            action='promotion.session_unlocked',
            school=session.school,
            target=session,
            details=f"Session={session.id}",
        )
    return redirect('school_list')
