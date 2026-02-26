from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
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
    SalaryHistory,
    SalaryStructure,
    Staff,
    StaffAttendance,
    Substitution,
    TeacherSubjectAssignment,
)
from .services import mark_staff_attendance, review_leave_request, set_salary_structure, submit_leave_request


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('filter_session')

    selected_session = None
    if session_id:
        selected_session = sessions.filter(id=session_id).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


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
    assignment.delete()

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
    assignment.delete()

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
    substitution.delete()

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
                    allowances=form.cleaned_data['allowances'],
                    deductions=form.cleaned_data['deductions'],
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
