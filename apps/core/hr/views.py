from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    ClassTeacherForm,
    DesignationForm,
    LeaveRequestForm,
    LeaveReviewForm,
    PayrollHoldForm,
    PayrollProcessForm,
    SalaryAdvanceForm,
    SalaryAdvanceStatusForm,
    SalaryStructureForm,
    StaffAttendanceForm,
    StaffForm,
    SubstitutionForm,
    TeacherSubjectAssignmentForm,
)
from .models import (
    ClassTeacher,
    Designation,
    LeaveRequest,
    Payroll,
    SalaryHistory,
    SalaryAdvance,
    SalaryStructure,
    Staff,
    StaffAttendance,
    Substitution,
    TeacherSubjectAssignment,
)
from .services import (
    create_salary_advance,
    generate_bulk_payslip_pdf,
    generate_payslip_pdf,
    lock_payroll,
    mark_payroll_paid,
    mark_staff_attendance,
    process_monthly_payroll,
    process_monthly_payroll_for_all,
    review_leave_request,
    set_payroll_hold,
    set_salary_structure,
    submit_leave_request,
    unlock_payroll,
    update_salary_advance_status,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('session') or request.POST.get('filter_session')

    selected_session = None
    if session_id:
        selected_session = sessions.filter(id=session_id).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


def _resolve_selected_period(request):
    today = timezone.localdate()
    month = request.GET.get('month') or request.POST.get('month')
    year = request.GET.get('year') or request.POST.get('year')
    try:
        month_value = int(month) if month else today.month
    except (TypeError, ValueError):
        month_value = today.month
    try:
        year_value = int(year) if year else today.year
    except (TypeError, ValueError):
        year_value = today.year

    if month_value < 1 or month_value > 12:
        month_value = today.month
    return month_value, year_value


def _actor_staff(user):
    if not getattr(user, 'school_id', None):
        return None
    return Staff.objects.filter(school=user.school, user=user).first()


@login_required
@role_required('schooladmin')
def hr_designation_list(request):
    designations = Designation.objects.filter(school=request.user.school).order_by('name')
    return render(request, 'hr/designation_list.html', {'designations': designations})


@login_required
@role_required('schooladmin')
def hr_designation_create(request):
    if request.method == 'POST':
        form = DesignationForm(request.POST)
        if form.is_valid():
            designation = form.save(commit=False)
            designation.school = request.user.school
            designation.save()
            log_audit_event(
                request=request,
                action='hr.designation_created',
                school=request.user.school,
                target=designation,
                details=f"Name={designation.name}",
            )
            messages.success(request, 'Designation created successfully.')
            return redirect('hr_designation_list')
    else:
        form = DesignationForm()

    return render(request, 'hr/designation_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def hr_designation_update(request, pk):
    designation = get_object_or_404(Designation, pk=pk, school=request.user.school)

    if request.method == 'POST':
        form = DesignationForm(request.POST, instance=designation)
        if form.is_valid():
            designation = form.save()
            log_audit_event(
                request=request,
                action='hr.designation_updated',
                school=request.user.school,
                target=designation,
                details=f"Name={designation.name}",
            )
            messages.success(request, 'Designation updated successfully.')
            return redirect('hr_designation_list')
    else:
        form = DesignationForm(instance=designation)

    return render(request, 'hr/designation_form.html', {
        'form': form,
        'designation': designation,
    })


@login_required
@role_required('schooladmin')
@require_POST
def hr_designation_deactivate(request, pk):
    designation = get_object_or_404(Designation, pk=pk, school=request.user.school)
    designation.delete()

    log_audit_event(
        request=request,
        action='hr.designation_deactivated',
        school=request.user.school,
        target=designation,
        details=f"Name={designation.name}",
    )
    messages.success(request, 'Designation deactivated successfully.')
    return redirect('hr_designation_list')


@login_required
@role_required('schooladmin')
def hr_staff_list(request):
    status = request.GET.get('status')

    staff_members = Staff.objects.filter(school=request.user.school).select_related(
        'user',
        'designation',
    )
    if status:
        staff_members = staff_members.filter(status=status)

    return render(request, 'hr/staff_list.html', {
        'staff_members': staff_members.order_by('employee_id'),
        'selected_status': status,
    })


@login_required
@role_required('schooladmin')
def hr_staff_create(request):
    if request.method == 'POST':
        form = StaffForm(request.POST, request.FILES, school=request.user.school)
        if form.is_valid():
            staff = form.save(commit=False)
            staff.school = request.user.school
            staff.save()
            log_audit_event(
                request=request,
                action='hr.staff_created',
                school=request.user.school,
                target=staff,
                details=f"Employee ID={staff.employee_id}",
            )
            messages.success(request, 'Staff profile created successfully.')
            return redirect('hr_staff_list')
    else:
        form = StaffForm(school=request.user.school)

    return render(request, 'hr/staff_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def hr_staff_update(request, pk):
    staff = get_object_or_404(Staff, pk=pk, school=request.user.school)

    if request.method == 'POST':
        form = StaffForm(request.POST, request.FILES, instance=staff, school=request.user.school)
        if form.is_valid():
            staff = form.save()
            log_audit_event(
                request=request,
                action='hr.staff_updated',
                school=request.user.school,
                target=staff,
                details=f"Employee ID={staff.employee_id}",
            )
            messages.success(request, 'Staff profile updated successfully.')
            return redirect('hr_staff_list')
    else:
        form = StaffForm(instance=staff, school=request.user.school)

    return render(request, 'hr/staff_form.html', {
        'form': form,
        'staff': staff,
    })


@login_required
@role_required('schooladmin')
@require_POST
def hr_staff_deactivate(request, pk):
    staff = get_object_or_404(Staff, pk=pk, school=request.user.school)
    staff.delete()

    log_audit_event(
        request=request,
        action='hr.staff_deactivated',
        school=request.user.school,
        target=staff,
        details=f"Employee ID={staff.employee_id}",
    )
    messages.success(request, 'Staff profile deactivated successfully.')
    return redirect('hr_staff_list')


@login_required
@role_required('schooladmin')
def hr_teacher_subject_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    assignments = TeacherSubjectAssignment.objects.filter(school=school).select_related(
        'session',
        'teacher',
        'teacher__user',
        'school_class',
        'subject',
    )
    if selected_session:
        assignments = assignments.filter(session=selected_session)

    return render(request, 'hr/teacher_subject_list.html', {
        'assignments': assignments.order_by('school_class__display_order', 'subject__name'),
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def hr_teacher_subject_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = TeacherSubjectAssignmentForm(request.POST, school=school, session=selected_session)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.school = school
            assignment.save()
            log_audit_event(
                request=request,
                action='hr.teacher_subject_created',
                school=school,
                target=assignment,
                details=f"Teacher={assignment.teacher_id}, Class={assignment.school_class_id}, Subject={assignment.subject_id}",
            )
            messages.success(request, 'Teacher-subject allocation saved successfully.')
            return redirect('hr_teacher_subject_list')
    else:
        form = TeacherSubjectAssignmentForm(school=school, session=selected_session)

    return render(request, 'hr/teacher_subject_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def hr_teacher_subject_update(request, pk):
    school = request.user.school
    assignment = get_object_or_404(TeacherSubjectAssignment, pk=pk, school=school)

    if request.method == 'POST':
        form = TeacherSubjectAssignmentForm(
            request.POST,
            instance=assignment,
            school=school,
            session=assignment.session,
        )
        if form.is_valid():
            assignment = form.save()
            log_audit_event(
                request=request,
                action='hr.teacher_subject_updated',
                school=school,
                target=assignment,
                details=f"Teacher={assignment.teacher_id}, Class={assignment.school_class_id}, Subject={assignment.subject_id}",
            )
            messages.success(request, 'Teacher-subject allocation updated successfully.')
            return redirect('hr_teacher_subject_list')
    else:
        form = TeacherSubjectAssignmentForm(instance=assignment, school=school, session=assignment.session)

    return render(request, 'hr/teacher_subject_form.html', {
        'form': form,
        'assignment': assignment,
    })


@login_required
@role_required('schooladmin')
@require_POST
def hr_teacher_subject_deactivate(request, pk):
    assignment = get_object_or_404(TeacherSubjectAssignment, pk=pk, school=request.user.school)
    try:
        assignment.delete()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='hr.teacher_subject_deactivated',
            school=request.user.school,
            target=assignment,
            details=f"ID={assignment.id}",
        )
        messages.success(request, 'Teacher-subject allocation deactivated successfully.')
    return redirect('hr_teacher_subject_list')


@login_required
@role_required('schooladmin')
def hr_class_teacher_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    assignments = ClassTeacher.objects.filter(school=school).select_related(
        'session',
        'school_class',
        'section',
        'teacher',
        'teacher__user',
    )
    if selected_session:
        assignments = assignments.filter(session=selected_session)

    return render(request, 'hr/class_teacher_list.html', {
        'assignments': assignments.order_by('school_class__display_order', 'section__name'),
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def hr_class_teacher_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = ClassTeacherForm(request.POST, school=school, session=selected_session)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.school = school
            assignment.save()
            log_audit_event(
                request=request,
                action='hr.class_teacher_assigned',
                school=school,
                target=assignment,
                details=f"Section={assignment.section_id}, Teacher={assignment.teacher_id}",
            )
            messages.success(request, 'Class teacher assigned successfully.')
            return redirect('hr_class_teacher_list')
    else:
        form = ClassTeacherForm(school=school, session=selected_session)

    return render(request, 'hr/class_teacher_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def hr_class_teacher_update(request, pk):
    school = request.user.school
    assignment = get_object_or_404(ClassTeacher, pk=pk, school=school)

    if request.method == 'POST':
        form = ClassTeacherForm(
            request.POST,
            instance=assignment,
            school=school,
            session=assignment.session,
        )
        if form.is_valid():
            assignment = form.save()
            log_audit_event(
                request=request,
                action='hr.class_teacher_updated',
                school=school,
                target=assignment,
                details=f"Section={assignment.section_id}, Teacher={assignment.teacher_id}",
            )
            messages.success(request, 'Class teacher assignment updated successfully.')
            return redirect('hr_class_teacher_list')
    else:
        form = ClassTeacherForm(instance=assignment, school=school, session=assignment.session)

    return render(request, 'hr/class_teacher_form.html', {
        'form': form,
        'assignment': assignment,
    })


@login_required
@role_required('schooladmin')
@require_POST
def hr_class_teacher_deactivate(request, pk):
    assignment = get_object_or_404(ClassTeacher, pk=pk, school=request.user.school)
    try:
        assignment.delete()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='hr.class_teacher_deactivated',
            school=request.user.school,
            target=assignment,
            details=f"ID={assignment.id}",
        )
        messages.success(request, 'Class teacher assignment deactivated successfully.')
    return redirect('hr_class_teacher_list')


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant'])
def hr_staff_attendance_list(request):
    school = request.user.school
    actor_is_admin = request.user.role == 'schooladmin'
    actor_staff = _actor_staff(request.user)

    attendances = StaffAttendance.objects.filter(school=school).select_related('staff', 'staff__user', 'marked_by')

    selected_date = request.GET.get('date')
    selected_staff = request.GET.get('staff')

    if selected_date:
        attendances = attendances.filter(date=selected_date)

    if actor_is_admin:
        if selected_staff and selected_staff.isdigit():
            attendances = attendances.filter(staff_id=int(selected_staff))
    else:
        if not actor_staff:
            messages.error(request, 'Your staff profile is not configured.')
            attendances = attendances.none()
        else:
            attendances = attendances.filter(staff=actor_staff)

    staff_options = Staff.objects.filter(school=school, is_active=True).order_by('employee_id') if actor_is_admin else []

    return render(request, 'hr/staff_attendance_list.html', {
        'attendances': attendances.order_by('-date', 'staff__employee_id'),
        'selected_date': selected_date,
        'selected_staff': int(selected_staff) if str(selected_staff).isdigit() else None,
        'staff_options': staff_options,
        'actor_is_admin': actor_is_admin,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant'])
def hr_staff_attendance_mark(request):
    school = request.user.school
    actor_is_admin = request.user.role == 'schooladmin'
    actor_staff = _actor_staff(request.user)

    if not actor_is_admin and not actor_staff:
        messages.error(request, 'Your staff profile is not configured.')
        return redirect('hr_staff_attendance_list')

    if request.method == 'POST':
        form = StaffAttendanceForm(
            request.POST,
            school=school,
            actor_staff=actor_staff,
            lock_staff=not actor_is_admin,
        )
        if form.is_valid():
            try:
                attendance, created = mark_staff_attendance(
                    school=school,
                    staff=form.cleaned_data['staff'],
                    date=form.cleaned_data['date'],
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
                action = 'hr.staff_attendance_marked' if created else 'hr.staff_attendance_updated'
                log_audit_event(
                    request=request,
                    action=action,
                    school=school,
                    target=attendance,
                    details=f"Staff={attendance.staff_id}, Date={attendance.date}, Status={attendance.status}",
                )
                messages.success(request, 'Attendance recorded successfully.')
                return redirect('hr_staff_attendance_list')
    else:
        initial = {'date': timezone.localdate(), 'status': StaffAttendance.STATUS_PRESENT}
        if actor_staff and not actor_is_admin:
            initial['staff'] = actor_staff
        form = StaffAttendanceForm(
            initial=initial,
            school=school,
            actor_staff=actor_staff,
            lock_staff=not actor_is_admin,
        )

    return render(request, 'hr/staff_attendance_form.html', {
        'form': form,
        'actor_is_admin': actor_is_admin,
    })


@login_required
@role_required('schooladmin')
def hr_staff_attendance_edit(request, pk):
    school = request.user.school
    attendance = get_object_or_404(StaffAttendance, pk=pk, school=school)

    if request.method == 'POST':
        form = StaffAttendanceForm(request.POST, instance=attendance, school=school)
        form.fields['staff'].disabled = True
        form.fields['date'].disabled = True

        if form.is_valid():
            try:
                attendance, _ = mark_staff_attendance(
                    school=school,
                    staff=attendance.staff,
                    date=attendance.date,
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
                    action='hr.staff_attendance_edited',
                    school=school,
                    target=attendance,
                    details=f"Staff={attendance.staff_id}, Date={attendance.date}, Status={attendance.status}",
                )
                messages.success(request, 'Attendance updated successfully.')
                return redirect('hr_staff_attendance_list')
    else:
        form = StaffAttendanceForm(instance=attendance, school=school)
        form.fields['staff'].disabled = True
        form.fields['date'].disabled = True

    return render(request, 'hr/staff_attendance_form.html', {
        'form': form,
        'attendance': attendance,
        'actor_is_admin': True,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant'])
def hr_leave_request_list(request):
    school = request.user.school
    actor_is_admin = request.user.role == 'schooladmin'
    actor_staff = _actor_staff(request.user)

    leaves = LeaveRequest.objects.filter(school=school).select_related('staff', 'staff__user', 'approved_by')

    if not actor_is_admin:
        if not actor_staff:
            leaves = leaves.none()
            messages.error(request, 'Your staff profile is not configured.')
        else:
            leaves = leaves.filter(staff=actor_staff)

    status = request.GET.get('status')
    if status:
        leaves = leaves.filter(status=status)

    return render(request, 'hr/leave_request_list.html', {
        'leaves': leaves.order_by('-created_at'),
        'selected_status': status,
        'actor_is_admin': actor_is_admin,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant'])
def hr_leave_request_create(request):
    school = request.user.school
    actor_is_admin = request.user.role == 'schooladmin'
    actor_staff = _actor_staff(request.user)

    if not actor_is_admin and not actor_staff:
        messages.error(request, 'Your staff profile is not configured.')
        return redirect('hr_leave_request_list')

    if request.method == 'POST':
        form = LeaveRequestForm(
            request.POST,
            school=school,
            actor_staff=actor_staff,
            lock_staff=not actor_is_admin,
        )
        if form.is_valid():
            try:
                leave_request = submit_leave_request(
                    school=school,
                    staff=form.cleaned_data['staff'],
                    leave_type=form.cleaned_data['leave_type'],
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data['end_date'],
                    reason=form.cleaned_data['reason'],
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='hr.leave_requested',
                    school=school,
                    target=leave_request,
                    details=f"Staff={leave_request.staff_id}, {leave_request.start_date} to {leave_request.end_date}",
                )
                messages.success(request, 'Leave request submitted successfully.')
                return redirect('hr_leave_request_list')
    else:
        initial = {}
        if actor_staff and not actor_is_admin:
            initial['staff'] = actor_staff
        form = LeaveRequestForm(
            initial=initial,
            school=school,
            actor_staff=actor_staff,
            lock_staff=not actor_is_admin,
        )

    return render(request, 'hr/leave_request_form.html', {
        'form': form,
        'actor_is_admin': actor_is_admin,
    })


@login_required
@role_required('schooladmin')
@require_POST
def hr_leave_request_review(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk, school=request.user.school)
    form = LeaveReviewForm(request.POST)

    if not form.is_valid():
        messages.error(request, 'Invalid leave review action.')
        return redirect('hr_leave_request_list')

    decision = form.cleaned_data['decision']

    try:
        leave_request = review_leave_request(
            leave_request=leave_request,
            approved_by=request.user,
            decision=decision,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('hr_leave_request_list')

    log_audit_event(
        request=request,
        action='hr.leave_reviewed',
        school=request.user.school,
        target=leave_request,
        details=f"Decision={decision}",
    )
    messages.success(request, 'Leave request reviewed successfully.')
    return redirect('hr_leave_request_list')


@login_required
@role_required('schooladmin')
def hr_substitution_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    substitutions = Substitution.objects.filter(school=school).select_related(
        'session',
        'period',
        'school_class',
        'section',
        'subject',
        'original_teacher',
        'original_teacher__user',
        'substitute_teacher',
        'substitute_teacher__user',
    )

    if selected_session:
        substitutions = substitutions.filter(session=selected_session)

    selected_date = request.GET.get('date')
    if selected_date:
        substitutions = substitutions.filter(date=selected_date)

    return render(request, 'hr/substitution_list.html', {
        'substitutions': substitutions.order_by('-date', 'period__period_number'),
        'sessions': sessions,
        'selected_session': selected_session,
        'selected_date': selected_date,
    })


@login_required
@role_required('schooladmin')
def hr_substitution_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = SubstitutionForm(request.POST, school=school, session=selected_session)
        if form.is_valid():
            substitution = form.save(commit=False)
            substitution.school = school
            substitution.save()
            log_audit_event(
                request=request,
                action='hr.substitution_created',
                school=school,
                target=substitution,
                details=f"Date={substitution.date}, Period={substitution.period_id}",
            )
            messages.success(request, 'Substitution added successfully.')
            return redirect('hr_substitution_list')
    else:
        form = SubstitutionForm(school=school, session=selected_session)

    return render(request, 'hr/substitution_form.html', {
        'form': form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def hr_substitution_update(request, pk):
    school = request.user.school
    substitution = get_object_or_404(Substitution, pk=pk, school=school)

    if request.method == 'POST':
        form = SubstitutionForm(request.POST, instance=substitution, school=school, session=substitution.session)
        if form.is_valid():
            substitution = form.save()
            log_audit_event(
                request=request,
                action='hr.substitution_updated',
                school=school,
                target=substitution,
                details=f"Date={substitution.date}, Period={substitution.period_id}",
            )
            messages.success(request, 'Substitution updated successfully.')
            return redirect('hr_substitution_list')
    else:
        form = SubstitutionForm(instance=substitution, school=school, session=substitution.session)

    return render(request, 'hr/substitution_form.html', {
        'form': form,
        'substitution': substitution,
    })


@login_required
@role_required('schooladmin')
@require_POST
def hr_substitution_deactivate(request, pk):
    substitution = get_object_or_404(Substitution, pk=pk, school=request.user.school)
    try:
        substitution.delete()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='hr.substitution_deactivated',
            school=request.user.school,
            target=substitution,
            details=f"ID={substitution.id}",
        )
        messages.success(request, 'Substitution deactivated successfully.')
    return redirect('hr_substitution_list')


@login_required
@role_required(['schooladmin', 'accountant'])
def hr_salary_structure_list(request):
    school = request.user.school

    structures = SalaryStructure.objects.filter(school=school).select_related('staff', 'staff__user')
    histories = SalaryHistory.objects.filter(school=school).select_related('staff', 'staff__user', 'changed_by')[:50]

    if request.method == 'POST':
        form = SalaryStructureForm(request.POST, school=school)
        if form.is_valid():
            try:
                structure, history = set_salary_structure(
                    school=school,
                    staff=form.cleaned_data['staff'],
                    basic_salary=form.cleaned_data['basic_salary'],
                    hra=form.cleaned_data['hra'] or 0,
                    da=form.cleaned_data['da'] or 0,
                    transport_allowance=form.cleaned_data['transport_allowance'] or 0,
                    other_allowances=form.cleaned_data['other_allowances'],
                    pf_deduction=form.cleaned_data['pf_deduction'] or 0,
                    esi_deduction=form.cleaned_data['esi_deduction'] or 0,
                    professional_tax=form.cleaned_data['professional_tax'] or 0,
                    other_deductions=form.cleaned_data['other_deductions'],
                    effective_from=form.cleaned_data['effective_from'],
                    changed_by=request.user,
                    reason=form.cleaned_data['reason'],
                )
            except ValidationError as exc:
                form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='hr.salary_structure_set',
                    school=school,
                    target=structure,
                    details=f"Staff={structure.staff_id}, Basic={structure.basic_salary}",
                )
                log_audit_event(
                    request=request,
                    action='hr.salary_history_logged',
                    school=school,
                    target=history,
                    details=f"Old={history.old_salary}, New={history.new_salary}",
                )
                messages.success(request, 'Salary structure updated successfully.')
                return redirect('hr_salary_structure_list')
    else:
        form = SalaryStructureForm(school=school)

    return render(request, 'hr/salary_structure_list.html', {
        'structures': structures.order_by('-is_active', 'staff__employee_id', '-effective_from'),
        'histories': histories,
        'form': form,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def hr_salary_advance_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    create_form = SalaryAdvanceForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'create' else None,
        school=school,
        default_session=selected_session,
    )
    status_form = SalaryAdvanceStatusForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'status' else None
    )

    if request.method == 'POST' and request.POST.get('action') == 'create':
        if create_form.is_valid():
            try:
                advance = create_salary_advance(
                    school=school,
                    session=create_form.cleaned_data['session'],
                    staff=create_form.cleaned_data['staff'],
                    amount=create_form.cleaned_data['amount'],
                    request_date=create_form.cleaned_data['request_date'],
                    approved_by=request.user if create_form.cleaned_data['status'] != SalaryAdvance.STATUS_PENDING else None,
                    status=create_form.cleaned_data['status'],
                )
            except ValidationError as exc:
                create_form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='hr.salary_advance_created',
                    school=school,
                    target=advance,
                    details=f"Staff={advance.staff_id}, Amount={advance.amount}, Status={advance.status}",
                )
                messages.success(request, 'Salary advance saved successfully.')
                return redirect('hr_salary_advance_list')

    if request.method == 'POST' and request.POST.get('action') == 'status':
        advance_id = request.POST.get('advance_id')
        advance = get_object_or_404(SalaryAdvance, pk=advance_id, school=school)
        if status_form.is_valid():
            try:
                advance = update_salary_advance_status(
                    salary_advance=advance,
                    status=status_form.cleaned_data['status'],
                    approved_by=request.user,
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='hr.salary_advance_status_updated',
                    school=school,
                    target=advance,
                    details=f"Status={advance.status}",
                )
                messages.success(request, 'Salary advance status updated successfully.')
                return redirect('hr_salary_advance_list')

    advances = SalaryAdvance.objects.filter(school=school).select_related('session', 'staff', 'staff__user', 'approved_by')
    if selected_session:
        advances = advances.filter(session=selected_session)

    return render(request, 'hr/salary_advance_list.html', {
        'advances': advances.order_by('-request_date', '-id'),
        'sessions': sessions,
        'selected_session': selected_session,
        'create_form': create_form,
        'status_form': status_form,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def hr_payroll_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    selected_month, selected_year = _resolve_selected_period(request)

    process_form = PayrollProcessForm(
        request.POST if request.method == 'POST' and request.POST.get('action') in {'process', 'process_all'} else None,
        school=school,
        default_session=selected_session,
    )
    hold_form = PayrollHoldForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'hold' else None
    )

    if request.method == 'POST' and request.POST.get('action') == 'process':
        if process_form.is_valid():
            staff = process_form.cleaned_data['staff']
            if not staff:
                process_form.add_error('staff', 'Select a staff member for single payroll processing.')
            else:
                try:
                    payroll = process_monthly_payroll(
                        school=school,
                        session=process_form.cleaned_data['session'],
                        staff=staff,
                        month=process_form.cleaned_data['month'],
                        year=process_form.cleaned_data['year'],
                        processed_by=request.user,
                    )
                except ValidationError as exc:
                    process_form.add_error(None, '; '.join(exc.messages))
                else:
                    log_audit_event(
                        request=request,
                        action='hr.payroll_processed',
                        school=school,
                        target=payroll,
                        details=f"Staff={payroll.staff_id}, Period={payroll.month:02d}/{payroll.year}",
                    )
                    messages.success(request, 'Payroll processed successfully.')
                    query = f"session={payroll.session_id}&month={payroll.month}&year={payroll.year}"
                    return redirect(f"{reverse('hr_payroll_list')}?{query}")

    if request.method == 'POST' and request.POST.get('action') == 'process_all':
        if process_form.is_valid():
            try:
                processed_rows, errors = process_monthly_payroll_for_all(
                    school=school,
                    session=process_form.cleaned_data['session'],
                    month=process_form.cleaned_data['month'],
                    year=process_form.cleaned_data['year'],
                    processed_by=request.user,
                )
            except ValidationError as exc:
                process_form.add_error(None, '; '.join(exc.messages))
            else:
                if processed_rows:
                    messages.success(request, f'Processed payroll for {len(processed_rows)} staff members.')
                if errors:
                    messages.error(request, '; '.join(errors))
                for payroll in processed_rows:
                    log_audit_event(
                        request=request,
                        action='hr.payroll_processed',
                        school=school,
                        target=payroll,
                        details=f"Staff={payroll.staff_id}, Period={payroll.month:02d}/{payroll.year}",
                    )
                query = (
                    f"session={process_form.cleaned_data['session'].id}"
                    f"&month={process_form.cleaned_data['month']}&year={process_form.cleaned_data['year']}"
                )
                return redirect(f"{reverse('hr_payroll_list')}?{query}")

    if request.method == 'POST' and request.POST.get('action') == 'lock':
        payroll = get_object_or_404(Payroll, pk=request.POST.get('payroll_id'), school=school)
        try:
            lock_payroll(payroll=payroll)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            log_audit_event(
                request=request,
                action='hr.payroll_locked',
                school=school,
                target=payroll,
                details=f"Period={payroll.month:02d}/{payroll.year}",
            )
            messages.success(request, 'Payroll locked successfully.')
        return redirect('hr_payroll_list')

    if request.method == 'POST' and request.POST.get('action') == 'hold':
        payroll = get_object_or_404(Payroll, pk=request.POST.get('payroll_id'), school=school)
        if hold_form.is_valid():
            try:
                set_payroll_hold(
                    payroll=payroll,
                    on_hold=True,
                    reason=hold_form.cleaned_data['reason'],
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='hr.payroll_hold_set',
                    school=school,
                    target=payroll,
                    details=f"Reason={payroll.hold_reason}",
                )
                messages.success(request, 'Payroll hold enabled.')
        return redirect('hr_payroll_list')

    if request.method == 'POST' and request.POST.get('action') == 'release_hold':
        payroll = get_object_or_404(Payroll, pk=request.POST.get('payroll_id'), school=school)
        try:
            set_payroll_hold(payroll=payroll, on_hold=False)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            log_audit_event(
                request=request,
                action='hr.payroll_hold_released',
                school=school,
                target=payroll,
                details='Hold released',
            )
            messages.success(request, 'Payroll hold released.')
        return redirect('hr_payroll_list')

    if request.method == 'POST' and request.POST.get('action') == 'mark_paid':
        payroll = get_object_or_404(Payroll, pk=request.POST.get('payroll_id'), school=school)
        try:
            mark_payroll_paid(payroll=payroll, paid_by=request.user)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            log_audit_event(
                request=request,
                action='hr.payroll_marked_paid',
                school=school,
                target=payroll,
                details=f"PaidOn={payroll.paid_on}",
            )
            messages.success(request, 'Payroll marked as paid.')
        return redirect('hr_payroll_list')

    payroll_rows = Payroll.objects.filter(school=school).select_related('session', 'staff', 'staff__user', 'processed_by', 'paid_by')
    if selected_session:
        payroll_rows = payroll_rows.filter(session=selected_session)
    payroll_rows = payroll_rows.filter(month=selected_month, year=selected_year).order_by('staff__employee_id')

    month_choices = [(idx, f'{idx:02d}') for idx in range(1, 13)]
    year_choices = sorted({row.year for row in Payroll.objects.filter(school=school)} | {timezone.localdate().year}, reverse=True)

    return render(request, 'hr/payroll_list.html', {
        'payroll_rows': payroll_rows,
        'sessions': sessions,
        'selected_session': selected_session,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_choices': month_choices,
        'year_choices': year_choices,
        'process_form': process_form,
        'hold_form': hold_form,
    })


@login_required
@role_required('superadmin')
@require_POST
def hr_payroll_unlock(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    try:
        unlock_payroll(payroll=payroll, allow_override=True)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='hr.payroll_unlocked_override',
            school=payroll.school,
            target=payroll,
            details='Superadmin override',
        )
        messages.success(request, 'Payroll unlocked by super admin override.')
    return redirect(reverse('admin:index'))


@login_required
@role_required(['schooladmin', 'accountant'])
def hr_payslip_download(request, payroll_id):
    payroll = get_object_or_404(
        Payroll.objects.select_related('school', 'session', 'staff', 'staff__user', 'staff__designation'),
        pk=payroll_id,
        school=request.user.school,
    )
    pdf_bytes = generate_payslip_pdf(payroll=payroll)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="payslip_{payroll.staff.employee_id}_{payroll.month:02d}_{payroll.year}.pdf"'
    )
    return response


@login_required
@role_required(['schooladmin', 'accountant'])
def hr_payslip_bulk_download(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    selected_month, selected_year = _resolve_selected_period(request)
    del sessions  # Selection already resolved from request context.

    payrolls = Payroll.objects.filter(
        school=school,
        month=selected_month,
        year=selected_year,
    ).select_related('school', 'session', 'staff', 'staff__user', 'staff__designation').order_by('staff__employee_id')
    if selected_session:
        payrolls = payrolls.filter(session=selected_session)

    if not payrolls.exists():
        messages.error(request, 'No payroll rows found for selected filters.')
        return redirect('hr_payroll_list')

    pdf_bytes = generate_bulk_payslip_pdf(payrolls=payrolls)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="payslips_{selected_month:02d}_{selected_year}.pdf"'
    return response
