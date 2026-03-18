from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.core.exams.models import Exam, ExamResultSummary
from apps.core.fees.services import student_outstanding_summary
from apps.core.hr.models import Payroll


def promotion_requires_clear_fees() -> bool:
    return bool(getattr(settings, 'PROMOTION_REQUIRE_CLEAR_FEES', False))


def student_result_summary(*, student, session):
    return ExamResultSummary.objects.filter(
        school=student.school,
        session=session,
        student=student,
        is_locked=True,
    ).select_related('exam', 'exam__exam_type').order_by('-exam__end_date', '-id').first()


def student_result_finalized(*, student, session) -> bool:
    return student_result_summary(student=student, session=session) is not None


def student_fee_due(*, student, session):
    return student_outstanding_summary(
        student=student,
        session=session,
        as_of_date=session.end_date,
    )['total_due']


def build_year_end_validation(*, school, session, require_clear_fees=None):
    require_clear_fees = promotion_requires_clear_fees() if require_clear_fees is None else require_clear_fees
    active_exams = Exam.objects.filter(
        school=school,
        session=session,
        is_active=True,
    )
    unlocked_exam_count = active_exams.filter(is_locked=False).count()
    results_generated = True
    if active_exams.exists():
        results_generated = not active_exams.filter(result_summaries__isnull=True).exists()

    pending_payroll_count = Payroll.objects.filter(
        school=school,
        session=session,
        is_locked=False,
    ).count()

    pending_fee_students = 0
    if require_clear_fees:
        student_qs = session.students_core.filter(is_archived=False).select_related('current_class', 'current_section')
        pending_fee_students = sum(
            1
            for student in student_qs
            if student_fee_due(student=student, session=session) > 0
        )

    attendance_finalized = bool(session.attendance_locked or session.is_locked)
    checks = {
        'session_open': not session.is_locked,
        'exams_locked': unlocked_exam_count == 0,
        'results_generated': results_generated,
        'attendance_finalized': attendance_finalized,
        'payroll_completed': pending_payroll_count == 0,
        'fees_reviewed': pending_fee_students == 0 if require_clear_fees else True,
    }

    errors = []
    if not checks['session_open']:
        errors.append('The selected session is already locked.')
    if not checks['exams_locked']:
        errors.append('All active exams must be locked before promotion.')
    if not checks['results_generated']:
        errors.append('Generate result summaries for all active exams before promotion.')
    if not checks['attendance_finalized']:
        errors.append('Attendance must be finalized before promotion.')
    if not checks['payroll_completed']:
        errors.append('All payroll rows must be locked before promotion.')
    if require_clear_fees and pending_fee_students:
        errors.append('Pending student dues must be cleared before promotion.')

    return {
        'checks': checks,
        'errors': errors,
        'unlocked_exam_count': unlocked_exam_count,
        'pending_payroll_count': pending_payroll_count,
        'pending_fee_students': pending_fee_students,
        'require_clear_fees': require_clear_fees,
    }


def validate_session_ready_for_promotion(*, school, session, require_clear_fees=None):
    snapshot = build_year_end_validation(
        school=school,
        session=session,
        require_clear_fees=require_clear_fees,
    )
    if snapshot['errors']:
        raise ValidationError(snapshot['errors'])
    return snapshot
