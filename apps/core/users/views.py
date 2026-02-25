from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.academics.attendance.models import StudentAttendance
from apps.academics.students.models import Student
from apps.finance.fees.models import FeePayment, StudentFee
from apps.operations.communication.models import Notice, NoticeRead
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
    current_session = school.current_session
    children = Student.objects.filter(
        school=school,
        parent_user=request.user
    ).select_related('school_class', 'section')

    child_rows = []
    total_due_amount = 0

    for child in children:
        today_status = StudentAttendance.objects.filter(
            school=school,
            academic_session=current_session,
            student=child,
            date=today
        ).values_list('status', flat=True).first()

        child_fee_rows = StudentFee.objects.filter(
            student=child,
            fee_structure__academic_session=current_session
        ).select_related('fee_structure')
        child_due_amount = sum((fee_row.due_amount for fee_row in child_fee_rows), start=0)
        total_due_amount += child_due_amount

        child_rows.append({
            'student': child,
            'today_status': today_status or 'not-marked',
            'due_amount': child_due_amount,
        })

    notice_queryset = Notice.objects.filter(
        school=school,
        is_published=True,
        target_role__in=['all', 'parent']
    ).order_by('-publish_at', '-id')[:10]
    read_notice_ids = set(
        NoticeRead.objects.filter(
            user=request.user,
            notice__in=notice_queryset
        ).values_list('notice_id', flat=True)
    )
    notice_rows = []
    unread_notice_count = 0
    for notice in notice_queryset:
        is_read = notice.id in read_notice_ids
        if not is_read:
            unread_notice_count += 1
        notice_rows.append({
            'notice': notice,
            'is_read': is_read,
        })

    return render(request, 'users/parent_dashboard.html', {
        'child_rows': child_rows,
        'total_due_amount': total_due_amount,
        'notice_rows': notice_rows,
        'unread_notice_count': unread_notice_count,
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


@login_required
@role_required('parent')
def parent_student_fees(request, student_id):
    school = request.user.school
    student = Student.objects.filter(
        id=student_id,
        school=school,
        parent_user=request.user
    ).first()
    if not student:
        return render(request, 'reports/forbidden.html', status=403)

    current_session = school.current_session
    student_fee_rows = StudentFee.objects.filter(
        student=student,
        fee_structure__academic_session=current_session
    ).select_related(
        'fee_structure',
        'fee_structure__school_class',
        'fee_structure__academic_session'
    ).order_by('fee_structure__name')

    payments = FeePayment.objects.filter(
        school=school,
        student=student,
        student_fee__in=student_fee_rows
    ).order_by('-date', '-id')

    total_due = sum((row.due_amount for row in student_fee_rows), start=0)

    return render(request, 'users/parent_student_fees.html', {
        'student': student,
        'student_fee_rows': student_fee_rows,
        'payments': payments,
        'current_session': current_session,
        'total_due': total_due,
    })
