from __future__ import annotations

from django.db.models import Avg, Count, Q

from apps.core.attendance.models import StudentAttendance, StudentAttendanceSummary
from apps.core.hr.models import StaffAttendance

from .filters import scoped_staff


def _report(title, columns, rows, summary):
    return {
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
    }


def daily_attendance_report(filters):
    rows_qs = StudentAttendance.objects.filter(
        school=filters.school,
        date__range=(filters.date_from, filters.date_to),
    ).select_related('student', 'school_class', 'section')
    if filters.session:
        rows_qs = rows_qs.filter(session=filters.session)
    if filters.school_class:
        rows_qs = rows_qs.filter(school_class=filters.school_class)
    if filters.section:
        rows_qs = rows_qs.filter(section=filters.section)
    if filters.student:
        rows_qs = rows_qs.filter(student=filters.student)

    rows = [[
        row.date,
        row.student.admission_number,
        row.student.full_name,
        row.school_class.name,
        row.section.name,
        row.get_status_display(),
    ] for row in rows_qs.order_by('-date', 'student__admission_number')]
    return _report(
        'Daily Attendance Report',
        ['Date', 'Admission No', 'Student', 'Class', 'Section', 'Status'],
        rows,
        [('Rows', len(rows))],
    )


def monthly_class_attendance_report(filters):
    summaries = StudentAttendanceSummary.objects.filter(
        school=filters.school,
        year=filters.year,
    ).select_related('student', 'student__current_class', 'student__current_section')
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.month:
        summaries = summaries.filter(month=filters.month)
    if filters.school_class:
        summaries = summaries.filter(student__current_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(student__current_section=filters.section)

    rows_qs = summaries.values(
        'student__current_class__name',
        'student__current_section__name',
    ).annotate(
        average_attendance=Avg('attendance_percentage'),
        student_count=Count('student_id'),
    ).order_by('student__current_class__name', 'student__current_section__name')

    rows = [[
        row['student__current_class__name'] or '-',
        row['student__current_section__name'] or '-',
        round(row['average_attendance'] or 0, 2),
        row['student_count'],
    ] for row in rows_qs]
    return _report(
        'Monthly Class Attendance Report',
        ['Class', 'Section', 'Average Attendance %', 'Students'],
        rows,
        [('Class Sections', len(rows))],
    )


def student_attendance_percentage_report(filters):
    summaries = StudentAttendanceSummary.objects.filter(
        school=filters.school,
        year=filters.year,
    ).select_related('student', 'student__current_class', 'student__current_section')
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.month:
        summaries = summaries.filter(month=filters.month)
    if filters.school_class:
        summaries = summaries.filter(student__current_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(student__current_section=filters.section)
    if filters.student:
        summaries = summaries.filter(student=filters.student)

    rows = [[
        row.student.admission_number,
        row.student.full_name,
        row.student.current_class.name if row.student.current_class_id else '-',
        row.student.current_section.name if row.student.current_section_id else '-',
        row.month,
        row.year,
        row.total_working_days,
        row.present_days,
        row.attendance_percentage,
    ] for row in summaries.order_by('student__admission_number', '-year', '-month')]
    return _report(
        'Student Attendance Percentage Report',
        ['Admission No', 'Student', 'Class', 'Section', 'Month', 'Year', 'Working Days', 'Present Days', 'Attendance %'],
        rows,
        [('Rows', len(rows))],
    )


def below_threshold_alert_report(filters, threshold=75):
    summaries = StudentAttendanceSummary.objects.filter(
        school=filters.school,
        year=filters.year,
        attendance_percentage__lt=threshold,
    ).select_related('student', 'student__current_class', 'student__current_section')
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.month:
        summaries = summaries.filter(month=filters.month)
    if filters.school_class:
        summaries = summaries.filter(student__current_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(student__current_section=filters.section)

    rows = [[
        row.student.admission_number,
        row.student.full_name,
        row.student.current_class.name if row.student.current_class_id else '-',
        row.student.current_section.name if row.student.current_section_id else '-',
        row.attendance_percentage,
    ] for row in summaries.order_by('attendance_percentage', 'student__admission_number')]
    return _report(
        'Below 75% Alert List',
        ['Admission No', 'Student', 'Class', 'Section', 'Attendance %'],
        rows,
        [('Alerts', len(rows)), ('Threshold', threshold)],
    )


def staff_attendance_report(filters):
    staff_ids = scoped_staff(filters).values_list('id', flat=True)
    rows_qs = StaffAttendance.objects.filter(
        school=filters.school,
        date__range=(filters.date_from, filters.date_to),
        staff_id__in=staff_ids,
    ).select_related('staff', 'staff__user', 'session')
    if filters.session:
        rows_qs = rows_qs.filter(session=filters.session)

    grouped = rows_qs.values(
        'staff__employee_id',
        'staff__user__first_name',
        'staff__user__last_name',
    ).annotate(
        present_count=Count('id', filter=Q(status=StaffAttendance.STATUS_PRESENT)),
        half_day_count=Count('id', filter=Q(status=StaffAttendance.STATUS_HALF_DAY)),
        leave_count=Count('id', filter=Q(status=StaffAttendance.STATUS_LEAVE)),
    ).order_by('staff__employee_id')

    rows = [[
        row['staff__employee_id'],
        f"{row['staff__user__first_name']} {row['staff__user__last_name']}".strip() or row['staff__employee_id'],
        row['present_count'],
        row['half_day_count'],
        row['leave_count'],
    ] for row in grouped]
    return _report(
        'Staff Attendance Report',
        ['Employee ID', 'Staff', 'Present', 'Half Day', 'Leave'],
        rows,
        [('Staff Rows', len(rows))],
    )
