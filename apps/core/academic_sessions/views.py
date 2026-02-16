from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import AcademicSessionForm
from .models import AcademicSession


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
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.school = request.user.school
            session.save()
            return redirect('session_list')
    else:
        form = AcademicSessionForm()

    return render(request, 'academic_sessions/session_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def session_update(request, pk):
    session = get_object_or_404(
        AcademicSession,
        pk=pk,
        school=request.user.school
    )

    if request.method == 'POST':
        form = AcademicSessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            return redirect('session_list')
    else:
        form = AcademicSessionForm(instance=session)

    return render(request, 'academic_sessions/session_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def session_delete(request, pk):
    session = get_object_or_404(
        AcademicSession,
        pk=pk,
        school=request.user.school
    )
    session.delete()
    return redirect('session_list')


@login_required
@role_required('schooladmin')
def session_activate(request, pk):
    school = request.user.school
    session = get_object_or_404(
        AcademicSession,
        pk=pk,
        school=school
    )

    with transaction.atomic():
        AcademicSession.objects.filter(
            school=school,
            is_active=True
        ).update(is_active=False)
        session.is_active = True
        session.save(update_fields=['is_active'])

        school.current_session = session
        school.save(update_fields=['current_session'])

    log_audit_event(
        request=request,
        action='session.activated',
        school=school,
        target=session,
        details=f"Activated session {session.name}",
    )
    return redirect('session_list')
