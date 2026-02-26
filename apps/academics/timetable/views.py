from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.academics.students.models import Student
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import TimetableEntryForm
from .models import TimetableEntry


@login_required
@role_required('schooladmin')
def timetable_manage(request):
    school = request.user.school
    error = None

    entries = TimetableEntry.objects.filter(
        school=school
    ).select_related(
        'academic_session',
        'school_class',
        'section',
        'subject',
        'teacher',
    ).order_by('day_of_week', 'period_number', 'start_time')

    if request.method == 'POST':
        form = TimetableEntryForm(request.POST, school=school)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.school = school
            entry.save()
            log_audit_event(
                request=request,
                action='timetable.created',
                school=school,
                target=entry,
                details=f"Class={entry.school_class_id}, Section={entry.section_id}, Day={entry.day_of_week}, Period={entry.period_number}",
            )
            return redirect('timetable_manage')
        error = 'Please correct timetable details.'
    else:
        form = TimetableEntryForm(school=school)

    return render(request, 'timetable/manage.html', {
        'form': form,
        'entries': entries,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def timetable_update(request, pk):
    school = request.user.school
    entry = get_object_or_404(
        TimetableEntry,
        pk=pk,
        school=school
    )
    error = None

    if request.method == 'POST':
        form = TimetableEntryForm(request.POST, instance=entry, school=school)
        if form.is_valid():
            entry = form.save()
            log_audit_event(
                request=request,
                action='timetable.updated',
                school=school,
                target=entry,
                details=f"Class={entry.school_class_id}, Section={entry.section_id}, Day={entry.day_of_week}, Period={entry.period_number}",
            )
            return redirect('timetable_manage')
        error = 'Please correct timetable details.'
    else:
        form = TimetableEntryForm(instance=entry, school=school)

    return render(request, 'timetable/form.html', {
        'form': form,
        'entry': entry,
        'error': error,
    })


@login_required
@role_required('schooladmin')
@require_POST
def timetable_delete(request, pk):
    entry = get_object_or_404(
        TimetableEntry,
        pk=pk,
        school=request.user.school
    )
    log_audit_event(
        request=request,
        action='timetable.deleted',
        school=request.user.school,
        target=entry,
        details=f"Day={entry.day_of_week}, Period={entry.period_number}",
    )
    entry.delete()
    return redirect('timetable_manage')


@login_required
@role_required('teacher')
def teacher_timetable(request):
    school = request.user.school
    staff_profile = getattr(request.user, 'staff_profile', None)
    entries = TimetableEntry.objects.none()
    if staff_profile and staff_profile.school_id == school.id:
        entries = TimetableEntry.objects.filter(
            school=school,
            is_active=True,
            teacher=staff_profile,
        ).select_related(
            'academic_session',
            'school_class',
            'section',
            'subject',
        ).order_by('day_of_week', 'period_number', 'start_time')

    return render(request, 'timetable/teacher_list.html', {
        'entries': entries,
    })


@login_required
@role_required('parent')
def parent_timetable(request):
    school = request.user.school
    current_session = school.current_session

    children = Student.objects.filter(
        school=school,
        parent_user=request.user,
    ).select_related('school_class', 'section').order_by('first_name', 'last_name')

    filter_query = Q()
    student_map = {}
    for child in children:
        if not child.school_class_id or not child.section_id:
            continue
        filter_query |= Q(
            school_class_id=child.school_class_id,
            section_id=child.section_id
        )
        key = (child.school_class_id, child.section_id)
        student_map.setdefault(key, []).append(child)

    entries = TimetableEntry.objects.none()
    if filter_query:
        entries = TimetableEntry.objects.filter(
            school=school,
            is_active=True
        ).filter(filter_query).select_related(
            'academic_session',
            'school_class',
            'section',
            'subject',
            'teacher',
        ).order_by('day_of_week', 'period_number', 'start_time')
        if current_session:
            entries = entries.filter(academic_session=current_session)

    rows = []
    for entry in entries:
        key = (entry.school_class_id, entry.section_id)
        rows.append({
            'entry': entry,
            'students': student_map.get(key, []),
        })

    return render(request, 'timetable/parent_list.html', {
        'rows': rows,
        'current_session': current_session,
    })
