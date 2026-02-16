from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.users.decorators import role_required
from .models import GradeScale, Student, StudentEnrollment, StudentMark
from .forms import GradeScaleForm, StudentForm
from django.db.models import Sum
from django.db import transaction
from apps.core.academic_sessions.models import AcademicSession
from apps.core.users.audit import log_audit_event


def _sync_student_enrollment(student):
    if not student.academic_session or not student.school_class or not student.section:
        return

    StudentEnrollment.objects.update_or_create(
        student=student,
        academic_session=student.academic_session,
        defaults={
            'school_class': student.school_class,
            'section': student.section,
            'status': 'active',
        }
    )


def _allowed_parent_users(school):
    user_model = get_user_model()
    return user_model.objects.filter(
        school=school,
        role='parent'
    ).order_by('first_name', 'username')


def _grade_for_percentage(school, percentage):
    grade = GradeScale.objects.filter(
        school=school,
        min_percentage__lte=percentage,
        max_percentage__gte=percentage
    ).order_by('-min_percentage').first()
    return grade.grade_name if grade else '-'


@login_required
@role_required('schooladmin')
def student_list(request):
    students = Student.objects.filter(school=request.user.school)
    return render(request, 'students/student_list.html', {'students': students})


@login_required
@role_required('schooladmin')
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        form.fields['school_class'].queryset = SchoolClass.objects.filter(
            school=request.user.school
        )
        form.fields['section'].queryset = Section.objects.filter(
            school_class__school=request.user.school
        )
        form.fields['academic_session'].queryset = AcademicSession.objects.filter(
            school=request.user.school
        )
        form.fields['parent_user'].queryset = _allowed_parent_users(request.user.school)
        if form.is_valid():
            with transaction.atomic():
                student = form.save(commit=False)
                student.school = request.user.school
                student.save()
                _sync_student_enrollment(student)
            return redirect('student_list')
    else:
        form = StudentForm()

        form.fields['school_class'].queryset = SchoolClass.objects.filter(
            school=request.user.school
        )
        form.fields['section'].queryset = Section.objects.filter(
            school_class__school=request.user.school
        )
        form.fields['academic_session'].queryset = AcademicSession.objects.filter(
            school=request.user.school
        )
        form.fields['parent_user'].queryset = _allowed_parent_users(request.user.school)

    return render(request, 'students/student_form.html', {'form': form})

@login_required
@role_required('schooladmin')
def student_detail(request, pk):
    student = get_object_or_404(
        Student,
        pk=pk,
        school=request.user.school
    )
    return render(request, 'students/student_detail.html', {
        'student': student
    })


@login_required
@role_required('schooladmin')
def student_update(request, pk):
    student = get_object_or_404(
        Student,
        pk=pk,
        school=request.user.school
    )

    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        form.fields['school_class'].queryset = SchoolClass.objects.filter(
            school=request.user.school
        )
        form.fields['section'].queryset = Section.objects.filter(
            school_class__school=request.user.school
        )
        form.fields['academic_session'].queryset = AcademicSession.objects.filter(
            school=request.user.school
        )
        form.fields['parent_user'].queryset = _allowed_parent_users(request.user.school)
        if form.is_valid():
            with transaction.atomic():
                student = form.save()
                _sync_student_enrollment(student)
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)

        form.fields['school_class'].queryset = SchoolClass.objects.filter(
            school=request.user.school
        )
        form.fields['section'].queryset = Section.objects.filter(
            school_class__school=request.user.school
        )
        form.fields['academic_session'].queryset = AcademicSession.objects.filter(
            school=request.user.school
        )
        form.fields['parent_user'].queryset = _allowed_parent_users(request.user.school)
    return render(request, 'students/student_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def student_delete(request, pk):
    student = get_object_or_404(
        Student,
        pk=pk,
        school=request.user.school
    )

    if request.method == 'POST':
        student.delete()
        return redirect('student_list')

    return render(request, 'students/student_delete.html', {
        'student': student
    })


@login_required
@role_required('teacher')
def add_marks(request):
    school = request.user.school
    students = Student.objects.filter(school=school)
    subject_map = {}
    for student in students:
        subjects = Subject.objects.filter(
            school=school,
            school_class=student.school_class
        ).values_list('name', flat=True)
        subject_map[student.id] = list(subjects)

    if request.method == 'POST':
        student_id = request.POST.get('student')
        subject = request.POST.get('subject')
        marks = request.POST.get('marks')
        total = request.POST.get('total')
        exam = request.POST.get('exam')

        student = get_object_or_404(
            Student,
            id=student_id,
            school=school
        )

        if subject not in subject_map.get(student.id, []):
            return render(request, 'students/add_marks.html', {
                'students': students,
                'subject_map': subject_map,
                'error': 'Please select a valid subject for the selected class.',
            })

        StudentMark.objects.create(
            school=school,
            student=student,
            subject=subject,
            marks_obtained=marks,
            total_marks=total,
            exam_type=exam
        )

        return redirect('add_marks')

    return render(request, 'students/add_marks.html', {
        'students': students,
        'subject_map': subject_map,
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def student_report(request, student_id):

    student = get_object_or_404(
        Student,
        id=student_id,
        school=request.user.school
    )

    marks = StudentMark.objects.filter(student=student)

    total_obtained = marks.aggregate(total=Sum('marks_obtained'))['total'] or 0
    total_max = marks.aggregate(total=Sum('total_marks'))['total'] or 0

    percentage = 0
    if total_max > 0:
        percentage = round((total_obtained / total_max) * 100, 2)

    status = "PASS" if percentage >= 40 else "FAIL"

    return render(request, 'students/student_report.html', {
        'student': student,
        'marks': marks,
        'total_obtained': total_obtained,
        'total_max': total_max,
        'percentage': percentage,
        'status': status,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'parent'])
def exam_report_card(request, student_id):
    user = request.user
    student_queryset = Student.objects.filter(id=student_id)

    if user.role == 'parent':
        student_queryset = student_queryset.filter(parent_user=user)
    else:
        student_queryset = student_queryset.filter(school=user.school)

    student = get_object_or_404(student_queryset)

    marks_queryset = StudentMark.objects.filter(
        school=student.school,
        student=student
    )
    exam_types = marks_queryset.values_list('exam_type', flat=True).distinct().order_by('exam_type')

    selected_exam = request.GET.get('exam', '')
    if selected_exam:
        marks_queryset = marks_queryset.filter(exam_type=selected_exam)

    marks_data = []
    total_obtained = 0
    total_max = 0
    for mark in marks_queryset:
        percentage = mark.percentage()
        grade = _grade_for_percentage(student.school, percentage)
        marks_data.append({
            'subject': mark.subject,
            'marks_obtained': mark.marks_obtained,
            'total_marks': mark.total_marks,
            'percentage': percentage,
            'grade': grade,
            'exam_type': mark.exam_type,
        })
        total_obtained += mark.marks_obtained
        total_max += mark.total_marks

    overall_percentage = round((total_obtained / total_max) * 100, 2) if total_max > 0 else 0
    overall_grade = _grade_for_percentage(student.school, overall_percentage)
    status = "PASS" if overall_percentage >= 40 else "FAIL"

    return render(request, 'students/exam_report_card.html', {
        'student': student,
        'exam_types': exam_types,
        'selected_exam': selected_exam,
        'marks_data': marks_data,
        'total_obtained': total_obtained,
        'total_max': total_max,
        'overall_percentage': overall_percentage,
        'overall_grade': overall_grade,
        'status': status,
    })


@login_required
@role_required('schooladmin')
def grade_scale_list(request):
    grade_scales = GradeScale.objects.filter(
        school=request.user.school
    ).order_by('-min_percentage')
    return render(request, 'students/grade_scale_list.html', {
        'grade_scales': grade_scales
    })


@login_required
@role_required('schooladmin')
def grade_scale_create(request):
    if request.method == 'POST':
        form = GradeScaleForm(request.POST)
        if form.is_valid():
            grade_scale = form.save(commit=False)
            grade_scale.school = request.user.school
            grade_scale.save()
            return redirect('grade_scale_list')
    else:
        form = GradeScaleForm()

    return render(request, 'students/grade_scale_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def grade_scale_update(request, pk):
    grade_scale = get_object_or_404(
        GradeScale,
        pk=pk,
        school=request.user.school
    )

    if request.method == 'POST':
        form = GradeScaleForm(request.POST, instance=grade_scale)
        if form.is_valid():
            form.save()
            return redirect('grade_scale_list')
    else:
        form = GradeScaleForm(instance=grade_scale)

    return render(request, 'students/grade_scale_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def grade_scale_delete(request, pk):
    grade_scale = get_object_or_404(
        GradeScale,
        pk=pk,
        school=request.user.school
    )
    grade_scale.delete()
    return redirect('grade_scale_list')


@login_required
@role_required('schooladmin')
def enrollment_history(request, pk):
    student = get_object_or_404(
        Student,
        pk=pk,
        school=request.user.school
    )
    enrollments = StudentEnrollment.objects.filter(
        student=student
    ).select_related('academic_session', 'school_class', 'section').order_by('-academic_session__start_date')
    return render(request, 'students/enrollment_history.html', {
        'student': student,
        'enrollments': enrollments,
    })


@login_required
@role_required('schooladmin')
def enrollment_status_update(request, enrollment_id):
    enrollment = get_object_or_404(
        StudentEnrollment,
        pk=enrollment_id,
        student__school=request.user.school
    )

    if request.method == 'POST':
        new_status = request.POST.get('status')
        allowed_status = {'active', 'passed', 'left'}
        if new_status in allowed_status:
            enrollment.status = new_status
            enrollment.save(update_fields=['status'])

            log_audit_event(
                request=request,
                action='enrollment.status_updated',
                school=request.user.school,
                target=enrollment,
                details=f"Student={enrollment.student_id}, Status={new_status}",
            )

    return redirect('enrollment_history', pk=enrollment.student_id)
