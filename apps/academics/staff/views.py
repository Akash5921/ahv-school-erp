from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.core.users.decorators import role_required
from apps.core.users.audit import log_audit_event

from apps.academics.students.models import Student
from apps.academics.attendance.models import StudentAttendance
from .forms import StaffForm, StaffUserMapForm
from .models import Staff
from django.db.models import Count, Q
from django.db.models.functions import ExtractMonth



@login_required
@role_required('teacher')
def teacher_dashboard(request):

    school = request.user.school

    students = Student.objects.filter(school=school)

    # Total students
    total_students = students.count()

    # Today's attendance
    today = timezone.now().date()

    today_attendance = StudentAttendance.objects.filter(
        school=school,
        date=today
    )

    present_count = today_attendance.filter(status='present').count()
    absent_count = today_attendance.filter(status='absent').count()

    # Monthly Attendance Chart Data
    monthly_data = (
        StudentAttendance.objects
        .filter(school=school)
        .annotate(month=ExtractMonth('date'))
        .values('month')
        .annotate(
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent'))
        )
        .order_by('month')
    )

    months = list(range(1, 13))

    present_dict = {item['month']: item['present'] for item in monthly_data}
    absent_dict = {item['month']: item['absent'] for item in monthly_data}

    present_list = [present_dict.get(m, 0) for m in months]
    absent_list = [absent_dict.get(m, 0) for m in months]

    attendance_summary = []
    current_session = school.current_session
    for student in students:
        total_days = StudentAttendance.objects.filter(
            school=school,
            academic_session=current_session,
            student=student
        ).count()
        present_days = StudentAttendance.objects.filter(
            school=school,
            academic_session=current_session,
            student=student,
            status='present'
        ).count()
        percentage = round((present_days / total_days) * 100, 2) if total_days else 0
        attendance_summary.append({
            'student': student,
            'percentage': percentage,
        })

    return render(request, 'staff/teacher_dashboard.html', {
        'total_students': total_students,
        'present_count': present_count,
        'absent_count': absent_count,
        'present_list': present_list,
        'absent_list': absent_list,
        'attendance_summary': attendance_summary,
    })


@login_required
@role_required('schooladmin')
def staff_list(request):
    staff_members = Staff.objects.filter(
        school=request.user.school
    ).order_by('staff_type', 'first_name')
    return render(request, 'staff/staff_list.html', {
        'staff_members': staff_members
    })


@login_required
@role_required('schooladmin')
def staff_create(request):
    if request.method == 'POST':
        form = StaffForm(request.POST)
        if form.is_valid():
            staff_member = form.save(commit=False)
            staff_member.school = request.user.school
            staff_member.save()
            return redirect('staff_list')
    else:
        form = StaffForm()

    return render(request, 'staff/staff_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def staff_update(request, pk):
    staff_member = get_object_or_404(
        Staff,
        pk=pk,
        school=request.user.school
    )

    if request.method == 'POST':
        form = StaffForm(request.POST, instance=staff_member)
        if form.is_valid():
            form.save()
            return redirect('staff_list')
    else:
        form = StaffForm(instance=staff_member)

    return render(request, 'staff/staff_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
@require_POST
def staff_toggle_active(request, pk):
    staff_member = get_object_or_404(
        Staff,
        pk=pk,
        school=request.user.school
    )
    staff_member.is_active = not staff_member.is_active
    staff_member.save(update_fields=['is_active'])

    log_audit_event(
        request=request,
        action='staff.active_toggled',
        school=request.user.school,
        target=staff_member,
        details=f"Active={staff_member.is_active}",
    )
    return redirect('staff_list')


@login_required
@role_required('schooladmin')
def staff_assign_user(request, pk):
    staff_member = get_object_or_404(
        Staff,
        pk=pk,
        school=request.user.school
    )

    if staff_member.user:
        return redirect('staff_list')

    if request.method == 'POST':
        form = StaffUserMapForm(request.POST)
        if form.is_valid():
            user_model = get_user_model()
            user = user_model.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                role=form.cleaned_data['role'],
                school=request.user.school,
                first_name=staff_member.first_name,
                last_name=staff_member.last_name,
            )
            staff_member.user = user
            staff_member.save(update_fields=['user'])

            log_audit_event(
                request=request,
                action='staff.user_linked',
                school=request.user.school,
                target=staff_member,
                details=f"Linked user {user.username}",
            )
            return redirect('staff_list')
    else:
        form = StaffUserMapForm(initial={
            'username': f"{staff_member.first_name.lower()}{staff_member.staff_id.lower()}",
            'email': staff_member.email,
        })

    return render(request, 'staff/staff_assign_user.html', {
        'staff_member': staff_member,
        'form': form
    })
