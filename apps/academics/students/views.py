from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.academics.models import SchoolClass, Section
from apps.core.users.decorators import role_required
from .models import Student, StudentMark
from .forms import StudentForm
from django.db.models import Sum


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
        if form.is_valid():
            student = form.save(commit=False)
            student.school = request.user.school
            student.save()
            return redirect('student_list')
    else:
        form = StudentForm()

        form.fields['school_class'].queryset = SchoolClass.objects.filter(
            school=request.user.school
        )
        form.fields['section'].queryset = Section.objects.filter(
            school_class__school=request.user.school
        )

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
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)

        form.fields['school_class'].queryset = SchoolClass.objects.filter(
            school=request.user.school
        )
        form.fields['section'].queryset = Section.objects.filter(
            school_class__school=request.user.school
        )
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

    if request.method == 'POST':
        student_id = request.POST.get('student')
        subject = request.POST.get('subject')
        marks = request.POST.get('marks')
        total = request.POST.get('total')
        exam = request.POST.get('exam')

        student = Student.objects.get(id=student_id)

        StudentMark.objects.create(
            school=request.user.school,
            student=student,
            subject=subject,
            marks_obtained=marks,
            total_marks=total,
            exam_type=exam
        )

        return redirect('add_marks')

    students = Student.objects.filter(school=request.user.school)

    return render(request, 'students/add_marks.html', {
        'students': students
    })


@login_required
@role_required(['schooladmin', 'teacher'])
def student_report(request, student_id):

    student = Student.objects.get(id=student_id, school=request.user.school)

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
