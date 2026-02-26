from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from PIL import Image, ImageDraw
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.attendance.models import StudentAttendanceSummary
from apps.core.hr.models import Staff, TeacherSubjectAssignment
from apps.core.students.models import Student, StudentSessionRecord, image_to_pdf_bytes

from .models import Exam, ExamResultSummary, ExamSubject, GradeScale, StudentMark


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _active_exam_subjects(exam: Exam):
    return list(
        ExamSubject.objects.filter(
            exam=exam,
            is_active=True,
        ).select_related('subject').order_by('subject__name', 'id')
    )


def eligible_students_for_exam(exam: Exam):
    records = StudentSessionRecord.objects.filter(
        school=exam.school,
        session=exam.session,
        school_class=exam.school_class,
    ).select_related('student', 'section')
    if exam.section_id:
        records = records.filter(section=exam.section)
    student_ids = records.values_list('student_id', flat=True)
    return Student.objects.filter(
        id__in=student_ids,
        is_archived=False,
    ).order_by('admission_number')


def grade_for_percentage(*, school, session, percentage: Decimal) -> str:
    scale = GradeScale.objects.filter(
        school=school,
        session=session,
        is_active=True,
        min_percentage__lte=percentage,
        max_percentage__gte=percentage,
    ).order_by('display_order', '-max_percentage').first()
    return scale.grade_name if scale else ''


def _attendance_percentage(student: Student, session) -> Decimal | None:
    summary = StudentAttendanceSummary.objects.filter(
        school=student.school,
        session=session,
        student=student,
    ).order_by('-year', '-month').first()
    if not summary:
        return None
    return summary.attendance_percentage


def _teacher_allowed_to_enter(*, user, exam: Exam, subject_id: int) -> bool:
    if user.role != 'teacher':
        return user.role == 'schooladmin'

    staff = Staff.objects.filter(
        school=exam.school,
        user=user,
        is_active=True,
    ).first()
    if not staff:
        return False

    return TeacherSubjectAssignment.objects.filter(
        school=exam.school,
        session=exam.session,
        teacher=staff,
        school_class=exam.school_class,
        subject_id=subject_id,
        is_active=True,
    ).exists()


@transaction.atomic
def upsert_student_mark(
    *,
    exam: Exam,
    student: Student,
    subject_id: int,
    marks_obtained,
    entered_by,
    remarks='',
    allow_override=False,
):
    if exam.is_locked and not allow_override:
        raise ValidationError('Exam is locked. Marks entry is not allowed.')

    if not _teacher_allowed_to_enter(user=entered_by, exam=exam, subject_id=subject_id) and not allow_override:
        raise ValidationError('You are not allowed to enter marks for this class-subject.')

    exam_subject = ExamSubject.objects.filter(
        exam=exam,
        subject_id=subject_id,
        is_active=True,
    ).select_related('subject').first()
    if not exam_subject:
        raise ValidationError('Selected subject is not configured for this exam.')

    if not StudentSessionRecord.objects.filter(
        student=student,
        school=exam.school,
        session=exam.session,
        school_class=exam.school_class,
        section=exam.section if exam.section_id else student.current_section,
    ).exists():
        if exam.section_id:
            raise ValidationError('Student does not belong to selected exam class-section.')
        if not StudentSessionRecord.objects.filter(
            student=student,
            school=exam.school,
            session=exam.session,
            school_class=exam.school_class,
        ).exists():
            raise ValidationError('Student does not belong to selected exam class.')

    try:
        marks_decimal = Decimal(str(marks_obtained))
    except Exception as exc:
        raise ValidationError('Marks must be a numeric value.') from exc

    if marks_decimal < 0:
        raise ValidationError('Marks cannot be negative.')
    if marks_decimal > exam_subject.max_marks:
        raise ValidationError(f'Marks cannot exceed {exam_subject.max_marks}.')

    subject_percentage = Decimal('0.00')
    if exam_subject.max_marks > 0:
        subject_percentage = _quantize((marks_decimal / exam_subject.max_marks) * Decimal('100'))
    subject_grade = grade_for_percentage(
        school=exam.school,
        session=exam.session,
        percentage=subject_percentage,
    )

    mark, created = StudentMark.objects.get_or_create(
        school=exam.school,
        session=exam.session,
        student=student,
        exam=exam,
        subject=exam_subject.subject,
        defaults={
            'marks_obtained': marks_decimal,
            'grade': subject_grade,
            'remarks': (remarks or '')[:255],
            'entered_by': entered_by,
        },
    )

    if created:
        mark.full_clean()
        mark.save()
        return mark, created

    if mark.is_locked and not allow_override:
        raise ValidationError('This mark record is locked.')

    mark.marks_obtained = marks_decimal
    mark.grade = subject_grade
    mark.remarks = (remarks or '')[:255]
    mark.entered_by = entered_by
    mark.full_clean()
    mark.save()
    return mark, created


@transaction.atomic
def calculate_student_result(*, exam: Exam, student: Student, allow_override=False):
    exam_subjects = _active_exam_subjects(exam)
    if not exam_subjects:
        raise ValidationError('Cannot calculate result without active exam subjects.')

    marks = StudentMark.objects.filter(
        school=exam.school,
        session=exam.session,
        exam=exam,
        student=student,
        subject_id__in=[row.subject_id for row in exam_subjects],
    ).select_related('subject')

    mark_map = {row.subject_id: row for row in marks}
    missing = [row.subject.code for row in exam_subjects if row.subject_id not in mark_map]
    if missing:
        raise ValidationError(
            f"Missing marks for {student.admission_number}: {', '.join(missing)}."
        )

    total_max = Decimal('0.00')
    total_obtained = Decimal('0.00')
    all_passed = True

    for exam_subject in exam_subjects:
        mark = mark_map[exam_subject.subject_id]
        total_max += exam_subject.max_marks
        total_obtained += mark.marks_obtained
        if mark.marks_obtained < exam_subject.pass_marks:
            all_passed = False

    percentage = Decimal('0.00')
    if total_max > 0:
        percentage = _quantize((total_obtained / total_max) * Decimal('100'))
    grade = grade_for_percentage(school=exam.school, session=exam.session, percentage=percentage)

    summary, created = ExamResultSummary.objects.get_or_create(
        school=exam.school,
        session=exam.session,
        student=student,
        exam=exam,
        defaults={
            'total_marks': _quantize(total_obtained),
            'percentage': percentage,
            'grade': grade,
            'attendance_percentage': _attendance_percentage(student, exam.session),
            'result_status': ExamResultSummary.STATUS_PASS if all_passed else ExamResultSummary.STATUS_FAIL,
            'rank': None,
            'is_locked': exam.is_locked,
        },
    )

    if not created:
        if summary.is_locked and not allow_override:
            raise ValidationError('Result summary is locked and cannot be recalculated.')

        summary.total_marks = _quantize(total_obtained)
        summary.percentage = percentage
        summary.grade = grade
        summary.attendance_percentage = _attendance_percentage(student, exam.session)
        summary.result_status = (
            ExamResultSummary.STATUS_PASS if all_passed else ExamResultSummary.STATUS_FAIL
        )
        if exam.is_locked:
            summary.is_locked = True
        summary.full_clean()
        summary.save()
    else:
        summary.full_clean()
        summary.save()

    return summary


@transaction.atomic
def recalculate_exam_ranks(*, exam: Exam, allow_override=False):
    summaries = list(
        ExamResultSummary.objects.filter(
            school=exam.school,
            session=exam.session,
            exam=exam,
        ).select_related('student').order_by(
            '-percentage',
            '-total_marks',
            'student__admission_number',
        )
    )

    current_rank = 0
    prev_key = None
    for index, summary in enumerate(summaries, start=1):
        if summary.is_locked and not allow_override:
            continue

        key = (summary.percentage, summary.total_marks)
        if key != prev_key:
            current_rank = index
            prev_key = key

        if summary.rank != current_rank:
            summary.rank = current_rank
            summary.save(update_fields=['rank', 'generated_at'])

    return summaries


@transaction.atomic
def generate_exam_results(*, exam: Exam, allow_override=False):
    if exam.is_locked and not allow_override:
        raise ValidationError('Exam results are locked.')

    students = list(eligible_students_for_exam(exam))
    if not students:
        raise ValidationError('No eligible students found for this exam.')

    summaries = []
    missing_errors = []
    for student in students:
        try:
            summaries.append(calculate_student_result(exam=exam, student=student, allow_override=allow_override))
        except ValidationError as exc:
            missing_errors.extend(exc.messages)

    if missing_errors:
        raise ValidationError(missing_errors)

    recalculate_exam_ranks(exam=exam, allow_override=allow_override)
    return summaries


@transaction.atomic
def lock_exam_results(*, exam: Exam):
    exam.is_locked = True
    exam.save(update_fields=['is_locked', 'updated_at'])
    marks_locked = StudentMark.objects.filter(exam=exam).update(is_locked=True)
    summaries_locked = ExamResultSummary.objects.filter(exam=exam).update(is_locked=True)
    return {
        'marks_locked': marks_locked,
        'summaries_locked': summaries_locked,
    }


@transaction.atomic
def unlock_exam_results(*, exam: Exam, allow_override=False):
    if not allow_override:
        raise ValidationError('Only super admin override can unlock exam results.')
    exam.is_locked = False
    exam.save(update_fields=['is_locked', 'updated_at'])
    StudentMark.objects.filter(exam=exam).update(is_locked=False)
    ExamResultSummary.objects.filter(exam=exam).update(is_locked=False)
    return exam


def build_report_card_image(*, summary: ExamResultSummary, teacher_remarks='', principal_signature=''):
    width = 1240
    height = 1754
    page = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(page)

    exam = summary.exam
    student = summary.student

    draw.rectangle((30, 30, width - 30, height - 30), outline='black', width=3)
    draw.text((60, 60), f"{summary.school.name} - Report Card", fill='black')
    draw.text((60, 110), f"Exam: {exam.exam_type.name}", fill='black')
    draw.text((60, 150), f"Session: {summary.session.name}", fill='black')
    draw.text((60, 190), f"Student: {student.full_name} ({student.admission_number})", fill='black')
    draw.text((60, 230), f"Class: {exam.school_class.name}", fill='black')
    draw.text((300, 230), f"Section: {(exam.section.name if exam.section_id else student.current_section.name if student.current_section_id else '-')}", fill='black')

    draw.text((60, 285), 'Subject', fill='black')
    draw.text((520, 285), 'Max', fill='black')
    draw.text((640, 285), 'Pass', fill='black')
    draw.text((760, 285), 'Obtained', fill='black')
    draw.text((930, 285), 'Grade', fill='black')
    draw.line((60, 310, width - 60, 310), fill='black')

    subject_rows = _active_exam_subjects(exam)
    marks = {
        row.subject_id: row
        for row in StudentMark.objects.filter(exam=exam, student=student).select_related('subject')
    }

    y = 330
    for row in subject_rows:
        mark = marks.get(row.subject_id)
        draw.text((60, y), row.subject.name, fill='black')
        draw.text((520, y), str(row.max_marks), fill='black')
        draw.text((640, y), str(row.pass_marks), fill='black')
        draw.text((760, y), str(mark.marks_obtained if mark else '-'), fill='black')
        draw.text((930, y), mark.grade if mark else '-', fill='black')
        y += 38

    y += 24
    draw.line((60, y, width - 60, y), fill='black')
    y += 24
    draw.text((60, y), f"Total Marks: {summary.total_marks}", fill='black')
    y += 36
    draw.text((60, y), f"Percentage: {summary.percentage}%", fill='black')
    y += 36
    draw.text((60, y), f"Grade: {summary.grade or '-'}", fill='black')
    y += 36
    draw.text((60, y), f"Rank: {summary.rank or '-'}", fill='black')
    y += 36
    draw.text((60, y), f"Result Status: {summary.get_result_status_display()}", fill='black')
    y += 36
    draw.text((60, y), f"Attendance %: {summary.attendance_percentage if summary.attendance_percentage is not None else '-'}", fill='black')
    y += 60

    draw.text((60, y), f"Teacher Remarks: {teacher_remarks or '-'}", fill='black')
    y += 120
    draw.text((60, y), f"Principal Signature: {principal_signature or '____________________'}", fill='black')

    return page


def generate_report_card_pdf(*, summary: ExamResultSummary, teacher_remarks='', principal_signature=''):
    image = build_report_card_image(
        summary=summary,
        teacher_remarks=teacher_remarks,
        principal_signature=principal_signature,
    )
    return image_to_pdf_bytes([image])


def generate_bulk_report_cards_pdf(
    *,
    summaries: Iterable[ExamResultSummary],
    teacher_remarks='',
    principal_signature='',
):
    pages = [
        build_report_card_image(
            summary=summary,
            teacher_remarks=teacher_remarks,
            principal_signature=principal_signature,
        )
        for summary in summaries
    ]
    return image_to_pdf_bytes(pages)
