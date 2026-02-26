from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import ExamForm, ExamSubjectForm, ExamTypeForm, GradeScaleForm, MarkEntrySelectionForm
from .models import Exam, ExamResultSummary, ExamSubject, ExamType, GradeScale, StudentMark
from .services import (
    eligible_students_for_exam,
    generate_bulk_report_cards_pdf,
    generate_exam_results,
    generate_report_card_pdf,
    lock_exam_results,
    recalculate_exam_ranks,
    upsert_student_mark,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('session')

    selected_session = None
    if session_id and str(session_id).isdigit():
        selected_session = sessions.filter(id=int(session_id)).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


@login_required
@role_required('schooladmin')
def exam_type_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    types = ExamType.objects.filter(school=school)
    if selected_session:
        types = types.filter(session=selected_session)

    return render(request, 'exams_core/exam_type_list.html', {
        'exam_types': types.order_by('name'),
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def exam_type_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = ExamTypeForm(request.POST, school=school, default_session=selected_session)
        if form.is_valid():
            exam_type = form.save(commit=False)
            exam_type.school = school
            exam_type.save()
            log_audit_event(
                request=request,
                action='exams.exam_type_created',
                school=school,
                target=exam_type,
                details=f"Session={exam_type.session_id}, Name={exam_type.name}",
            )
            messages.success(request, 'Exam type created successfully.')
            return redirect('exam_type_list')
    else:
        form = ExamTypeForm(school=school, default_session=selected_session)

    return render(request, 'exams_core/exam_type_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def exam_type_update(request, pk):
    school = request.user.school
    exam_type = get_object_or_404(ExamType, pk=pk, school=school)

    if request.method == 'POST':
        form = ExamTypeForm(request.POST, instance=exam_type, school=school, default_session=exam_type.session)
        if form.is_valid():
            exam_type = form.save()
            log_audit_event(
                request=request,
                action='exams.exam_type_updated',
                school=school,
                target=exam_type,
                details=f"Session={exam_type.session_id}, Name={exam_type.name}",
            )
            messages.success(request, 'Exam type updated successfully.')
            return redirect('exam_type_list')
    else:
        form = ExamTypeForm(instance=exam_type, school=school, default_session=exam_type.session)

    return render(request, 'exams_core/exam_type_form.html', {
        'form': form,
        'exam_type': exam_type,
    })


@login_required
@role_required('schooladmin')
@require_POST
def exam_type_deactivate(request, pk):
    exam_type = get_object_or_404(ExamType, pk=pk, school=request.user.school)
    exam_type.delete()
    log_audit_event(
        request=request,
        action='exams.exam_type_deactivated',
        school=request.user.school,
        target=exam_type,
        details=f"Name={exam_type.name}",
    )
    messages.success(request, 'Exam type deactivated.')
    return redirect('exam_type_list')


@login_required
@role_required('schooladmin')
def exam_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    exams = Exam.objects.filter(school=school).select_related(
        'session',
        'exam_type',
        'school_class',
        'section',
    )
    if selected_session:
        exams = exams.filter(session=selected_session)

    return render(request, 'exams_core/exam_list.html', {
        'exams': exams.order_by('-start_date', '-id'),
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def exam_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = ExamForm(request.POST, school=school, default_session=selected_session)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.school = school
            exam.created_by = request.user
            exam.save()
            log_audit_event(
                request=request,
                action='exams.exam_created',
                school=school,
                target=exam,
                details=f"ExamType={exam.exam_type_id}, Class={exam.school_class_id}, Section={exam.section_id or '-'}",
            )
            messages.success(request, 'Exam created successfully.')
            return redirect('exam_list_core')
    else:
        form = ExamForm(school=school, default_session=selected_session)

    return render(request, 'exams_core/exam_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def exam_update(request, pk):
    school = request.user.school
    exam = get_object_or_404(Exam, pk=pk, school=school)

    if request.method == 'POST':
        form = ExamForm(request.POST, instance=exam, school=school, default_session=exam.session)
        if form.is_valid():
            try:
                exam = form.save()
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='exams.exam_updated',
                    school=school,
                    target=exam,
                    details=f"ExamType={exam.exam_type_id}, Class={exam.school_class_id}, Section={exam.section_id or '-'}",
                )
                messages.success(request, 'Exam updated successfully.')
                return redirect('exam_list_core')
    else:
        form = ExamForm(instance=exam, school=school, default_session=exam.session)

    return render(request, 'exams_core/exam_form.html', {
        'form': form,
        'exam': exam,
    })


@login_required
@role_required('schooladmin')
@require_POST
def exam_lock(request, pk):
    exam = get_object_or_404(Exam, pk=pk, school=request.user.school)
    try:
        if not exam.result_summaries.exists():
            generate_exam_results(exam=exam)
        lock_info = lock_exam_results(exam=exam)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='exams.exam_locked',
            school=request.user.school,
            target=exam,
            details=(
                f"MarksLocked={lock_info['marks_locked']}, "
                f"SummariesLocked={lock_info['summaries_locked']}"
            ),
        )
        messages.success(request, 'Exam results locked successfully.')
    return redirect('exam_result_summary', exam_id=exam.id)


@login_required
@role_required('schooladmin')
def exam_subject_manage(request, exam_id):
    school = request.user.school
    exam = get_object_or_404(
        Exam.objects.select_related('exam_type', 'school_class', 'section', 'session'),
        pk=exam_id,
        school=school,
    )

    if request.method == 'POST':
        form = ExamSubjectForm(request.POST, exam=exam)
        if form.is_valid():
            exam_subject = form.save(commit=False)
            exam_subject.exam = exam
            try:
                exam_subject.save()
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='exams.exam_subject_added',
                    school=school,
                    target=exam_subject,
                    details=f"Exam={exam.id}, Subject={exam_subject.subject_id}",
                )
                messages.success(request, 'Exam subject configuration saved.')
                return redirect('exam_subject_manage', exam_id=exam.id)
    else:
        form = ExamSubjectForm(exam=exam)

    subjects = exam.exam_subjects.select_related('subject').order_by('subject__name')
    return render(request, 'exams_core/exam_subject_manage.html', {
        'exam': exam,
        'form': form,
        'subjects': subjects,
    })


@login_required
@role_required('schooladmin')
def exam_subject_update(request, exam_id, pk):
    school = request.user.school
    exam = get_object_or_404(Exam, pk=exam_id, school=school)
    exam_subject = get_object_or_404(ExamSubject, pk=pk, exam=exam)

    if request.method == 'POST':
        form = ExamSubjectForm(request.POST, instance=exam_subject, exam=exam)
        if form.is_valid():
            try:
                exam_subject = form.save()
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='exams.exam_subject_updated',
                    school=school,
                    target=exam_subject,
                    details=f"Exam={exam.id}, Subject={exam_subject.subject_id}",
                )
                messages.success(request, 'Exam subject updated successfully.')
                return redirect('exam_subject_manage', exam_id=exam.id)
    else:
        form = ExamSubjectForm(instance=exam_subject, exam=exam)

    return render(request, 'exams_core/exam_subject_form.html', {
        'form': form,
        'exam': exam,
        'exam_subject': exam_subject,
    })


@login_required
@role_required('schooladmin')
@require_POST
def exam_subject_deactivate(request, exam_id, pk):
    school = request.user.school
    exam = get_object_or_404(Exam, pk=exam_id, school=school)
    exam_subject = get_object_or_404(ExamSubject, pk=pk, exam=exam)
    try:
        exam_subject.delete()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='exams.exam_subject_deactivated',
            school=school,
            target=exam_subject,
            details=f"Exam={exam.id}, Subject={exam_subject.subject_id}",
        )
        messages.success(request, 'Exam subject deactivated.')
    return redirect('exam_subject_manage', exam_id=exam.id)


@login_required
@role_required('schooladmin')
def grade_scale_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    grades = GradeScale.objects.filter(school=school)
    if selected_session:
        grades = grades.filter(session=selected_session)

    return render(request, 'exams_core/grade_scale_list.html', {
        'grades': grades.order_by('display_order', '-max_percentage'),
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def grade_scale_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = GradeScaleForm(request.POST, school=school, default_session=selected_session)
        if form.is_valid():
            grade = form.save(commit=False)
            grade.school = school
            grade.save()
            log_audit_event(
                request=request,
                action='exams.grade_scale_created',
                school=school,
                target=grade,
                details=f"Session={grade.session_id}, Grade={grade.grade_name}",
            )
            messages.success(request, 'Grade scale created successfully.')
            return redirect('grade_scale_list_core')
    else:
        form = GradeScaleForm(school=school, default_session=selected_session)

    return render(request, 'exams_core/grade_scale_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def grade_scale_update(request, pk):
    school = request.user.school
    grade = get_object_or_404(GradeScale, pk=pk, school=school)

    if request.method == 'POST':
        form = GradeScaleForm(request.POST, instance=grade, school=school, default_session=grade.session)
        if form.is_valid():
            grade = form.save()
            log_audit_event(
                request=request,
                action='exams.grade_scale_updated',
                school=school,
                target=grade,
                details=f"Session={grade.session_id}, Grade={grade.grade_name}",
            )
            messages.success(request, 'Grade scale updated successfully.')
            return redirect('grade_scale_list_core')
    else:
        form = GradeScaleForm(instance=grade, school=school, default_session=grade.session)

    return render(request, 'exams_core/grade_scale_form.html', {
        'form': form,
        'grade': grade,
    })


@login_required
@role_required('schooladmin')
@require_POST
def grade_scale_deactivate(request, pk):
    grade = get_object_or_404(GradeScale, pk=pk, school=request.user.school)
    grade.delete()
    log_audit_event(
        request=request,
        action='exams.grade_scale_deactivated',
        school=request.user.school,
        target=grade,
        details=f"Grade={grade.grade_name}",
    )
    messages.success(request, 'Grade scale deactivated.')
    return redirect('grade_scale_list_core')


@login_required
@role_required(['schooladmin', 'teacher'])
def marks_entry(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    selection_form = MarkEntrySelectionForm(
        request.POST or request.GET or None,
        school=school,
        default_session=selected_session,
    )

    selected_exam = None
    selected_subject = None
    student_rows = []

    if selection_form.is_valid():
        selected_exam = selection_form.cleaned_data['exam']
        selected_subject = selection_form.cleaned_data['subject']

        students = eligible_students_for_exam(selected_exam)
        marks_map = {
            row.student_id: row
            for row in StudentMark.objects.filter(
                exam=selected_exam,
                subject=selected_subject,
            ).select_related('student')
        }

        for student in students:
            mark_row = marks_map.get(student.id)
            student_rows.append({
                'student': student,
                'marks': mark_row.marks_obtained if mark_row else '',
                'remarks': mark_row.remarks if mark_row else '',
                'grade': mark_row.grade if mark_row else '',
            })

        if request.method == 'POST' and request.POST.get('action') == 'save':
            save_errors = []
            for row in student_rows:
                mark_value = request.POST.get(f"marks_{row['student'].id}", '').strip()
                remarks_value = request.POST.get(f"remarks_{row['student'].id}", '').strip()

                if mark_value == '':
                    save_errors.append(f"Marks missing for {row['student'].admission_number}.")
                    continue

                try:
                    marks_decimal = Decimal(mark_value)
                except (InvalidOperation, TypeError):
                    save_errors.append(f"Invalid marks for {row['student'].admission_number}.")
                    continue

                try:
                    upsert_student_mark(
                        exam=selected_exam,
                        student=row['student'],
                        subject_id=selected_subject.id,
                        marks_obtained=marks_decimal,
                        entered_by=request.user,
                        remarks=remarks_value,
                    )
                except ValidationError as exc:
                    save_errors.extend(exc.messages)

            if save_errors:
                messages.error(request, '; '.join(save_errors))
            else:
                try:
                    recalculate_exam_ranks(exam=selected_exam)
                except ValidationError:
                    pass
                log_audit_event(
                    request=request,
                    action='exams.marks_saved',
                    school=school,
                    target=selected_exam,
                    details=f"Exam={selected_exam.id}, Subject={selected_subject.id}",
                )
                messages.success(request, 'Marks saved successfully.')
                query = f"exam={selected_exam.id}&subject={selected_subject.id}"
                return redirect(f"{reverse('marks_entry_core')}?{query}")

    return render(request, 'exams_core/marks_entry.html', {
        'selection_form': selection_form,
        'selected_exam': selected_exam,
        'selected_subject': selected_subject,
        'student_rows': student_rows,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def exam_result_summary(request, exam_id):
    school = request.user.school
    exam = get_object_or_404(
        Exam.objects.select_related('exam_type', 'school_class', 'section', 'session'),
        pk=exam_id,
        school=school,
    )

    summaries = ExamResultSummary.objects.filter(
        exam=exam,
        school=school,
    ).select_related('student').order_by('rank', '-percentage', 'student__admission_number')

    return render(request, 'exams_core/result_summary.html', {
        'exam': exam,
        'summaries': summaries,
    })


@login_required
@role_required('schooladmin')
@require_POST
def exam_result_generate(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, school=request.user.school)
    try:
        generated = generate_exam_results(exam=exam)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='exams.results_generated',
            school=request.user.school,
            target=exam,
            details=f"Exam={exam.id}, Count={len(generated)}",
        )
        messages.success(request, 'Results generated successfully.')
    return redirect('exam_result_summary', exam_id=exam.id)


@login_required
@role_required(['schooladmin', 'teacher'])
def report_card_download(request, exam_id, student_id):
    school = request.user.school
    summary = get_object_or_404(
        ExamResultSummary.objects.select_related('exam', 'student'),
        school=school,
        exam_id=exam_id,
        student_id=student_id,
    )

    teacher_remarks = (request.GET.get('teacher_remarks') or '').strip()
    principal_signature = (request.GET.get('principal_signature') or '').strip()

    pdf_bytes = generate_report_card_pdf(
        summary=summary,
        teacher_remarks=teacher_remarks,
        principal_signature=principal_signature,
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename=\"report_card_{summary.exam_id}_{summary.student.admission_number}.pdf\"'
    )
    return response


@login_required
@role_required(['schooladmin', 'teacher'])
def report_card_bulk_download(request, exam_id):
    school = request.user.school
    exam = get_object_or_404(Exam, pk=exam_id, school=school)
    summaries = list(
        ExamResultSummary.objects.filter(
            school=school,
            exam=exam,
        ).select_related('student').order_by('rank', 'student__admission_number')
    )
    if not summaries:
        messages.error(request, 'No result summaries found. Generate results first.')
        return redirect('exam_result_summary', exam_id=exam.id)

    teacher_remarks = (request.GET.get('teacher_remarks') or '').strip()
    principal_signature = (request.GET.get('principal_signature') or '').strip()
    pdf_bytes = generate_bulk_report_cards_pdf(
        summaries=summaries,
        teacher_remarks=teacher_remarks,
        principal_signature=principal_signature,
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=\"report_cards_exam_{exam.id}.pdf\"'
    return response
