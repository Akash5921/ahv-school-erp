from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.academics.students.models import Student
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import HomeworkForm
from .models import Homework


@login_required
@role_required(['schooladmin', 'teacher'])
def homework_manage(request):
    school = request.user.school
    error = None
    homeworks = Homework.objects.filter(
        school=school
    ).select_related(
        'academic_session',
        'school_class',
        'section',
        'subject',
        'assigned_by',
    ).order_by('due_date', '-id')

    if request.method == 'POST':
        form = HomeworkForm(request.POST, school=school)
        if form.is_valid():
            homework = form.save(commit=False)
            homework.school = school
            homework.assigned_by = request.user
            homework.save()
            log_audit_event(
                request=request,
                action='homework.created',
                school=school,
                target=homework,
                details=f"Class={homework.school_class_id}, Section={homework.section_id}, Subject={homework.subject_id}",
            )
            return redirect('homework_manage')
        error = 'Please correct homework details.'
    else:
        form = HomeworkForm(school=school)

    return render(request, 'homework/manage.html', {
        'form': form,
        'homeworks': homeworks,
        'error': error,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def homework_update(request, pk):
    school = request.user.school
    homework = get_object_or_404(
        Homework,
        pk=pk,
        school=school
    )
    error = None

    if request.method == 'POST':
        form = HomeworkForm(request.POST, instance=homework, school=school)
        if form.is_valid():
            homework = form.save()
            log_audit_event(
                request=request,
                action='homework.updated',
                school=school,
                target=homework,
                details=f"Class={homework.school_class_id}, Section={homework.section_id}, Subject={homework.subject_id}",
            )
            return redirect('homework_manage')
        error = 'Please correct homework details.'
    else:
        form = HomeworkForm(instance=homework, school=school)

    return render(request, 'homework/form.html', {
        'form': form,
        'homework': homework,
        'error': error,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
@require_POST
def homework_toggle_publish(request, pk):
    homework = get_object_or_404(
        Homework,
        pk=pk,
        school=request.user.school
    )
    homework.is_published = not homework.is_published
    homework.save(update_fields=['is_published'])
    log_audit_event(
        request=request,
        action='homework.publish_toggled',
        school=request.user.school,
        target=homework,
        details=f"Published={homework.is_published}",
    )
    return redirect('homework_manage')


@login_required
@role_required(['schooladmin', 'teacher'])
@require_POST
def homework_delete(request, pk):
    homework = get_object_or_404(
        Homework,
        pk=pk,
        school=request.user.school
    )
    log_audit_event(
        request=request,
        action='homework.deleted',
        school=request.user.school,
        target=homework,
        details=f"Title={homework.title}",
    )
    homework.delete()
    return redirect('homework_manage')


@login_required
@role_required('parent')
def parent_homework_list(request):
    school = request.user.school
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

    homeworks = Homework.objects.none()
    if filter_query:
        homeworks = Homework.objects.filter(
            school=school,
            is_published=True
        ).filter(filter_query).select_related(
            'school_class',
            'section',
            'subject',
            'academic_session',
        ).order_by('due_date', '-id')

    rows = []
    for homework in homeworks:
        key = (homework.school_class_id, homework.section_id)
        rows.append({
            'homework': homework,
            'students': student_map.get(key, []),
        })

    return render(request, 'homework/parent_list.html', {
        'rows': rows,
    })
