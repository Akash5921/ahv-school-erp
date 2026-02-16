from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from apps.core.users.decorators import role_required

from apps.academics.students.models import Student
from apps.academics.attendance.models import StudentAttendance
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

    return render(request, 'staff/teacher_dashboard.html', {
        'total_students': total_students,
        'present_count': present_count,
        'absent_count': absent_count,
        'present_list': present_list,
        'absent_list': absent_list,
    })