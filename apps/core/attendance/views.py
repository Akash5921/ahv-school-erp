from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import AcademicConfig
from apps.core.hr.models import Staff, StaffAttendance
from apps.core.students.models import Student
from apps.core.timetable.models import TimetableEntry
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    AttendanceLockForm,
    ClassAttendanceReportForm,
    DailyAbsenteeReportForm,
    StaffAttendanceFilterForm,
    StaffAttendanceMarkForm,
    StaffAttendanceReportForm,
    StudentDailyAttendanceSelectionForm,
    StudentMonthlyReportForm,
    StudentPeriodAttendanceSelectionForm,
    ThresholdReportForm,
)
from .models import StudentAttendance, StudentPeriodAttendance
from .services import (
    calculate_student_monthly_summary,
    class_attendance_report,
    daily_absentee_list,
    lock_attendance_records,
    mark_staff_attendance_record,
    mark_student_daily_attendance_bulk,
    mark_student_period_attendance_bulk,
    rows_to_csv_bytes,
    student_monthly_report,
    students_below_threshold,
    table_pdf_bytes,
    teacher_staff_attendance_report,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _actor_staff(user):
    if not getattr(user, 'school_id', None):
        return None
    return Staff.objects.filter(
        school=user.school,
        user=user,
        is_active=True,
    ).select_related('user').first()


def _session_from_request(request, school):
    session_id = request.GET.get('session') or request.POST.get('session')
    sessions = _school_sessions(school)

    selected = None
    if session_id and str(session_id).isdigit():
        selected = sessions.filter(id=int(session_id)).first()
    elif school.current_session_id:
        selected = sessions.filter(id=school.current_session_id).first()
    return sessions, selected


def _students_for_class_section(*, school, session, school_class, section):
    return Student.objects.filter(
        session_records__school=school,
        session_records__session=session,
        session_records__school_class=school_class,
        session_records__section=section,
        is_archived=False,
    ).distinct().order_by('admission_number')


def _attendance_mode_for_session(*, school, session):
    config = AcademicConfig.objects.filter(school=school, session=session).first()
    if not config:
        return AcademicConfig.ATTENDANCE_DAILY
    return config.attendance_type


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


def _response_for_export(*, title, headers, rows, filename_base, export_type):
    if export_type == 'csv':
        content = rows_to_csv_bytes(headers, rows)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=\"{filename_base}.csv\"'
        return response

    if export_type == 'pdf':
        content = table_pdf_bytes(title=title, headers=headers, rows=rows)
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=\"{filename_base}.pdf\"'
        return response

    return None


def _status_from_post(request, student):
    return request.POST.get(f'status_{student.id}', StudentAttendance.STATUS_PRESENT)


def _is_status_allowed(status_value):
    return status_value in {
        StudentAttendance.STATUS_PRESENT,
        StudentAttendance.STATUS_ABSENT,
        StudentAttendance.STATUS_LEAVE,
        StudentAttendance.STATUS_LATE,
    }


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant'])
def attendance_staff_list(request):
    school = request.user.school
    actor_is_admin = request.user.role == 'schooladmin'
    actor_staff = _actor_staff(request.user)
    _, selected_session = _session_from_request(request, school)

    filter_form = StaffAttendanceFilterForm(
        request.GET or None,
        school=school,
        allow_staff_selection=actor_is_admin,
        initial={'session': selected_session},
    )

    attendances = StaffAttendance.objects.filter(
        school=school,
    ).select_related('session', 'staff', 'staff__user', 'marked_by')

    if filter_form.is_valid():
        selected_session = filter_form.cleaned_data.get('session') or selected_session
        selected_date = filter_form.cleaned_data.get('date')
        selected_staff = filter_form.cleaned_data.get('staff')
    else:
        selected_date = None
        selected_staff = None

    if selected_session:
        attendances = attendances.filter(session=selected_session)
    if selected_date:
        attendances = attendances.filter(date=selected_date)

    if actor_is_admin:
        if selected_staff:
            attendances = attendances.filter(staff=selected_staff)
    else:
        if not actor_staff:
            messages.error(request, 'Your staff profile is not configured.')
            attendances = attendances.none()
        else:
            attendances = attendances.filter(staff=actor_staff)

    return render(request, 'attendance_core/staff_list.html', {
        'filter_form': filter_form,
        'attendances': attendances.order_by('-date', 'staff__employee_id'),
        'actor_is_admin': actor_is_admin,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant'])
def attendance_staff_mark(request):
    school = request.user.school
    actor_is_admin = request.user.role == 'schooladmin'
    actor_staff = _actor_staff(request.user)
    _, selected_session = _session_from_request(request, school)

    if not actor_is_admin and not actor_staff:
        messages.error(request, 'Your staff profile is not configured.')
        return redirect('attendance_staff_list')

    if request.method == 'POST':
        form = StaffAttendanceMarkForm(
            request.POST,
            school=school,
            actor_staff=actor_staff,
            lock_staff=not actor_is_admin,
            default_session=selected_session,
        )
        if form.is_valid():
            try:
                attendance, created = mark_staff_attendance_record(
                    school=school,
                    staff=form.cleaned_data['staff'],
                    session=form.cleaned_data['session'],
                    target_date=form.cleaned_data['date'],
                    status=form.cleaned_data['status'],
                    marked_by=request.user,
                    check_in_time=form.cleaned_data['check_in_time'],
                    check_out_time=form.cleaned_data['check_out_time'],
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    device_info=request.META.get('HTTP_USER_AGENT', '')[:255],
                    allow_override=actor_is_admin,
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='attendance.staff_marked' if created else 'attendance.staff_updated',
                    school=school,
                    target=attendance,
                    details=(
                        f"Session={attendance.session_id}, Staff={attendance.staff_id}, "
                        f"Date={attendance.date}, Status={attendance.status}"
                    ),
                )
                messages.success(request, 'Staff attendance saved successfully.')
                return redirect('attendance_staff_list')
    else:
        initial = {
            'session': selected_session,
            'date': date.today(),
            'status': StaffAttendance.STATUS_PRESENT,
        }
        if actor_staff and not actor_is_admin:
            initial['staff'] = actor_staff

        form = StaffAttendanceMarkForm(
            school=school,
            actor_staff=actor_staff,
            lock_staff=not actor_is_admin,
            default_session=selected_session,
            initial=initial,
        )

    return render(request, 'attendance_core/staff_form.html', {
        'form': form,
        'actor_is_admin': actor_is_admin,
    })


@login_required
@role_required('schooladmin')
def attendance_staff_edit(request, pk):
    school = request.user.school
    attendance = get_object_or_404(
        StaffAttendance.objects.select_related('staff', 'staff__user', 'session'),
        pk=pk,
        school=school,
    )

    if request.method == 'POST':
        form = StaffAttendanceMarkForm(
            request.POST,
            instance=attendance,
            school=school,
            default_session=attendance.session,
        )
        form.fields['session'].disabled = True
        form.fields['staff'].disabled = True
        form.fields['date'].disabled = True

        if form.is_valid():
            try:
                updated, _ = mark_staff_attendance_record(
                    school=school,
                    staff=attendance.staff,
                    session=attendance.session,
                    target_date=attendance.date,
                    status=form.cleaned_data['status'],
                    marked_by=request.user,
                    check_in_time=form.cleaned_data['check_in_time'],
                    check_out_time=form.cleaned_data['check_out_time'],
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    device_info=request.META.get('HTTP_USER_AGENT', '')[:255],
                    allow_override=True,
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='attendance.staff_edited',
                    school=school,
                    target=updated,
                    details=f"Session={updated.session_id}, Staff={updated.staff_id}, Date={updated.date}",
                )
                messages.success(request, 'Staff attendance updated successfully.')
                return redirect('attendance_staff_list')
    else:
        form = StaffAttendanceMarkForm(
            instance=attendance,
            school=school,
            default_session=attendance.session,
        )
        form.fields['session'].disabled = True
        form.fields['staff'].disabled = True
        form.fields['date'].disabled = True

    return render(request, 'attendance_core/staff_form.html', {
        'form': form,
        'attendance': attendance,
        'actor_is_admin': True,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def attendance_student_daily_mark(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    students = Student.objects.none()
    existing_status_map = {}
    selected_session = None
    selected_class = None
    selected_section = None
    target_date = None
    can_submit = False
    student_rows = []

    if request.method == 'POST':
        selection_form = StudentDailyAttendanceSelectionForm(
            request.POST,
            school=school,
            default_session=default_session,
        )
        if selection_form.is_valid():
            selected_session = selection_form.cleaned_data['session']
            selected_class = selection_form.cleaned_data['school_class']
            selected_section = selection_form.cleaned_data['section']
            target_date = selection_form.cleaned_data['target_date']

            mode = _attendance_mode_for_session(school=school, session=selected_session)
            if mode == AcademicConfig.ATTENDANCE_PERIOD:
                messages.error(
                    request,
                    'Period-wise attendance is enabled. Use period attendance marking.',
                )
            else:
                students = _students_for_class_section(
                    school=school,
                    session=selected_session,
                    school_class=selected_class,
                    section=selected_section,
                )

                if not students.exists():
                    messages.error(request, 'No students found for selected class-section.')
                else:
                    status_by_student_id = {}
                    has_error = False
                    for student in students:
                        status_value = _status_from_post(request, student)
                        if not _is_status_allowed(status_value):
                            selection_form.add_error(None, f'Invalid status for {student.admission_number}.')
                            has_error = True
                            break
                        status_by_student_id[student.id] = status_value

                    if not has_error:
                        try:
                            saved_records = mark_student_daily_attendance_bulk(
                                school=school,
                                session=selected_session,
                                school_class=selected_class,
                                section=selected_section,
                                target_date=target_date,
                                status_by_student_id=status_by_student_id,
                                marked_by=request.user,
                                allow_override=request.user.role == 'schooladmin',
                            )
                        except ValidationError as exc:
                            selection_form.add_error(None, '; '.join(exc.messages))
                        else:
                            log_audit_event(
                                request=request,
                                action='attendance.student_daily_marked',
                                school=school,
                                target=selected_class,
                                details=(
                                    f"Session={selected_session.id}, Class={selected_class.id}, "
                                    f"Section={selected_section.id}, Date={target_date}, Rows={len(saved_records)}"
                                ),
                            )
                            messages.success(request, 'Student daily attendance saved successfully.')
                            query = (
                                f"session={selected_session.id}&school_class={selected_class.id}&"
                                f"section={selected_section.id}&target_date={target_date.isoformat()}"
                            )
                            return redirect(f"{reverse('attendance_student_daily_mark')}?{query}")
    else:
        selection_form = StudentDailyAttendanceSelectionForm(
            request.GET or None,
            school=school,
            default_session=default_session,
        )

    if selection_form.is_valid():
        selected_session = selection_form.cleaned_data['session']
        selected_class = selection_form.cleaned_data['school_class']
        selected_section = selection_form.cleaned_data['section']
        target_date = selection_form.cleaned_data['target_date']

        mode = _attendance_mode_for_session(school=school, session=selected_session)
        can_submit = mode == AcademicConfig.ATTENDANCE_DAILY
        students = _students_for_class_section(
            school=school,
            session=selected_session,
            school_class=selected_class,
            section=selected_section,
        )
        existing_status_map = {
            row.student_id: row.status
            for row in StudentAttendance.objects.filter(
                school=school,
                session=selected_session,
                school_class=selected_class,
                section=selected_section,
                date=target_date,
            )
        }
        student_rows = [
            {
                'student': student,
                'status': existing_status_map.get(student.id, StudentAttendance.STATUS_PRESENT),
            }
            for student in students
        ]

    return render(request, 'attendance_core/student_daily_mark.html', {
        'selection_form': selection_form,
        'students': students,
        'student_rows': student_rows,
        'selected_session': selected_session,
        'selected_class': selected_class,
        'selected_section': selected_section,
        'target_date': target_date,
        'status_choices': StudentAttendance.STATUS_CHOICES,
        'can_submit': can_submit,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def attendance_student_period_mark(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    students = Student.objects.none()
    existing_status_map = {}
    selected_session = None
    selected_class = None
    selected_section = None
    selected_period = None
    target_date = None
    can_submit = False
    timetable_entry = None
    active_substitution = None
    student_rows = []

    if request.method == 'POST':
        selection_form = StudentPeriodAttendanceSelectionForm(
            request.POST,
            school=school,
            default_session=default_session,
        )
        if selection_form.is_valid():
            selected_session = selection_form.cleaned_data['session']
            selected_class = selection_form.cleaned_data['school_class']
            selected_section = selection_form.cleaned_data['section']
            selected_period = selection_form.cleaned_data['period']
            target_date = selection_form.cleaned_data['target_date']

            mode = _attendance_mode_for_session(school=school, session=selected_session)
            if mode != AcademicConfig.ATTENDANCE_PERIOD:
                messages.error(request, 'Period-wise attendance is not enabled in academic config.')
            else:
                students = _students_for_class_section(
                    school=school,
                    session=selected_session,
                    school_class=selected_class,
                    section=selected_section,
                )

                status_by_student_id = {}
                has_error = False
                for student in students:
                    status_value = _status_from_post(request, student)
                    if not _is_status_allowed(status_value):
                        selection_form.add_error(None, f'Invalid status for {student.admission_number}.')
                        has_error = True
                        break
                    status_by_student_id[student.id] = status_value

                if not has_error and students.exists():
                    try:
                        saved_records, active_substitution = mark_student_period_attendance_bulk(
                            school=school,
                            session=selected_session,
                            school_class=selected_class,
                            section=selected_section,
                            target_date=target_date,
                            period=selected_period,
                            status_by_student_id=status_by_student_id,
                            marked_by=request.user,
                            allow_override=request.user.role == 'schooladmin',
                        )
                    except ValidationError as exc:
                        selection_form.add_error(None, '; '.join(exc.messages))
                    else:
                        log_audit_event(
                            request=request,
                            action='attendance.student_period_marked',
                            school=school,
                            target=selected_class,
                            details=(
                                f"Session={selected_session.id}, Class={selected_class.id}, "
                                f"Section={selected_section.id}, Date={target_date}, Period={selected_period.id}, "
                                f"Rows={len(saved_records)}"
                            ),
                        )
                        messages.success(request, 'Student period attendance saved successfully.')
                        query = (
                            f"session={selected_session.id}&school_class={selected_class.id}&"
                            f"section={selected_section.id}&period={selected_period.id}&"
                            f"target_date={target_date.isoformat()}"
                        )
                        return redirect(f"{reverse('attendance_student_period_mark')}?{query}")
    else:
        selection_form = StudentPeriodAttendanceSelectionForm(
            request.GET or None,
            school=school,
            default_session=default_session,
        )

    if selection_form.is_valid():
        selected_session = selection_form.cleaned_data['session']
        selected_class = selection_form.cleaned_data['school_class']
        selected_section = selection_form.cleaned_data['section']
        selected_period = selection_form.cleaned_data['period']
        target_date = selection_form.cleaned_data['target_date']

        mode = _attendance_mode_for_session(school=school, session=selected_session)
        can_submit = mode == AcademicConfig.ATTENDANCE_PERIOD

        students = _students_for_class_section(
            school=school,
            session=selected_session,
            school_class=selected_class,
            section=selected_section,
        )
        existing_status_map = {
            row.student_id: row.status
            for row in StudentPeriodAttendance.objects.filter(
                school=school,
                session=selected_session,
                school_class=selected_class,
                section=selected_section,
                period=selected_period,
                date=target_date,
            )
        }
        student_rows = [
            {
                'student': student,
                'status': existing_status_map.get(student.id, StudentAttendance.STATUS_PRESENT),
            }
            for student in students
        ]

        timetable_entry = TimetableEntry.objects.filter(
            school=school,
            session=selected_session,
            school_class=selected_class,
            section=selected_section,
            day_of_week=_weekday_key_safe(target_date),
            period=selected_period,
            is_active=True,
        ).select_related('subject', 'teacher', 'teacher__user').first()

    return render(request, 'attendance_core/student_period_mark.html', {
        'selection_form': selection_form,
        'students': students,
        'student_rows': student_rows,
        'selected_session': selected_session,
        'selected_class': selected_class,
        'selected_section': selected_section,
        'selected_period': selected_period,
        'target_date': target_date,
        'status_choices': StudentAttendance.STATUS_CHOICES,
        'can_submit': can_submit,
        'timetable_entry': timetable_entry,
        'active_substitution': active_substitution,
    })


@login_required
@role_required('schooladmin')
def attendance_lock_manage(request):
    school = request.user.school
    sessions, selected_session = _session_from_request(request, school)

    if request.method == 'POST':
        form = AttendanceLockForm(
            request.POST,
            school=school,
            default_session=selected_session,
        )
        action = request.POST.get('action')
        if form.is_valid():
            selected_session = form.cleaned_data['session']

            if action == 'lock_records':
                result = lock_attendance_records(
                    school=school,
                    session=selected_session,
                    target_date=form.cleaned_data.get('target_date'),
                    school_class=form.cleaned_data.get('school_class'),
                    section=form.cleaned_data.get('section'),
                )
                log_audit_event(
                    request=request,
                    action='attendance.records_locked',
                    school=school,
                    target=selected_session,
                    details=(
                        f"Session={selected_session.id}, Staff={result['staff_locked']}, "
                        f"Daily={result['student_daily_locked']}, Period={result['student_period_locked']}"
                    ),
                )
                messages.success(
                    request,
                    'Records locked. '
                    f"Staff={result['staff_locked']}, Daily={result['student_daily_locked']}, "
                    f"Period={result['student_period_locked']}.",
                )
            elif action == 'session_lock':
                selected_session.attendance_locked = True
                selected_session.save(update_fields=['attendance_locked'])
                log_audit_event(
                    request=request,
                    action='attendance.session_locked',
                    school=school,
                    target=selected_session,
                    details=f"Session={selected_session.id}",
                )
                messages.success(request, 'Session attendance lock enabled.')
            elif action == 'session_unlock':
                selected_session.attendance_locked = False
                selected_session.save(update_fields=['attendance_locked'])
                log_audit_event(
                    request=request,
                    action='attendance.session_unlocked',
                    school=school,
                    target=selected_session,
                    details=f"Session={selected_session.id}",
                )
                messages.success(request, 'Session attendance lock disabled.')
            else:
                messages.error(request, 'Invalid lock action requested.')

            query = f"session={selected_session.id}"
            return redirect(f"{reverse('attendance_lock_manage')}?{query}")
    else:
        form = AttendanceLockForm(
            school=school,
            default_session=selected_session,
            initial={'session': selected_session.id if selected_session else None},
        )

    session_states = sessions.values('id', 'name', 'attendance_locked')
    return render(request, 'attendance_core/lock_manage.html', {
        'form': form,
        'selected_session': selected_session,
        'session_states': session_states,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def attendance_report_class(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    form = ClassAttendanceReportForm(
        request.GET or None,
        school=school,
        default_session=default_session,
    )
    report_rows = []

    if form.is_valid():
        cleaned = form.cleaned_data
        report_rows = class_attendance_report(
            school=school,
            session=cleaned['session'],
            school_class=cleaned['school_class'],
            section=cleaned['section'],
            date_from=cleaned['date_from'],
            date_to=cleaned['date_to'],
        )

        export = request.GET.get('export')
        if export in {'csv', 'pdf'}:
            rows = [
                [
                    row['student'].admission_number,
                    row['student'].full_name,
                    row['total_days'],
                    row['present_days'],
                    row['late_days'],
                    row['absent_days'],
                    row['leave_days'],
                    row['attendance_percentage'],
                ]
                for row in report_rows
            ]
            headers = [
                'Admission No',
                'Student',
                'Total Days',
                'Present',
                'Late',
                'Absent',
                'Leave',
                'Attendance %',
            ]
            title = (
                f"Class Attendance Report - {cleaned['school_class'].name}-{cleaned['section'].name} "
                f"({cleaned['date_from']} to {cleaned['date_to']})"
            )
            response = _response_for_export(
                title=title,
                headers=headers,
                rows=rows,
                filename_base='class_attendance_report',
                export_type=export,
            )
            if response:
                return response

    return render(request, 'attendance_core/report_class.html', {
        'form': form,
        'report_rows': report_rows,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def attendance_report_student_monthly(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    form = StudentMonthlyReportForm(
        request.GET or None,
        school=school,
        default_session=default_session,
    )
    summary = None
    records = []

    if form.is_valid():
        cleaned = form.cleaned_data
        summary, records = student_monthly_report(
            student=cleaned['student'],
            session=cleaned['session'],
            year=cleaned['year'],
            month=cleaned['month'],
        )

        export = request.GET.get('export')
        if export in {'csv', 'pdf'}:
            rows = [
                [row.date, row.get_status_display()]
                for row in records
            ]
            headers = ['Date', 'Status']
            title = (
                f"Student Monthly Attendance - {cleaned['student'].admission_number} "
                f"({cleaned['month']}/{cleaned['year']})"
            )
            response = _response_for_export(
                title=title,
                headers=headers,
                rows=rows,
                filename_base='student_monthly_attendance',
                export_type=export,
            )
            if response:
                return response

    return render(request, 'attendance_core/report_student_monthly.html', {
        'form': form,
        'summary': summary,
        'records': records,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def attendance_report_staff(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    form = StaffAttendanceReportForm(
        request.GET or None,
        school=school,
        default_session=default_session,
    )
    report_rows = []

    if form.is_valid():
        cleaned = form.cleaned_data
        report_rows = teacher_staff_attendance_report(
            school=school,
            session=cleaned['session'],
            date_from=cleaned['date_from'],
            date_to=cleaned['date_to'],
            staff=cleaned.get('staff'),
        )

        export = request.GET.get('export')
        if export in {'csv', 'pdf'}:
            rows = [
                [
                    row['staff'].employee_id,
                    row['staff'].full_name,
                    row['total_days'],
                    row['present_days'],
                    row['half_days'],
                    row['leave_days'],
                ]
                for row in report_rows
            ]
            headers = ['Employee ID', 'Staff', 'Total Days', 'Present', 'Half-Day', 'Leave']
            title = (
                f"Staff Attendance Report ({cleaned['date_from']} to {cleaned['date_to']})"
            )
            response = _response_for_export(
                title=title,
                headers=headers,
                rows=rows,
                filename_base='staff_attendance_report',
                export_type=export,
            )
            if response:
                return response

    return render(request, 'attendance_core/report_staff.html', {
        'form': form,
        'report_rows': report_rows,
    })


@login_required
@role_required('schooladmin')
def attendance_report_threshold(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    form = ThresholdReportForm(
        request.GET or None,
        school=school,
        default_session=default_session,
    )
    summaries = []

    if form.is_valid():
        cleaned = form.cleaned_data
        students = Student.objects.filter(
            school=school,
            session_records__session=cleaned['session'],
            session_records__school=school,
            is_archived=False,
        ).distinct()

        for student in students:
            calculate_student_monthly_summary(
                student=student,
                session=cleaned['session'],
                year=cleaned['year'],
                month=cleaned['month'],
            )

        summaries = students_below_threshold(
            school=school,
            session=cleaned['session'],
            threshold=cleaned['threshold'],
            year=cleaned['year'],
            month=cleaned['month'],
        )

        export = request.GET.get('export')
        if export in {'csv', 'pdf'}:
            rows = [
                [
                    row.student.admission_number,
                    row.student.full_name,
                    row.total_working_days,
                    row.present_days,
                    row.attendance_percentage,
                ]
                for row in summaries
            ]
            headers = ['Admission No', 'Student', 'Working Days', 'Present Days', 'Attendance %']
            title = (
                f"Attendance Below {cleaned['threshold']}% ({cleaned['month']}/{cleaned['year']})"
            )
            response = _response_for_export(
                title=title,
                headers=headers,
                rows=rows,
                filename_base='attendance_below_threshold',
                export_type=export,
            )
            if response:
                return response

    return render(request, 'attendance_core/report_threshold.html', {
        'form': form,
        'summaries': summaries,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def attendance_report_absentees(request):
    school = request.user.school
    _, default_session = _session_from_request(request, school)
    form = DailyAbsenteeReportForm(
        request.GET or None,
        school=school,
        default_session=default_session,
    )
    records = []

    if form.is_valid():
        cleaned = form.cleaned_data
        records = daily_absentee_list(
            school=school,
            session=cleaned['session'],
            target_date=cleaned['target_date'],
            school_class=cleaned.get('school_class'),
            section=cleaned.get('section'),
        )

        export = request.GET.get('export')
        if export in {'csv', 'pdf'}:
            rows = [
                [
                    row.student.admission_number,
                    row.student.full_name,
                    row.school_class.name,
                    row.section.name,
                    row.date,
                ]
                for row in records
            ]
            headers = ['Admission No', 'Student', 'Class', 'Section', 'Date']
            title = f"Daily Absentee List ({cleaned['target_date']})"
            response = _response_for_export(
                title=title,
                headers=headers,
                rows=rows,
                filename_base='daily_absentee_list',
                export_type=export,
            )
            if response:
                return response

    return render(request, 'attendance_core/report_absentees.html', {
        'form': form,
        'records': records,
    })
