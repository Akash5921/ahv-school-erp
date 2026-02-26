from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession

from .models import (
    ClassTeacher,
    LeaveRequest,
    SalaryHistory,
    SalaryStructure,
    Staff,
    StaffAttendance,
    Substitution,
    TeacherSubjectAssignment,
)


def _attendance_edit_window_hours() -> int:
    return int(getattr(settings, 'STAFF_ATTENDANCE_EDIT_WINDOW_HOURS', 6))


def _date_range(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


@transaction.atomic
def assign_teacher_subject(*, school, session, teacher, school_class, subject, is_active=True):
    assignment, created = TeacherSubjectAssignment.objects.get_or_create(
        school=school,
        session=session,
        teacher=teacher,
        school_class=school_class,
        subject=subject,
        defaults={'is_active': is_active},
    )

    if not created and assignment.is_active != is_active:
        assignment.is_active = is_active
        assignment.full_clean()
        assignment.save(update_fields=['is_active'])

    if created:
        assignment.full_clean()
        assignment.save()

    return assignment


@transaction.atomic
def assign_class_teacher(*, school, session, school_class, section, teacher):
    assignment, created = ClassTeacher.objects.get_or_create(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        teacher=teacher,
        defaults={'is_active': True},
    )

    if not created and not assignment.is_active:
        assignment.is_active = True

    assignment.full_clean()
    assignment.save()
    return assignment


@transaction.atomic
def mark_staff_attendance(
    *,
    school,
    staff,
    date,
    status,
    session=None,
    marked_by=None,
    check_in_time=None,
    check_out_time=None,
    ip_address='',
    device_info='',
    allow_override=False,
):
    if staff.school_id != school.id:
        raise ValidationError('Staff does not belong to selected school.')

    session = session or school.current_session
    if not session:
        raise ValidationError('No active academic session found for the selected school.')
    if session.school_id != school.id:
        raise ValidationError('Selected session does not belong to selected school.')

    today = timezone.localdate()
    if date > today:
        raise ValidationError('Cannot mark staff attendance for a future date.')
    if date < session.start_date or date > session.end_date:
        raise ValidationError('Attendance date must be within session date range.')
    if session.attendance_locked and not allow_override:
        raise ValidationError('Attendance is locked for this session.')

    attendance, created = StaffAttendance.objects.get_or_create(
        school=school,
        session=session,
        staff=staff,
        date=date,
        defaults={
            'status': status,
            'check_in_time': check_in_time,
            'check_out_time': check_out_time,
            'marked_by': marked_by,
            'ip_address': ip_address,
            'device_info': device_info,
        },
    )

    if created:
        attendance.full_clean()
        attendance.save()
        return attendance, created

    if attendance.is_locked and not allow_override:
        raise ValidationError('Attendance record is locked and cannot be edited.')

    edit_deadline = attendance.created_at + timedelta(hours=_attendance_edit_window_hours())
    if not allow_override and timezone.now() > edit_deadline:
        raise ValidationError('Attendance edit window has expired for this record.')

    attendance.status = status
    attendance.check_in_time = check_in_time
    attendance.check_out_time = check_out_time
    attendance.marked_by = marked_by
    attendance.ip_address = ip_address
    attendance.device_info = device_info
    attendance.edited_at = timezone.now()
    attendance.full_clean()
    attendance.save()
    return attendance, created


@transaction.atomic
def submit_leave_request(*, school, staff, leave_type, start_date, end_date, reason):
    leave_request = LeaveRequest(
        school=school,
        staff=staff,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    leave_request.full_clean()
    leave_request.save()
    return leave_request


@transaction.atomic
def review_leave_request(*, leave_request, approved_by, decision):
    if leave_request.status != LeaveRequest.STATUS_PENDING:
        raise ValidationError('Only pending leave requests can be reviewed.')

    if decision not in {LeaveRequest.STATUS_APPROVED, LeaveRequest.STATUS_REJECTED}:
        raise ValidationError('Invalid leave decision.')

    leave_request.status = decision
    leave_request.approved_by = approved_by
    leave_request.approved_at = timezone.now()
    leave_request.full_clean()
    leave_request.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

    if decision == LeaveRequest.STATUS_APPROVED:
        for leave_date in _date_range(leave_request.start_date, leave_request.end_date):
            session = AcademicSession.objects.filter(
                school=leave_request.school,
                start_date__lte=leave_date,
                end_date__gte=leave_date,
            ).order_by('-is_active', '-start_date').first()

            attendance, _ = StaffAttendance.objects.get_or_create(
                school=leave_request.school,
                session=session,
                staff=leave_request.staff,
                date=leave_date,
                defaults={
                    'status': StaffAttendance.STATUS_LEAVE,
                    'marked_by': approved_by,
                },
            )
            if attendance.status != StaffAttendance.STATUS_LEAVE:
                attendance.status = StaffAttendance.STATUS_LEAVE
                attendance.check_in_time = None
                attendance.check_out_time = None
                attendance.marked_by = approved_by
                attendance.edited_at = timezone.now()
                attendance.full_clean()
                attendance.save()

    return leave_request


@transaction.atomic
def create_substitution(
    *,
    school,
    session,
    date,
    period,
    school_class,
    section,
    subject,
    original_teacher,
    substitute_teacher,
    is_active=True,
):
    substitution = Substitution(
        school=school,
        session=session,
        date=date,
        period=period,
        school_class=school_class,
        section=section,
        subject=subject,
        original_teacher=original_teacher,
        substitute_teacher=substitute_teacher,
        is_active=is_active,
    )
    substitution.full_clean()
    substitution.save()
    return substitution


@transaction.atomic
def set_salary_structure(
    *,
    school,
    staff,
    basic_salary,
    allowances,
    deductions,
    effective_from,
    changed_by=None,
    reason='',
):
    if staff.school_id != school.id:
        raise ValidationError('Staff does not belong to selected school.')

    old_active = SalaryStructure.objects.filter(
        school=school,
        staff=staff,
        is_active=True,
    ).first()

    old_salary = old_active.basic_salary if old_active else Decimal('0.00')
    if old_active:
        old_active.is_active = False
        old_active.save(update_fields=['is_active'])

    new_structure = SalaryStructure(
        school=school,
        staff=staff,
        basic_salary=basic_salary,
        allowances=allowances or {},
        deductions=deductions or {},
        effective_from=effective_from,
        is_active=True,
    )
    new_structure.full_clean()
    new_structure.save()

    history = SalaryHistory.objects.create(
        school=school,
        staff=staff,
        old_salary=old_salary,
        new_salary=new_structure.basic_salary,
        changed_by=changed_by,
        reason=reason,
    )

    return new_structure, history
