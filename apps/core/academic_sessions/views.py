from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import AcademicSessionForm
from .models import AcademicSession
from .services import activate_session, ensure_session_editable


@login_required
@role_required('schooladmin')
def session_list(request):
    sessions = AcademicSession.objects.filter(
        school=request.user.school
    ).order_by('-start_date')
    return render(request, 'academic_sessions/session_list.html', {
        'sessions': sessions
    })


@login_required
@role_required('schooladmin')
def session_create(request):
    school = request.user.school
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.school = school
            should_activate = session.is_active
            if should_activate:
                session.is_active = False
            session.save()
            if should_activate:
                activate_session(school=school, session=session)
            return redirect('session_list')
    else:
        form = AcademicSessionForm()

    return render(request, 'academic_sessions/session_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def session_update(request, pk):
    school = request.user.school
    session = get_object_or_404(
        AcademicSession,
        pk=pk,
        school=school
    )

    if session.is_locked:
        messages.error(request, 'Locked academic sessions cannot be edited.')
        return redirect('session_list')

    if request.method == 'POST':
        form = AcademicSessionForm(request.POST, instance=session)
        if form.is_valid():
            updated_session = form.save(commit=False)
            should_activate = updated_session.is_active
            if should_activate:
                updated_session.is_active = False
            try:
                ensure_session_editable(session=session)
                updated_session.save()
                if should_activate:
                    activate_session(school=school, session=updated_session)
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
                return redirect('session_list')
            return redirect('session_list')
    else:
        form = AcademicSessionForm(instance=session)

    return render(request, 'academic_sessions/session_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
@require_POST
def session_delete(request, pk):
    session = get_object_or_404(
        AcademicSession,
        pk=pk,
        school=request.user.school
    )
    if session.is_locked:
        messages.error(request, 'Locked academic sessions cannot be deleted.')
        return redirect('session_list')

    related_data_exists = any([
        session.classes.exists(),
        session.students_core.exists(),
        session.exams.exists(),
        session.student_fees_core.exists(),
        session.payrolls.exists(),
        session.student_attendances.exists(),
        session.staff_attendances.exists(),
    ])
    if related_data_exists:
        messages.error(request, 'This session already has data and cannot be deleted.')
        return redirect('session_list')

    session.delete()
    return redirect('session_list')


@login_required
@role_required('schooladmin')
@require_POST
def session_activate(request, pk):
    school = request.user.school
    session = get_object_or_404(
        AcademicSession,
        pk=pk,
        school=school
    )
    try:
        activate_session(school=school, session=session)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('session_list')

    log_audit_event(
        request=request,
        action='session.activated',
        school=school,
        target=session,
        details=f"Activated session {session.name}",
    )
    return redirect('session_list')
