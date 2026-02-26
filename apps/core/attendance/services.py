from __future__ import annotations

import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO, StringIO

from PIL import Image, ImageDraw
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.academics.models import AcademicConfig, SchoolClass, Section
from apps.core.hr.models import ClassTeacher, Staff, StaffAttendance
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.timetable.models import TimetableEntry
from apps.core.timetable.services import resolve_effective_teacher, teacher_can_handle_slot

from .models import StudentAttendance, StudentAttendanceSummary, StudentPeriodAttendance


def _staff_edit_hours() -> int:
    return int(getattr(settings, 'STAFF_ATTENDANCE_EDIT_WINDOW_HOURS', 6))


def _student_edit_days() -> int:
    return int(getattr(settings, 'STUDENT_ATTENDANCE_EDIT_WINDOW_DAYS', 2))


def _weekday_key_safe(target_date):
    return [
        'monday',
        'tuesday',
        'wednesday',
        'thursday',
        'friday',
        'saturday',
        'sunday',
    ][target_date.weekday()]


def _resolve_session(school, session=None):
    resolved = session or school.current_session
    if not resolved:
        raise ValidationError('No active academic session found for selected school.')
    if resolved.school_id != school.id:
        raise ValidationError('Selected session does not belong to selected school.')
    return resolved


def _ensure_session_editable(session, allow_override=False):
    if session.attendance_locked and not allow_override:
        raise ValidationError('Attendance is locked for this session.')


def _staff_profile_for_user(user, school):
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return Staff.objects.filter(user=user, school=school, is_active=True).select_related('user').first()


def _can_mark_daily_attendance(user, school, session, school_class, section):
    if user.role == 'schooladmin':
        return True

    staff = _staff_profile_for_user(user, school)
    if not staff or user.role != 'teacher':
        return False

    return ClassTeacher.objects.filter(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        teacher=staff,
        is_active=True,
    ).exists()


@transaction.atomic
def mark_staff_attendance_record(
    *,
    school,
    staff,
    target_date,
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

    resolved_session = _resolve_session(school, session)
    _ensure_session_editable(resolved_session, allow_override=allow_override)

    today = timezone.localdate()
    if target_date > today:
        raise ValidationError('Cannot mark staff attendance for future date.')
    if target_date < resolved_session.start_date or target_date > resolved_session.end_date:
        raise ValidationError('Attendance date must be within session range.')

    attendance, created = StaffAttendance.objects.get_or_create(
        school=school,
        session=resolved_session,
        staff=staff,
        date=target_date,
        defaults={
            'status': status,
            'check_in_time': check_in_time,
            'check_out_time': check_out_time,
            'ip_address': ip_address,
            'device_info': device_info,
            'marked_by': marked_by,
        },
    )

    if created:
        attendance.full_clean()
        attendance.save()
        return attendance, created

    if attendance.is_locked and not allow_override:
        raise ValidationError('Staff attendance record is locked.')

    edit_deadline = attendance.created_at + timedelta(hours=_staff_edit_hours())
    if not allow_override and timezone.now() > edit_deadline:
        raise ValidationError('Staff attendance edit window has expired.')

    attendance.status = status
    attendance.check_in_time = check_in_time
    attendance.check_out_time = check_out_time
    attendance.ip_address = ip_address
    attendance.device_info = device_info
    attendance.marked_by = marked_by
    attendance.edited_at = timezone.now()
    attendance.full_clean()
    attendance.save()
    return attendance, created


def _student_queryset_for_class_section(*, school, session, school_class, section):
    return Student.objects.filter(
        session_records__school=school,
        session_records__session=session,
        session_records__school_class=school_class,
        session_records__section=section,
    ).distinct().order_by('admission_number')


def _ensure_student_editable(record, allow_override=False):
    if record.is_locked and not allow_override:
        raise ValidationError('Attendance record is locked.')

    editable_until = record.created_at.date() + timedelta(days=_student_edit_days())
    if not allow_override and timezone.localdate() > editable_until:
        raise ValidationError('Student attendance edit window has expired.')


def _resolve_daily_status_from_period(statuses):
    if not statuses:
        return StudentAttendance.STATUS_ABSENT

    statuses = list(statuses)

    if any(status == StudentPeriodAttendance.STATUS_PRESENT for status in statuses):
        return StudentAttendance.STATUS_PRESENT

    if any(status == StudentPeriodAttendance.STATUS_LATE for status in statuses):
        return StudentAttendance.STATUS_LATE

    if all(status == StudentPeriodAttendance.STATUS_LEAVE for status in statuses):
        return StudentAttendance.STATUS_LEAVE

    return StudentAttendance.STATUS_ABSENT


@transaction.atomic
def mark_student_daily_attendance_bulk(
    *,
    school,
    session,
    school_class,
    section,
    target_date,
    status_by_student_id,
    marked_by,
    allow_override=False,
):
    resolved_session = _resolve_session(school, session)
    _ensure_session_editable(resolved_session, allow_override=allow_override)

    if school_class.school_id != school.id or school_class.session_id != resolved_session.id:
        raise ValidationError('Selected class is invalid for school/session.')
    if section.school_class_id != school_class.id:
        raise ValidationError('Selected section does not belong to class.')

    today = timezone.localdate()
    if target_date > today:
        raise ValidationError('Cannot mark student attendance for future date.')
    if target_date < resolved_session.start_date or target_date > resolved_session.end_date:
        raise ValidationError('Attendance date must be within session range.')

    if not _can_mark_daily_attendance(marked_by, school, resolved_session, school_class, section):
        raise ValidationError('You are not allowed to mark daily attendance for this class-section.')

    allowed_student_ids = set(
        _student_queryset_for_class_section(
            school=school,
            session=resolved_session,
            school_class=school_class,
            section=section,
        ).values_list('id', flat=True)
    )

    if not allowed_student_ids:
        return []

    saved_records = []
    for student_id, status in status_by_student_id.items():
        try:
            parsed_id = int(student_id)
        except (TypeError, ValueError):
            continue

        if parsed_id not in allowed_student_ids:
            raise ValidationError('Student list contains invalid class-section student mapping.')

        record, created = StudentAttendance.objects.get_or_create(
            school=school,
            session=resolved_session,
            student_id=parsed_id,
            date=target_date,
            defaults={
                'school_class': school_class,
                'section': section,
                'status': status,
                'marked_by': marked_by,
            },
        )

        if created:
            record.full_clean()
            record.save()
            saved_records.append(record)
            continue

        _ensure_student_editable(record, allow_override=allow_override)
        record.school_class = school_class
        record.section = section
        record.status = status
        record.marked_by = marked_by
        record.full_clean()
        record.save()
        saved_records.append(record)

    return saved_records


@transaction.atomic
def mark_student_period_attendance_bulk(
    *,
    school,
    session,
    school_class,
    section,
    target_date,
    period,
    status_by_student_id,
    marked_by,
    allow_override=False,
):
    resolved_session = _resolve_session(school, session)
    _ensure_session_editable(resolved_session, allow_override=allow_override)

    if school_class.school_id != school.id or school_class.session_id != resolved_session.id:
        raise ValidationError('Selected class is invalid for school/session.')
    if section.school_class_id != school_class.id:
        raise ValidationError('Selected section does not belong to class.')

    if period.school_id != school.id or period.session_id != resolved_session.id:
        raise ValidationError('Selected period is invalid for school/session.')

    today = timezone.localdate()
    if target_date > today:
        raise ValidationError('Cannot mark student attendance for future date.')
    if target_date < resolved_session.start_date or target_date > resolved_session.end_date:
        raise ValidationError('Attendance date must be within session range.')

    day_key = _weekday_key_safe(target_date)
    entry = TimetableEntry.objects.filter(
        school=school,
        session=resolved_session,
        school_class=school_class,
        section=section,
        day_of_week=day_key,
        period=period,
        is_active=True,
    ).select_related('subject', 'teacher', 'teacher__user').first()
    if not entry:
        raise ValidationError('No active timetable entry found for selected class-section-day-period.')

    if marked_by.role != 'schooladmin':
        actor_staff = _staff_profile_for_user(marked_by, school)
        if not actor_staff:
            raise ValidationError('No active staff profile is linked to this user.')
        if not teacher_can_handle_slot(entry=entry, teacher=actor_staff, target_date=target_date):
            raise ValidationError('Teacher is not allowed to mark this period attendance slot.')

    effective_teacher, substitution = resolve_effective_teacher(entry, target_date)

    allowed_student_ids = set(
        _student_queryset_for_class_section(
            school=school,
            session=resolved_session,
            school_class=school_class,
            section=section,
        ).values_list('id', flat=True)
    )

    saved_records = []
    for student_id, status in status_by_student_id.items():
        try:
            parsed_id = int(student_id)
        except (TypeError, ValueError):
            continue

        if parsed_id not in allowed_student_ids:
            raise ValidationError('Student list contains invalid class-section student mapping.')

        record, created = StudentPeriodAttendance.objects.get_or_create(
            school=school,
            session=resolved_session,
            student_id=parsed_id,
            date=target_date,
            period=period,
            defaults={
                'school_class': school_class,
                'section': section,
                'subject': entry.subject,
                'teacher': effective_teacher,
                'status': status,
                'marked_by': marked_by,
            },
        )

        if created:
            record.full_clean()
            record.save()
            saved_records.append(record)
            continue

        _ensure_student_editable(record, allow_override=allow_override)
        record.school_class = school_class
        record.section = section
        record.subject = entry.subject
        record.teacher = effective_teacher
        record.status = status
        record.marked_by = marked_by
        record.full_clean()
        record.save()
        saved_records.append(record)

    refresh_daily_attendance_from_period(
        school=school,
        session=resolved_session,
        school_class=school_class,
        section=section,
        target_date=target_date,
        marked_by=marked_by,
        allow_override=allow_override,
    )

    return saved_records, substitution


@transaction.atomic
def refresh_daily_attendance_from_period(
    *,
    school,
    session,
    school_class,
    section,
    target_date,
    marked_by,
    allow_override=False,
):
    resolved_session = _resolve_session(school, session)
    students = _student_queryset_for_class_section(
        school=school,
        session=resolved_session,
        school_class=school_class,
        section=section,
    )

    updated = []
    for student in students:
        statuses = list(
            StudentPeriodAttendance.objects.filter(
                school=school,
                session=resolved_session,
                student=student,
                date=target_date,
            ).values_list('status', flat=True)
        )

        daily_status = _resolve_daily_status_from_period(statuses)

        record, created = StudentAttendance.objects.get_or_create(
            school=school,
            session=resolved_session,
            student=student,
            date=target_date,
            defaults={
                'school_class': school_class,
                'section': section,
                'status': daily_status,
                'marked_by': marked_by,
            },
        )

        if not created:
            _ensure_student_editable(record, allow_override=allow_override)
            record.school_class = school_class
            record.section = section
            record.status = daily_status
            record.marked_by = marked_by
            record.full_clean()
            record.save()

        updated.append(record)

    return updated


@transaction.atomic
def lock_attendance_records(
    *,
    school,
    session,
    target_date=None,
    school_class=None,
    section=None,
):
    resolved_session = _resolve_session(school, session)

    staff_qs = StaffAttendance.objects.filter(school=school, session=resolved_session)
    daily_qs = StudentAttendance.objects.filter(school=school, session=resolved_session)
    period_qs = StudentPeriodAttendance.objects.filter(school=school, session=resolved_session)

    if target_date:
        staff_qs = staff_qs.filter(date__lte=target_date)
        daily_qs = daily_qs.filter(date__lte=target_date)
        period_qs = period_qs.filter(date__lte=target_date)

    if school_class:
        daily_qs = daily_qs.filter(school_class=school_class)
        period_qs = period_qs.filter(school_class=school_class)
    if section:
        daily_qs = daily_qs.filter(section=section)
        period_qs = period_qs.filter(section=section)

    staff_count = staff_qs.update(is_locked=True)
    daily_count = daily_qs.update(is_locked=True)
    period_count = period_qs.update(is_locked=True)

    return {
        'staff_locked': staff_count,
        'student_daily_locked': daily_count,
        'student_period_locked': period_count,
    }


def _month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _working_day_keys_for_session(session):
    config = AcademicConfig.objects.filter(school=session.school, session=session).first()
    if config and isinstance(config.working_days, list) and config.working_days:
        return set(config.working_days)
    return {'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'}


def _count_working_days(session, year, month):
    start, end = _month_bounds(year, month)
    if end < session.start_date or start > session.end_date:
        return 0

    start = max(start, session.start_date)
    end = min(end, session.end_date)
    working_keys = _working_day_keys_for_session(session)

    current = start
    total = 0
    while current <= end:
        if _weekday_key_safe(current) in working_keys:
            total += 1
        current += timedelta(days=1)
    return total


@transaction.atomic
def calculate_student_monthly_summary(*, student, session, year, month):
    if student.school_id != session.school_id:
        raise ValidationError('Student/session school mismatch.')

    month_start, month_end = _month_bounds(year, month)
    attendance_qs = StudentAttendance.objects.filter(
        school=student.school,
        session=session,
        student=student,
        date__range=(month_start, month_end),
    )

    present_days = attendance_qs.filter(
        status__in=[StudentAttendance.STATUS_PRESENT, StudentAttendance.STATUS_LATE]
    ).count()

    total_working_days = _count_working_days(session, year, month)
    percentage = Decimal('0.00')
    if total_working_days > 0:
        percentage = (
            Decimal(present_days) / Decimal(total_working_days) * Decimal('100')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    summary, _ = StudentAttendanceSummary.objects.update_or_create(
        school=student.school,
        session=session,
        student=student,
        year=year,
        month=month,
        defaults={
            'total_working_days': total_working_days,
            'present_days': present_days,
            'attendance_percentage': percentage,
        },
    )
    return summary


def recalculate_class_monthly_summaries(*, school, session, school_class, section, year, month):
    students = _student_queryset_for_class_section(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
    )
    summaries = []
    for student in students:
        summaries.append(
            calculate_student_monthly_summary(
                student=student,
                session=session,
                year=year,
                month=month,
            )
        )
    return summaries


def class_attendance_report(*, school, session, school_class, section, date_from, date_to):
    students = _student_queryset_for_class_section(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
    )

    records = StudentAttendance.objects.filter(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        date__range=(date_from, date_to),
    )

    aggregates = {
        row['student_id']: row
        for row in records.values('student_id').annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status=StudentAttendance.STATUS_PRESENT)),
            late=Count('id', filter=Q(status=StudentAttendance.STATUS_LATE)),
            absent=Count('id', filter=Q(status=StudentAttendance.STATUS_ABSENT)),
            leave=Count('id', filter=Q(status=StudentAttendance.STATUS_LEAVE)),
        )
    }

    result = []
    for student in students:
        row = aggregates.get(student.id, {'total': 0, 'present': 0, 'late': 0, 'absent': 0, 'leave': 0})
        present_effective = row['present'] + row['late']
        percentage = Decimal('0.00')
        if row['total'] > 0:
            percentage = (
                Decimal(present_effective) / Decimal(row['total']) * Decimal('100')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        result.append(
            {
                'student': student,
                'total_days': row['total'],
                'present_days': row['present'],
                'late_days': row['late'],
                'absent_days': row['absent'],
                'leave_days': row['leave'],
                'attendance_percentage': percentage,
            }
        )
    return result


def student_monthly_report(*, student, session, year, month):
    summary = calculate_student_monthly_summary(student=student, session=session, year=year, month=month)
    start, end = _month_bounds(year, month)
    records = StudentAttendance.objects.filter(
        school=student.school,
        session=session,
        student=student,
        date__range=(start, end),
    ).order_by('date')
    return summary, records


def teacher_staff_attendance_report(*, school, session, date_from, date_to, staff=None):
    qs = StaffAttendance.objects.filter(
        school=school,
        session=session,
        date__range=(date_from, date_to),
    ).select_related('staff', 'staff__user')

    if staff:
        qs = qs.filter(staff=staff)

    aggregates = qs.values('staff_id').annotate(
        total=Count('id'),
        present=Count('id', filter=Q(status=StaffAttendance.STATUS_PRESENT)),
        half_day=Count('id', filter=Q(status=StaffAttendance.STATUS_HALF_DAY)),
        leave=Count('id', filter=Q(status=StaffAttendance.STATUS_LEAVE)),
    )

    staff_map = {member.id: member for member in Staff.objects.filter(id__in=[row['staff_id'] for row in aggregates])}

    result = []
    for row in aggregates:
        staff_member = staff_map.get(row['staff_id'])
        if not staff_member:
            continue
        result.append(
            {
                'staff': staff_member,
                'total_days': row['total'],
                'present_days': row['present'],
                'half_days': row['half_day'],
                'leave_days': row['leave'],
            }
        )
    return result


def daily_absentee_list(*, school, session, target_date, school_class=None, section=None):
    qs = StudentAttendance.objects.filter(
        school=school,
        session=session,
        date=target_date,
        status=StudentAttendance.STATUS_ABSENT,
    ).select_related('student', 'school_class', 'section')

    if school_class:
        qs = qs.filter(school_class=school_class)
    if section:
        qs = qs.filter(section=section)

    return qs.order_by('school_class__display_order', 'section__name', 'student__admission_number')


def students_below_threshold(*, school, session, threshold, year, month):
    summaries = StudentAttendanceSummary.objects.filter(
        school=school,
        session=session,
        year=year,
        month=month,
        attendance_percentage__lt=Decimal(str(threshold)),
    ).select_related('student', 'student__current_class', 'student__current_section').order_by('attendance_percentage')

    return summaries


def rows_to_csv_bytes(headers, rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode('utf-8')


def table_pdf_bytes(title, headers, rows):
    width = 1800
    row_height = 44
    header_height = 60
    title_height = 50

    visible_rows = max(1, len(rows))
    height = title_height + header_height + visible_rows * row_height + 30

    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    draw.text((20, 15), title, fill='black')

    cols = len(headers)
    col_width = (width - 40) // max(1, cols)

    y = title_height
    for idx, header in enumerate(headers):
        x1 = 20 + idx * col_width
        x2 = x1 + col_width
        draw.rectangle((x1, y, x2, y + header_height), outline='black')
        draw.text((x1 + 6, y + 18), str(header), fill='black')

    y += header_height
    for row in rows:
        for idx, value in enumerate(row):
            x1 = 20 + idx * col_width
            x2 = x1 + col_width
            draw.rectangle((x1, y, x2, y + row_height), outline='black')
            text = str(value)
            if len(text) > 35:
                text = text[:32] + '...'
            draw.text((x1 + 6, y + 14), text, fill='black')
        y += row_height

    output = BytesIO()
    image.convert('RGB').save(output, format='PDF')
    return output.getvalue()
