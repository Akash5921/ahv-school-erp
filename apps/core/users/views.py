from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.academics.attendance.models import StudentAttendance
from apps.academics.students.models import Student
from apps.core.users.decorators import role_required


@login_required
def role_redirect(request):

    role = request.user.role

    if role == 'superadmin':
        return redirect('school_list')

    elif role == 'schooladmin':
        return redirect('school_dashboard')

    elif role == 'teacher':
        return redirect('teacher_dashboard')

    elif role == 'accountant':
        return redirect('accountant_dashboard')

    elif role == 'parent':
        return redirect('parent_dashboard')

    elif role == 'staff':
        return redirect('staff_dashboard')

    else:
        return redirect('/login/')


@login_required
@role_required('parent')
def parent_dashboard(request):
    today = timezone.now().date()
    school = request.user.school
    children = Student.objects.filter(
        school=school,
        parent_user=request.user
    ).select_related('school_class', 'section')

    child_rows = []
    current_session = school.current_session
    for child in children:
        today_status = StudentAttendance.objects.filter(
            school=school,
            academic_session=current_session,
            student=child,
            date=today
        ).values_list('status', flat=True).first()
        child_rows.append({
            'student': child,
            'today_status': today_status or 'not-marked',
        })

    return render(request, 'users/parent_dashboard.html', {
        'child_rows': child_rows
    })


@login_required
@role_required('staff')
def staff_dashboard(request):
    return render(request, 'users/staff_dashboard.html')


@login_required
@role_required('parent')
def parent_student_attendance(request, student_id):
    school = request.user.school
    student = Student.objects.filter(
        id=student_id,
        school=school,
        parent_user=request.user
    ).first()
    if not student:
        return render(request, 'reports/forbidden.html', status=403)

    selected_month = request.GET.get('month')
    attendance_queryset = StudentAttendance.objects.filter(
        school=school,
        academic_session=school.current_session,
        student=student
    ).order_by('-date')

    if selected_month:
        try:
            attendance_queryset = attendance_queryset.filter(date__month=int(selected_month))
        except ValueError:
            selected_month = ''

    total_days = attendance_queryset.count()
    present_days = attendance_queryset.filter(status='present').count()
    absent_days = attendance_queryset.filter(status='absent').count()
    percentage = round((present_days / total_days) * 100, 2) if total_days else 0

    return render(request, 'users/parent_student_attendance.html', {
        'student': student,
        'attendance_rows': attendance_queryset,
        'selected_month': selected_month,
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': absent_days,
        'percentage': percentage,
    })
