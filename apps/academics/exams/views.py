from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.academics.students.models import Student
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import ExamForm, ExamScheduleForm
from .models import Exam, ExamSchedule


@login_required
@role_required('schooladmin')
def exam_manage(request):
    school = request.user.school
    error = None
    exams = Exam.objects.filter(
        school=school
    ).select_related('academic_session', 'created_by').order_by(
        '-academic_session__start_date', '-start_date', 'name'
    )

    if request.method == 'POST':
        form = ExamForm(request.POST, school=school)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.school = school
            exam.created_by = request.user
            exam.save()
            log_audit_event(
                request=request,
                action='exam.created',
                school=school,
                target=exam,
                details=f"Session={exam.academic_session_id}, Name={exam.name}",
            )
            return redirect('exam_manage')
        error = 'Please correct exam details.'
    else:
        form = ExamForm(school=school)

    return render(request, 'exams/manage.html', {
        'form': form,
        'exams': exams,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def exam_update(request, pk):
    school = request.user.school
    exam = get_object_or_404(
        Exam,
        pk=pk,
        school=school
    )
    error = None

    if request.method == 'POST':
        form = ExamForm(request.POST, instance=exam, school=school)
        if form.is_valid():
            exam = form.save()
            log_audit_event(
                request=request,
                action='exam.updated',
                school=school,
                target=exam,
                details=f"Session={exam.academic_session_id}, Name={exam.name}",
            )
            return redirect('exam_manage')
        error = 'Please correct exam details.'
    else:
        form = ExamForm(instance=exam, school=school)

    return render(request, 'exams/form.html', {
        'form': form,
        'exam': exam,
        'error': error,
    })


@login_required
@role_required('schooladmin')
@require_POST
def exam_toggle_publish(request, pk):
    exam = get_object_or_404(Exam, pk=pk, school=request.user.school)
    exam.is_published = not exam.is_published
    exam.save(update_fields=['is_published'])
    log_audit_event(
        request=request,
        action='exam.publish_toggled',
        school=request.user.school,
        target=exam,
        details=f"Published={exam.is_published}",
    )
    return redirect('exam_manage')


@login_required
@role_required('schooladmin')
@require_POST
def exam_delete(request, pk):
    exam = get_object_or_404(Exam, pk=pk, school=request.user.school)
    log_audit_event(
        request=request,
        action='exam.deleted',
        school=request.user.school,
        target=exam,
        details=f"Name={exam.name}",
    )
    exam.delete()
    return redirect('exam_manage')


@login_required
@role_required('schooladmin')
def exam_schedule_manage(request, exam_id):
    school = request.user.school
    exam = get_object_or_404(
        Exam,
        pk=exam_id,
        school=school
    )
    error = None
    schedules = ExamSchedule.objects.filter(
        school=school,
        exam=exam
    ).select_related(
        'school_class',
        'section',
        'subject',
        'invigilator',
    ).order_by('date', 'start_time', 'school_class__order', 'section__name')

    if request.method == 'POST':
        form = ExamScheduleForm(request.POST, school=school, exam=exam)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.school = school
            schedule.exam = exam
            try:
                schedule.save()
            except IntegrityError:
                error = 'This subject schedule already exists for the selected exam/class/section.'
            else:
                log_audit_event(
                    request=request,
                    action='exam.schedule_created',
                    school=school,
                    target=schedule,
                    details=f"Exam={exam.id}, Class={schedule.school_class_id}, Section={schedule.section_id}, Subject={schedule.subject_id}",
                )
                return redirect('exam_schedule_manage', exam_id=exam.id)
        elif not error:
            error = 'Please correct exam schedule details.'
    else:
        form = ExamScheduleForm(school=school, exam=exam)

    return render(request, 'exams/schedule_manage.html', {
        'exam': exam,
        'form': form,
        'schedules': schedules,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def exam_schedule_update(request, exam_id, pk):
    school = request.user.school
    exam = get_object_or_404(
        Exam,
        pk=exam_id,
        school=school
    )
    schedule = get_object_or_404(
        ExamSchedule,
        pk=pk,
        school=school,
        exam=exam,
    )
    error = None

    if request.method == 'POST':
        form = ExamScheduleForm(request.POST, instance=schedule, school=school, exam=exam)
        if form.is_valid():
            schedule = form.save()
            log_audit_event(
                request=request,
                action='exam.schedule_updated',
                school=school,
                target=schedule,
                details=f"Exam={exam.id}, Class={schedule.school_class_id}, Section={schedule.section_id}, Subject={schedule.subject_id}",
            )
            return redirect('exam_schedule_manage', exam_id=exam.id)
        error = 'Please correct exam schedule details.'
    else:
        form = ExamScheduleForm(instance=schedule, school=school, exam=exam)

    return render(request, 'exams/schedule_form.html', {
        'exam': exam,
        'form': form,
        'schedule': schedule,
        'error': error,
    })


@login_required
@role_required('schooladmin')
@require_POST
def exam_schedule_delete(request, exam_id, pk):
    schedule = get_object_or_404(
        ExamSchedule,
        pk=pk,
        school=request.user.school,
        exam_id=exam_id,
    )
    log_audit_event(
        request=request,
        action='exam.schedule_deleted',
        school=request.user.school,
        target=schedule,
        details=f"Exam={schedule.exam_id}, Subject={schedule.subject_id}",
    )
    schedule.delete()
    return redirect('exam_schedule_manage', exam_id=exam_id)


@login_required
@role_required('teacher')
def teacher_exam_schedule(request):
    school = request.user.school
    staff_profile = getattr(request.user, 'staff_profile', None)
    schedules = ExamSchedule.objects.filter(
        school=school,
        exam__is_published=True,
        is_active=True,
    ).select_related(
        'exam',
        'exam__academic_session',
        'school_class',
        'section',
        'subject',
        'invigilator',
    ).order_by('date', 'start_time', 'school_class__order', 'section__name')

    if school.current_session:
        schedules = schedules.filter(exam__academic_session=school.current_session)

    invigilator_ids = set()
    if staff_profile and staff_profile.school_id == school.id:
        invigilator_ids = set(
            schedules.filter(invigilator=staff_profile).values_list('id', flat=True)
        )

    rows = []
    for schedule in schedules:
        rows.append({
            'schedule': schedule,
            'is_invigilator': schedule.id in invigilator_ids,
        })

    return render(request, 'exams/teacher_schedule.html', {
        'rows': rows,
        'current_session': school.current_session,
    })


@login_required
@role_required('parent')
def parent_exam_schedule(request):
    school = request.user.school
    current_session = school.current_session
    children = Student.objects.filter(
        school=school,
        parent_user=request.user
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

    schedules = ExamSchedule.objects.none()
    if filter_query:
        schedules = ExamSchedule.objects.filter(
            school=school,
            exam__is_published=True,
            is_active=True,
        ).filter(filter_query).select_related(
            'exam',
            'exam__academic_session',
            'school_class',
            'section',
            'subject',
            'invigilator',
        ).order_by('date', 'start_time', 'school_class__order', 'section__name')

        if current_session:
            schedules = schedules.filter(exam__academic_session=current_session)

    rows = []
    for schedule in schedules:
        key = (schedule.school_class_id, schedule.section_id)
        rows.append({
            'schedule': schedule,
            'students': student_map.get(key, []),
        })

    return render(request, 'exams/parent_schedule.html', {
        'rows': rows,
        'current_session': current_session,
    })
