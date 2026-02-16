from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import StudentAttendance
from apps.academics.students.models import Student
from django.db import transaction
from apps.core.academics.models import SchoolClass, Section
from apps.core.users.decorators import role_required




@login_required
@role_required('teacher')
def mark_attendance(request):
    school = request.user.school
    today = timezone.now().date()

    classes = SchoolClass.objects.filter(school=school)
    sections = Section.objects.filter(school_class__school=school)

    selected_class = request.GET.get('class', '')
    selected_section = request.GET.get('section', '')
    students = None
    school_class = None
    section = None
    error = None

    if request.method == 'POST':
        selected_class = request.POST.get('class', '').strip() or request.GET.get('class', '').strip()
        selected_section = request.POST.get('section', '').strip() or request.GET.get('section', '').strip()

    if selected_class and selected_section:
        school_class = SchoolClass.objects.filter(id=selected_class, school=school).first()
        section = Section.objects.filter(id=selected_section, school_class=school_class).first() if school_class else None

        if school_class and section:
            students = Student.objects.filter(
                school=school,
                school_class=school_class,
                section=section
            )
        else:
            error = 'Invalid class or section selected.'

    if request.method == 'POST':
        if not school_class or not section:
            error = error or 'Please select a valid class and section.'
        else:
            current_session = school.current_session
            if not current_session:
                error = 'No active academic session set for this school.'
            else:
                valid_statuses = {choice[0] for choice in StudentAttendance.STATUS_CHOICES}
                attendance_rows = []

                for student in students:
                    status = request.POST.get(f'status_{student.id}')
                    if status not in valid_statuses:
                        error = 'Please mark attendance for all listed students.'
                        break
                    attendance_rows.append((student, status))

                if not error:
                    with transaction.atomic():
                        for student, status in attendance_rows:
                            StudentAttendance.objects.update_or_create(
                                school=school,
                                academic_session=current_session,
                                school_class=school_class,
                                section=section,
                                student=student,
                                date=today,
                                defaults={'status': status}
                            )
                    return redirect('teacher_dashboard')

    return render(request, 'attendance/mark_attendance.html', {
        'classes': classes,
        'sections': sections,
        'students': students,
        'selected_class': selected_class,
        'selected_section': selected_section,
        'error': error,
    })


@login_required
@role_required('teacher')
def monthly_report(request):

    school = request.user.school

    classes = SchoolClass.objects.filter(school=school)
    sections = Section.objects.filter(school_class__school=school)

    selected_class = request.GET.get('class')
    selected_section = request.GET.get('section')
    selected_month = request.GET.get('month')

    report_data = []

    if selected_class and selected_section and selected_month:

        students = Student.objects.filter(
            school=school,
            school_class_id=selected_class,
            section_id=selected_section
        )

        for student in students:

            total_days = StudentAttendance.objects.filter(
                student=student,
                date__month=int(selected_month)
            ).count()

            present_days = StudentAttendance.objects.filter(
                student=student,
                date__month=int(selected_month),
                status='present'
            ).count()

            percentage = 0
            if total_days > 0:
                percentage = round((present_days / total_days) * 100, 2)

            report_data.append({
                'student': student,
                'present_days': present_days,
                'total_days': total_days,
                'percentage': percentage
            })

    return render(request, 'attendance/monthly_report.html', {
        'classes': classes,
        'sections': sections,
        'report_data': report_data,
        'selected_class': selected_class,
        'selected_section': selected_section,
        'selected_month': selected_month,
    })
