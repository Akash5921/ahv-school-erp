from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    AcademicConfigForm,
    ClassSubjectForm,
    PeriodForm,
    SchoolClassForm,
    SectionForm,
    SubjectForm,
)
from .models import AcademicConfig, ClassSubject, Period, SchoolClass, Section, Subject


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('filter_session')

    selected_session = None
    if session_id:
        selected_session = sessions.filter(id=session_id).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


@login_required
@role_required('schooladmin')
def class_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    classes = SchoolClass.objects.filter(school=school)
    if selected_session:
        classes = classes.filter(session=selected_session)
    classes = classes.order_by('display_order', 'name')

    return render(request, 'academics/class_list.html', {
        'classes': classes,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def class_create(request):
    school = request.user.school
    if request.method == 'POST':
        form = SchoolClassForm(request.POST, school=school)
        if form.is_valid():
            school_class = form.save(commit=False)
            school_class.school = school
            school_class.save()
            log_audit_event(
                request=request,
                action='academics.class_created',
                school=school,
                target=school_class,
                details=f"Session={school_class.session_id}, Name={school_class.name}",
            )
            return redirect('class_list')
    else:
        form = SchoolClassForm(school=school)

    return render(request, 'academics/class_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def class_update(request, pk):
    school = request.user.school
    school_class = get_object_or_404(SchoolClass, pk=pk, school=school)

    if request.method == 'POST':
        form = SchoolClassForm(request.POST, instance=school_class, school=school)
        if form.is_valid():
            school_class = form.save()
            log_audit_event(
                request=request,
                action='academics.class_updated',
                school=school,
                target=school_class,
                details=f"Session={school_class.session_id}, Name={school_class.name}",
            )
            return redirect('class_list')
    else:
        form = SchoolClassForm(instance=school_class, school=school)

    return render(request, 'academics/class_form.html', {'form': form, 'school_class': school_class})


@login_required
@role_required('schooladmin')
@require_POST
def class_deactivate(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk, school=request.user.school)
    try:
        school_class.delete()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='academics.class_deactivated',
            school=request.user.school,
            target=school_class,
            details=f"Class={school_class.id}",
        )
    return redirect('class_list')


@login_required
@role_required('schooladmin')
def section_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    sections = Section.objects.filter(school_class__school=school).select_related(
        'school_class',
        'school_class__session',
        'class_teacher',
    )
    if selected_session:
        sections = sections.filter(school_class__session=selected_session)
    sections = sections.order_by('school_class__display_order', 'school_class__name', 'name')

    return render(request, 'academics/section_list.html', {
        'sections': sections,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def section_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)
    if request.method == 'POST':
        form = SectionForm(request.POST, school=school, session=selected_session)
        if form.is_valid():
            section = form.save()
            log_audit_event(
                request=request,
                action='academics.section_created',
                school=school,
                target=section,
                details=f"Class={section.school_class_id}, Name={section.name}",
            )
            return redirect('section_list')
    else:
        form = SectionForm(school=school, session=selected_session)

    return render(request, 'academics/section_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def section_update(request, pk):
    school = request.user.school
    section = get_object_or_404(Section, pk=pk, school_class__school=school)

    if request.method == 'POST':
        form = SectionForm(
            request.POST,
            instance=section,
            school=school,
            session=section.school_class.session,
        )
        if form.is_valid():
            section = form.save()
            log_audit_event(
                request=request,
                action='academics.section_updated',
                school=school,
                target=section,
                details=f"Class={section.school_class_id}, Name={section.name}",
            )
            return redirect('section_list')
    else:
        form = SectionForm(instance=section, school=school, session=section.school_class.session)

    return render(request, 'academics/section_form.html', {'form': form, 'section': section})


@login_required
@role_required('schooladmin')
@require_POST
def section_deactivate(request, pk):
    section = get_object_or_404(Section, pk=pk, school_class__school=request.user.school)
    section.delete()
    log_audit_event(
        request=request,
        action='academics.section_deactivated',
        school=request.user.school,
        target=section,
        details=f"Section={section.id}",
    )
    return redirect('section_list')


@login_required
@role_required('schooladmin')
def subject_list(request):
    subjects = Subject.objects.filter(
        school=request.user.school
    ).order_by('name')
    return render(request, 'academics/subject_list.html', {'subjects': subjects})


@login_required
@role_required('schooladmin')
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)
            subject.school = request.user.school
            subject.save()
            log_audit_event(
                request=request,
                action='academics.subject_created',
                school=request.user.school,
                target=subject,
                details=f"Code={subject.code}",
            )
            return redirect('subject_list')
    else:
        form = SubjectForm()

    return render(request, 'academics/subject_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk, school=request.user.school)

    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            subject = form.save()
            log_audit_event(
                request=request,
                action='academics.subject_updated',
                school=request.user.school,
                target=subject,
                details=f"Code={subject.code}",
            )
            return redirect('subject_list')
    else:
        form = SubjectForm(instance=subject)

    return render(request, 'academics/subject_form.html', {'form': form, 'subject': subject})


@login_required
@role_required('schooladmin')
@require_POST
def subject_deactivate(request, pk):
    subject = get_object_or_404(Subject, pk=pk, school=request.user.school)
    subject.delete()
    log_audit_event(
        request=request,
        action='academics.subject_deactivated',
        school=request.user.school,
        target=subject,
        details=f"Subject={subject.id}",
    )
    return redirect('subject_list')


@login_required
@role_required('schooladmin')
def class_subject_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    mappings = ClassSubject.objects.filter(
        school_class__school=school,
    ).select_related(
        'school_class',
        'school_class__session',
        'subject',
    )
    if selected_session:
        mappings = mappings.filter(school_class__session=selected_session)
    mappings = mappings.order_by('school_class__display_order', 'school_class__name', 'subject__name')

    return render(request, 'academics/class_subject_list.html', {
        'mappings': mappings,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def class_subject_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, school=school, session=selected_session)
        if form.is_valid():
            mapping = form.save()
            log_audit_event(
                request=request,
                action='academics.class_subject_created',
                school=school,
                target=mapping,
                details=f"Class={mapping.school_class_id}, Subject={mapping.subject_id}",
            )
            return redirect('class_subject_list')
    else:
        form = ClassSubjectForm(school=school, session=selected_session)

    return render(request, 'academics/class_subject_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def class_subject_update(request, pk):
    school = request.user.school
    mapping = get_object_or_404(ClassSubject, pk=pk, school_class__school=school)

    if request.method == 'POST':
        form = ClassSubjectForm(
            request.POST,
            instance=mapping,
            school=school,
            session=mapping.school_class.session,
        )
        if form.is_valid():
            mapping = form.save()
            log_audit_event(
                request=request,
                action='academics.class_subject_updated',
                school=school,
                target=mapping,
                details=f"Class={mapping.school_class_id}, Subject={mapping.subject_id}",
            )
            return redirect('class_subject_list')
    else:
        form = ClassSubjectForm(instance=mapping, school=school, session=mapping.school_class.session)

    return render(request, 'academics/class_subject_form.html', {'form': form, 'mapping': mapping})


@login_required
@role_required('schooladmin')
@require_POST
def class_subject_delete(request, pk):
    mapping = get_object_or_404(ClassSubject, pk=pk, school_class__school=request.user.school)
    log_audit_event(
        request=request,
        action='academics.class_subject_deleted',
        school=request.user.school,
        target=mapping,
        details=f"Class={mapping.school_class_id}, Subject={mapping.subject_id}",
    )
    mapping.delete()
    return redirect('class_subject_list')


@login_required
@role_required('schooladmin')
def period_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    periods = Period.objects.filter(school=school).select_related('session')
    if selected_session:
        periods = periods.filter(session=selected_session)
    periods = periods.order_by('period_number', 'start_time')

    return render(request, 'academics/period_list.html', {
        'periods': periods,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def period_create(request):
    school = request.user.school
    if request.method == 'POST':
        form = PeriodForm(request.POST, school=school)
        if form.is_valid():
            period = form.save(commit=False)
            period.school = school
            period.save()
            log_audit_event(
                request=request,
                action='academics.period_created',
                school=school,
                target=period,
                details=f"Session={period.session_id}, Period={period.period_number}",
            )
            return redirect('period_list')
    else:
        form = PeriodForm(school=school)

    return render(request, 'academics/period_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def period_update(request, pk):
    school = request.user.school
    period = get_object_or_404(Period, pk=pk, school=school)

    if request.method == 'POST':
        form = PeriodForm(request.POST, instance=period, school=school)
        if form.is_valid():
            period = form.save()
            log_audit_event(
                request=request,
                action='academics.period_updated',
                school=school,
                target=period,
                details=f"Session={period.session_id}, Period={period.period_number}",
            )
            return redirect('period_list')
    else:
        form = PeriodForm(instance=period, school=school)

    return render(request, 'academics/period_form.html', {'form': form, 'period': period})


@login_required
@role_required('schooladmin')
@require_POST
def period_deactivate(request, pk):
    period = get_object_or_404(Period, pk=pk, school=request.user.school)
    period.delete()
    log_audit_event(
        request=request,
        action='academics.period_deactivated',
        school=request.user.school,
        target=period,
        details=f"Period={period.period_number}",
    )
    return redirect('period_list')


@login_required
@role_required('schooladmin')
def academic_config_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    configs = AcademicConfig.objects.filter(school=school).select_related('session')
    if selected_session:
        configs = configs.filter(session=selected_session)
    configs = configs.order_by('-session__start_date')

    return render(request, 'academics/academic_config_list.html', {
        'configs': configs,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def academic_config_create(request):
    school = request.user.school
    if request.method == 'POST':
        form = AcademicConfigForm(request.POST, school=school)
        if form.is_valid():
            config = form.save(commit=False)
            config.school = school
            config.save()
            log_audit_event(
                request=request,
                action='academics.config_created',
                school=school,
                target=config,
                details=f"Session={config.session_id}",
            )
            return redirect('academic_config_list')
    else:
        form = AcademicConfigForm(school=school)

    return render(request, 'academics/academic_config_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def academic_config_update(request, pk):
    school = request.user.school
    config = get_object_or_404(AcademicConfig, pk=pk, school=school)

    if request.method == 'POST':
        form = AcademicConfigForm(request.POST, instance=config, school=school)
        if form.is_valid():
            config = form.save()
            log_audit_event(
                request=request,
                action='academics.config_updated',
                school=school,
                target=config,
                details=f"Session={config.session_id}",
            )
            return redirect('academic_config_list')
    else:
        form = AcademicConfigForm(instance=config, school=school)

    return render(request, 'academics/academic_config_form.html', {'form': form, 'config': config})
