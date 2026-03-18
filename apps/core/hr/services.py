from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from PIL import Image, ImageDraw
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_date
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import AcademicConfig
from apps.core.fees.models import LedgerEntry
from apps.core.students.models import image_to_pdf_bytes

from .models import (
    ClassTeacher,
    LeaveRequest,
    Payroll,
    PayrollAdvanceAdjustment,
    SalaryHistory,
    SalaryAdvance,
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


def _decimal(value) -> Decimal:
    return Decimal(str(value or '0'))


def _quantize(value) -> Decimal:
    return _decimal(value).quantize(Decimal('0.01'))


def _coerce_date(value, *, label='date') -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = parse_date(value)
        if parsed:
            return parsed
    raise ValidationError(f'Invalid {label} value.')


def _attendance_deduction_enabled() -> bool:
    return bool(getattr(settings, 'PAYROLL_ENABLE_ATTENDANCE_DEDUCTION', True))


def _advance_limit_percent() -> Decimal:
    value = getattr(settings, 'SALARY_ADVANCE_MAX_PERCENT', 50)
    try:
        pct = _decimal(value)
    except Exception:
        pct = Decimal('50')
    if pct <= 0:
        return Decimal('0')
    if pct > 100:
        return Decimal('100')
    return pct


def _advance_monthly_deduction_percent() -> Decimal:
    value = getattr(settings, 'PAYROLL_ADVANCE_MONTHLY_DEDUCTION_PERCENT', 50)
    try:
        pct = _decimal(value)
    except Exception:
        pct = Decimal('50')
    if pct <= 0:
        return Decimal('0')
    if pct > 100:
        return Decimal('100')
    return pct


def _working_weekdays(school, session):
    config = AcademicConfig.objects.filter(school=school, session=session).first()
    if config and isinstance(config.working_days, list) and config.working_days:
        day_map = {
            'monday': 0,
            'tuesday': 1,
            'wednesday': 2,
            'thursday': 3,
            'friday': 4,
            'saturday': 5,
            'sunday': 6,
        }
        weekdays = {day_map[day] for day in config.working_days if day in day_map}
        if weekdays:
            return weekdays
    # Fallback: Mon-Sat working.
    return {0, 1, 2, 3, 4, 5}


def _ensure_session_editable(session, allow_override=False):
    if session and session.is_locked and not allow_override:
        raise ValidationError('This academic session is locked.')


def _month_range_within_session(*, session, month, year):
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    session_start = _coerce_date(session.start_date, label='session start date')
    session_end = _coerce_date(session.end_date, label='session end date')
    start = max(first_day, session_start)
    end = min(last_day, session_end)
    return start, end


def _salary_structure_for_period(*, school, staff, month, year):
    period_end = date(year, month, monthrange(year, month)[1])
    return SalaryStructure.objects.filter(
        school=school,
        staff=staff,
        is_active=True,
        effective_from__lte=period_end,
    ).order_by('-effective_from', '-id').first()


def _sum_json_decimal(values):
    if not isinstance(values, dict):
        return Decimal('0.00')
    return sum((_decimal(value) for value in values.values()), Decimal('0.00'))


def _salary_snapshot(structure):
    gross = (
        _decimal(structure.basic_salary)
        + _decimal(structure.hra)
        + _decimal(structure.da)
        + _decimal(structure.transport_allowance)
        + _sum_json_decimal(structure.other_allowances)
    )
    fixed_deductions = (
        _decimal(structure.pf_deduction)
        + _decimal(structure.esi_deduction)
        + _decimal(structure.professional_tax)
        + _sum_json_decimal(structure.other_deductions)
    )
    return {
        'basic_salary': _quantize(structure.basic_salary),
        'hra': _quantize(structure.hra),
        'da': _quantize(structure.da),
        'transport_allowance': _quantize(structure.transport_allowance),
        'other_allowances': {k: _quantize(v) for k, v in (structure.other_allowances or {}).items()},
        'pf_deduction': _quantize(structure.pf_deduction),
        'esi_deduction': _quantize(structure.esi_deduction),
        'professional_tax': _quantize(structure.professional_tax),
        'other_deductions': {k: _quantize(v) for k, v in (structure.other_deductions or {}).items()},
        'gross_salary': _quantize(gross),
        'fixed_deductions_total': _quantize(fixed_deductions),
    }


@transaction.atomic
def assign_teacher_subject(*, school, session, teacher, school_class, subject, is_active=True):
    _ensure_session_editable(session)
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
    _ensure_session_editable(session)
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
    date = _coerce_date(date, label='attendance date')

    if staff.school_id != school.id:
        raise ValidationError('Staff does not belong to selected school.')

    session = session or school.current_session
    if not session:
        raise ValidationError('No active academic session found for the selected school.')
    if session.school_id != school.id:
        raise ValidationError('Selected session does not belong to selected school.')
    session_start = _coerce_date(session.start_date, label='session start date')
    session_end = _coerce_date(session.end_date, label='session end date')

    today = timezone.localdate()
    if date > today:
        raise ValidationError('Cannot mark staff attendance for a future date.')
    if date < session_start or date > session_end:
        raise ValidationError('Attendance date must be within session date range.')
    _ensure_session_editable(session, allow_override=allow_override)
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
    hra=Decimal('0.00'),
    da=Decimal('0.00'),
    transport_allowance=Decimal('0.00'),
    other_allowances=None,
    pf_deduction=Decimal('0.00'),
    esi_deduction=Decimal('0.00'),
    professional_tax=Decimal('0.00'),
    other_deductions=None,
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

    old_salary = old_active.net_salary if old_active else Decimal('0.00')
    if old_active:
        old_active.is_active = False
        old_active.save(update_fields=['is_active'])

    new_structure = SalaryStructure(
        school=school,
        staff=staff,
        basic_salary=basic_salary,
        hra=hra,
        da=da,
        transport_allowance=transport_allowance,
        other_allowances=other_allowances or {},
        pf_deduction=pf_deduction,
        esi_deduction=esi_deduction,
        professional_tax=professional_tax,
        other_deductions=other_deductions or {},
        effective_from=effective_from,
        is_active=True,
    )
    new_structure.full_clean()
    new_structure.save()

    history = SalaryHistory.objects.create(
        school=school,
        staff=staff,
        old_salary=old_salary,
        new_salary=new_structure.net_salary,
        changed_by=changed_by,
        reason=reason,
    )

    return new_structure, history


def calculate_staff_attendance_summary(*, school, session, staff, month, year):
    weekdays = _working_weekdays(school, session)
    start, end = _month_range_within_session(session=session, month=month, year=year)
    if start > end:
        return {
            'start_date': start,
            'end_date': end,
            'total_working_days': Decimal('0.00'),
            'present_days': Decimal('0.00'),
            'absent_days': Decimal('0.00'),
            'unpaid_leave_days': Decimal('0.00'),
            'paid_leave_days': Decimal('0.00'),
        }

    working_dates = [day for day in _date_range(start, end) if day.weekday() in weekdays]
    attendance_rows = StaffAttendance.objects.filter(
        school=school,
        session=session,
        staff=staff,
        date__range=(start, end),
    ).order_by('date')
    attendance_by_date = {row.date: row for row in attendance_rows}

    paid_leave_dates = set()
    approved_paid_leaves = LeaveRequest.objects.filter(
        school=school,
        staff=staff,
        status=LeaveRequest.STATUS_APPROVED,
        leave_type=LeaveRequest.TYPE_PAID,
        start_date__lte=end,
        end_date__gte=start,
    )
    for leave in approved_paid_leaves:
        leave_start = max(leave.start_date, start)
        leave_end = min(leave.end_date, end)
        for leave_day in _date_range(leave_start, leave_end):
            if leave_day.weekday() in weekdays:
                paid_leave_dates.add(leave_day)

    present_days = Decimal('0.00')
    absent_days = Decimal('0.00')
    unpaid_leave_days = Decimal('0.00')
    paid_leave_days = Decimal('0.00')

    for day in working_dates:
        record = attendance_by_date.get(day)
        if record:
            if record.status == StaffAttendance.STATUS_PRESENT:
                present_days += Decimal('1.00')
                continue
            if record.status == StaffAttendance.STATUS_HALF_DAY:
                present_days += Decimal('0.50')
                absent_days += Decimal('0.50')
                continue
            if day in paid_leave_dates:
                present_days += Decimal('1.00')
                paid_leave_days += Decimal('1.00')
                continue
            unpaid_leave_days += Decimal('1.00')
            continue

        if day in paid_leave_dates:
            present_days += Decimal('1.00')
            paid_leave_days += Decimal('1.00')
        else:
            absent_days += Decimal('1.00')

    return {
        'start_date': start,
        'end_date': end,
        'total_working_days': _quantize(Decimal(len(working_dates))),
        'present_days': _quantize(present_days),
        'absent_days': _quantize(absent_days),
        'unpaid_leave_days': _quantize(unpaid_leave_days),
        'paid_leave_days': _quantize(paid_leave_days),
    }


@transaction.atomic
def create_salary_advance(
    *,
    school,
    session,
    staff,
    amount,
    request_date=None,
    approved_by=None,
    status=SalaryAdvance.STATUS_PENDING,
):
    if staff.school_id != school.id:
        raise ValidationError('Staff does not belong to selected school.')
    if session.school_id != school.id:
        raise ValidationError('Session does not belong to selected school.')
    _ensure_session_editable(session)
    if staff.status != Staff.STATUS_ACTIVE or not staff.is_active:
        raise ValidationError('Only active staff can request salary advance.')

    amount = _quantize(amount)
    if amount <= 0:
        raise ValidationError('Advance amount must be greater than zero.')

    structure = SalaryStructure.objects.filter(
        school=school,
        staff=staff,
        is_active=True,
    ).order_by('-effective_from', '-id').first()
    if not structure:
        raise ValidationError('Active salary structure is required before creating salary advance.')

    max_allowed = _quantize((_decimal(structure.basic_salary) * _advance_limit_percent()) / Decimal('100'))
    if amount > max_allowed:
        raise ValidationError(f'Advance exceeds configured limit ({max_allowed}).')

    remaining_balance = amount if status in {SalaryAdvance.STATUS_PENDING, SalaryAdvance.STATUS_APPROVED} else Decimal('0.00')
    advance = SalaryAdvance(
        school=school,
        session=session,
        staff=staff,
        amount=amount,
        request_date=request_date or timezone.localdate(),
        approved_by=approved_by if status in {SalaryAdvance.STATUS_APPROVED, SalaryAdvance.STATUS_REJECTED, SalaryAdvance.STATUS_ADJUSTED} else None,
        remaining_balance=remaining_balance,
        status=status,
    )
    advance.full_clean()
    advance.save()
    return advance


@transaction.atomic
def update_salary_advance_status(*, salary_advance, status, approved_by):
    _ensure_session_editable(salary_advance.session)
    if status not in {
        SalaryAdvance.STATUS_APPROVED,
        SalaryAdvance.STATUS_REJECTED,
        SalaryAdvance.STATUS_ADJUSTED,
    }:
        raise ValidationError('Invalid salary advance status update.')

    salary_advance.status = status
    salary_advance.approved_by = approved_by

    if status == SalaryAdvance.STATUS_REJECTED:
        salary_advance.remaining_balance = Decimal('0.00')
    elif status == SalaryAdvance.STATUS_ADJUSTED:
        salary_advance.remaining_balance = Decimal('0.00')
    elif status == SalaryAdvance.STATUS_APPROVED and salary_advance.remaining_balance <= 0:
        salary_advance.remaining_balance = salary_advance.amount

    salary_advance.full_clean()
    salary_advance.save(update_fields=['status', 'approved_by', 'remaining_balance', 'updated_at'])
    return salary_advance


@transaction.atomic
def process_monthly_payroll(*, school, session, staff, month, year, processed_by):
    if staff.school_id != school.id:
        raise ValidationError('Staff does not belong to selected school.')
    if session.school_id != school.id:
        raise ValidationError('Session does not belong to selected school.')
    _ensure_session_editable(session)
    if month < 1 or month > 12:
        raise ValidationError('Month must be between 1 and 12.')
    if Payroll.objects.filter(staff=staff, month=month, year=year).exists():
        raise ValidationError('Payroll already processed for this staff-month-year.')

    structure = _salary_structure_for_period(school=school, staff=staff, month=month, year=year)
    if not structure:
        raise ValidationError('No applicable salary structure found for payroll month.')

    salary_snapshot = _salary_snapshot(structure)
    attendance = calculate_staff_attendance_summary(
        school=school,
        session=session,
        staff=staff,
        month=month,
        year=year,
    )

    gross_salary = salary_snapshot['gross_salary']
    fixed_deductions = salary_snapshot['fixed_deductions_total']
    attendance_deduction = Decimal('0.00')
    leave_deduction = Decimal('0.00')

    if _attendance_deduction_enabled() and attendance['total_working_days'] > 0:
        per_day_salary = _quantize(_decimal(structure.basic_salary) / attendance['total_working_days'])
        attendance_deduction = _quantize(per_day_salary * attendance['absent_days'])
        leave_deduction = _quantize(per_day_salary * attendance['unpaid_leave_days'])

    pre_advance_deduction_total = _quantize(fixed_deductions + attendance_deduction + leave_deduction)
    max_advance_pool = _quantize((gross_salary * _advance_monthly_deduction_percent()) / Decimal('100'))
    net_before_advances = _quantize(gross_salary - pre_advance_deduction_total)
    if net_before_advances < 0:
        net_before_advances = Decimal('0.00')
    if max_advance_pool > net_before_advances:
        max_advance_pool = net_before_advances

    advances = SalaryAdvance.objects.select_for_update().filter(
        school=school,
        session=session,
        staff=staff,
        status=SalaryAdvance.STATUS_APPROVED,
        remaining_balance__gt=0,
    ).order_by('request_date', 'id')

    advance_deduction = Decimal('0.00')
    advance_adjustments = []
    remaining_pool = max_advance_pool
    for advance in advances:
        if remaining_pool <= 0:
            break
        adjustment_amount = min(_decimal(advance.remaining_balance), remaining_pool)
        adjustment_amount = _quantize(adjustment_amount)
        if adjustment_amount <= 0:
            continue

        advance.remaining_balance = _quantize(_decimal(advance.remaining_balance) - adjustment_amount)
        if advance.remaining_balance <= 0:
            advance.remaining_balance = Decimal('0.00')
            advance.status = SalaryAdvance.STATUS_ADJUSTED
        advance.save(update_fields=['remaining_balance', 'status', 'updated_at'])

        advance_deduction += adjustment_amount
        remaining_pool = _quantize(remaining_pool - adjustment_amount)
        advance_adjustments.append((advance, adjustment_amount))

    advance_deduction = _quantize(advance_deduction)
    total_deductions = _quantize(pre_advance_deduction_total + advance_deduction)
    if total_deductions > gross_salary:
        total_deductions = gross_salary
    net_salary = _quantize(gross_salary - total_deductions)

    payroll = Payroll.objects.create(
        school=school,
        session=session,
        staff=staff,
        month=month,
        year=year,
        gross_salary=gross_salary,
        attendance_deduction=attendance_deduction,
        leave_deduction=leave_deduction,
        advance_deduction=advance_deduction,
        total_deductions=total_deductions,
        net_salary=net_salary,
        total_working_days=attendance['total_working_days'],
        present_days=attendance['present_days'],
        absent_days=_quantize(attendance['absent_days'] + attendance['unpaid_leave_days']),
        processed_by=processed_by,
        attendance_snapshot={
            'start_date': str(attendance['start_date']),
            'end_date': str(attendance['end_date']),
            'total_working_days': str(attendance['total_working_days']),
            'present_days': str(attendance['present_days']),
            'absent_days': str(attendance['absent_days']),
            'unpaid_leave_days': str(attendance['unpaid_leave_days']),
            'paid_leave_days': str(attendance['paid_leave_days']),
        },
        salary_snapshot={
            'basic_salary': str(salary_snapshot['basic_salary']),
            'hra': str(salary_snapshot['hra']),
            'da': str(salary_snapshot['da']),
            'transport_allowance': str(salary_snapshot['transport_allowance']),
            'other_allowances': {k: str(v) for k, v in salary_snapshot['other_allowances'].items()},
            'pf_deduction': str(salary_snapshot['pf_deduction']),
            'esi_deduction': str(salary_snapshot['esi_deduction']),
            'professional_tax': str(salary_snapshot['professional_tax']),
            'other_deductions': {k: str(v) for k, v in salary_snapshot['other_deductions'].items()},
            'gross_salary': str(gross_salary),
            'fixed_deductions_total': str(fixed_deductions),
        },
    )

    for advance, amount in advance_adjustments:
        PayrollAdvanceAdjustment.objects.create(
            payroll=payroll,
            salary_advance=advance,
            amount=amount,
        )

    LedgerEntry.objects.get_or_create(
        school=school,
        transaction_type=LedgerEntry.TYPE_EXPENSE,
        reference_model='Payroll',
        reference_id=str(payroll.id),
        defaults={
            'session': session,
            'amount': net_salary,
            'date': timezone.localdate(),
            'description': f'Payroll expense for {staff.employee_id} - {month:02d}/{year}',
            'created_by': processed_by,
        },
    )

    return payroll


@transaction.atomic
def process_monthly_payroll_for_all(*, school, session, month, year, processed_by):
    processed = []
    errors = []

    staff_rows = Staff.objects.filter(
        school=school,
        is_active=True,
        status=Staff.STATUS_ACTIVE,
    ).order_by('employee_id')

    for staff in staff_rows:
        try:
            payroll = process_monthly_payroll(
                school=school,
                session=session,
                staff=staff,
                month=month,
                year=year,
                processed_by=processed_by,
            )
            processed.append(payroll)
        except ValidationError as exc:
            errors.append(f'{staff.employee_id}: {"; ".join(exc.messages)}')

    return processed, errors


@transaction.atomic
def set_payroll_hold(*, payroll, on_hold, reason=''):
    _ensure_session_editable(payroll.session)
    if on_hold:
        reason = (reason or '').strip()
        if not reason:
            raise ValidationError('Hold reason is required.')
        if payroll.is_paid:
            raise ValidationError('Paid payroll cannot be put on hold.')
        payroll.is_on_hold = True
        payroll.hold_reason = reason[:255]
    else:
        payroll.is_on_hold = False
        payroll.hold_reason = ''

    payroll.full_clean()
    payroll.save(update_fields=['is_on_hold', 'hold_reason', 'updated_at'])
    return payroll


@transaction.atomic
def mark_payroll_paid(*, payroll, paid_by):
    _ensure_session_editable(payroll.session)
    if payroll.is_on_hold:
        raise ValidationError('Payroll is on hold and cannot be marked paid.')
    if payroll.is_paid:
        return payroll

    payroll.is_paid = True
    payroll.paid_on = timezone.now()
    payroll.paid_by = paid_by
    payroll.full_clean()
    payroll.save(update_fields=['is_paid', 'paid_on', 'paid_by', 'updated_at'])
    return payroll


@transaction.atomic
def lock_payroll(*, payroll):
    _ensure_session_editable(payroll.session)
    if payroll.is_locked:
        return payroll

    payroll.is_locked = True
    payroll.full_clean()
    payroll.save(update_fields=['is_locked', 'updated_at'])

    start, end = _month_range_within_session(session=payroll.session, month=payroll.month, year=payroll.year)
    StaffAttendance.objects.filter(
        school=payroll.school,
        session=payroll.session,
        staff=payroll.staff,
        date__range=(start, end),
    ).update(is_locked=True)
    return payroll


@transaction.atomic
def unlock_payroll(*, payroll, allow_override=False):
    if not allow_override:
        raise ValidationError('Only super admin override can unlock payroll.')

    payroll.is_locked = False
    payroll.full_clean()
    payroll.save(update_fields=['is_locked', 'updated_at'])

    start, end = _month_range_within_session(session=payroll.session, month=payroll.month, year=payroll.year)
    StaffAttendance.objects.filter(
        school=payroll.school,
        session=payroll.session,
        staff=payroll.staff,
        date__range=(start, end),
    ).update(is_locked=False)
    return payroll


def _money_str(value):
    return str(_quantize(value))


def build_payslip_image(*, payroll):
    width = 1240
    height = 1754
    page = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(page)

    school = payroll.school
    staff = payroll.staff

    draw.rectangle((30, 30, width - 30, height - 30), outline='black', width=3)
    draw.text((60, 60), f'{school.name} - Payslip', fill='black')
    draw.text((60, 105), f'Month/Year: {payroll.month:02d}/{payroll.year}', fill='black')
    draw.text((60, 145), f'Employee: {staff.employee_id} - {staff.full_name}', fill='black')
    draw.text((60, 185), f'Designation: {staff.designation.name}', fill='black')
    draw.text((60, 225), f'Status: {"PAID" if payroll.is_paid else "UNPAID"}', fill='black')

    y = 290
    draw.text((60, y), 'Earnings', fill='black')
    draw.text((700, y), 'Amount', fill='black')
    draw.text((860, y), 'Deductions', fill='black')
    draw.text((1080, y), 'Amount', fill='black')
    draw.line((60, y + 24, width - 60, y + 24), fill='black')
    y += 44

    salary_snapshot = payroll.salary_snapshot or {}
    earnings_rows = [
        ('Basic', salary_snapshot.get('basic_salary', '0.00')),
        ('HRA', salary_snapshot.get('hra', '0.00')),
        ('DA', salary_snapshot.get('da', '0.00')),
        ('Transport', salary_snapshot.get('transport_allowance', '0.00')),
    ]
    for key, value in (salary_snapshot.get('other_allowances') or {}).items():
        earnings_rows.append((f'Allowance: {key}', value))

    deduction_rows = [
        ('PF', salary_snapshot.get('pf_deduction', '0.00')),
        ('ESI', salary_snapshot.get('esi_deduction', '0.00')),
        ('Professional Tax', salary_snapshot.get('professional_tax', '0.00')),
    ]
    for key, value in (salary_snapshot.get('other_deductions') or {}).items():
        deduction_rows.append((f'Deduction: {key}', value))
    deduction_rows.extend([
        ('Attendance', _money_str(payroll.attendance_deduction)),
        ('Leave', _money_str(payroll.leave_deduction)),
        ('Advance', _money_str(payroll.advance_deduction)),
    ])

    max_rows = max(len(earnings_rows), len(deduction_rows))
    for index in range(max_rows):
        if index < len(earnings_rows):
            label, value = earnings_rows[index]
            draw.text((60, y), label, fill='black')
            draw.text((700, y), str(value), fill='black')
        if index < len(deduction_rows):
            label, value = deduction_rows[index]
            draw.text((860, y), label, fill='black')
            draw.text((1080, y), str(value), fill='black')
        y += 34

    y += 22
    draw.line((60, y, width - 60, y), fill='black')
    y += 30
    draw.text((60, y), f'Gross Salary: {_money_str(payroll.gross_salary)}', fill='black')
    y += 36
    draw.text((60, y), f'Total Deductions: {_money_str(payroll.total_deductions)}', fill='black')
    y += 36
    draw.text((60, y), f'Net Salary: {_money_str(payroll.net_salary)}', fill='black')
    y += 60

    attendance_snapshot = payroll.attendance_snapshot or {}
    draw.text((60, y), 'Attendance Summary', fill='black')
    y += 36
    draw.text((60, y), f"Working Days: {attendance_snapshot.get('total_working_days', payroll.total_working_days)}", fill='black')
    y += 32
    draw.text((60, y), f"Present Days: {attendance_snapshot.get('present_days', payroll.present_days)}", fill='black')
    y += 32
    draw.text((60, y), f"Absent Days: {attendance_snapshot.get('absent_days', payroll.absent_days)}", fill='black')
    y += 32
    draw.text((60, y), f"Unpaid Leave Days: {attendance_snapshot.get('unpaid_leave_days', '0.00')}", fill='black')
    y += 90

    draw.text((60, y), 'Authorized Signature: ____________________', fill='black')

    return page


def generate_payslip_pdf(*, payroll):
    page = build_payslip_image(payroll=payroll)
    return image_to_pdf_bytes([page])


def generate_bulk_payslip_pdf(*, payrolls: Iterable[Payroll]):
    pages = [build_payslip_image(payroll=payroll) for payroll in payrolls]
    return image_to_pdf_bytes(pages)
