from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import ExtractMonth
from django.shortcuts import redirect, render

from apps.academics.staff.models import Staff
from apps.core.users.decorators import role_required

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.academics.students.models import Student
from apps.finance.fees.models import FeePayment
from apps.core.users.audit import log_audit_event
from .forms import SchoolOnboardingForm
from .models import School


@login_required
@role_required('schooladmin')
def school_admin_dashboard(request):

    school = request.user.school

    # Basic Counts
    total_students = Student.objects.for_school(school).count()
    total_teachers = Staff.objects.for_school(school).filter(staff_type='teacher').count()
    total_classes = SchoolClass.objects.filter(school=school).count()
    total_sections = Section.objects.filter(
        school_class__school=school
    ).count()

    # Monthly Fee Collection and Student Trend
    monthly_data = (
        FeePayment.objects
        .filter(school=school)
        .annotate(month=ExtractMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )

    student_monthly_data = (
        Student.objects.for_school(school)
        .annotate(month=ExtractMonth('created_at'))
        .values('month')
        .annotate(total=Count('id'))
        .order_by('month')
    )

    months = list(range(1, 13))
    monthly_collection = {item['month']: float(item['total']) for item in monthly_data}
    student_data = {item['month']: item['total'] for item in student_monthly_data}
    fee_data = [monthly_collection.get(m, 0) for m in months]

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_classes': total_classes,
        'total_sections': total_sections,
        'months': months,
        'student_data': [student_data.get(m, 0) for m in months],
        'fee_data': fee_data,
    }

    return render(request, 'schools/school_admin_dashboard.html', context)


@login_required
@role_required('superadmin')
def school_list(request):
    schools = School.objects.all().order_by('name')
    return render(request, 'schools/school_list.html', {'schools': schools})


@login_required
@role_required('superadmin')
def school_onboard(request):
    if request.method == 'POST':
        form = SchoolOnboardingForm(request.POST)
        if form.is_valid():
            user_model = get_user_model()

            with transaction.atomic():
                school = School.objects.create(
                    name=form.cleaned_data['school_name'],
                    address=form.cleaned_data['school_address'],
                    phone=form.cleaned_data['school_phone'],
                    email=form.cleaned_data['school_email'],
                )

                session = AcademicSession.objects.create(
                    school=school,
                    name=form.cleaned_data['session_name'],
                    start_date=form.cleaned_data['session_start_date'],
                    end_date=form.cleaned_data['session_end_date'],
                    is_active=True,
                )

                school.current_session = session
                school.save(update_fields=['current_session'])

                admin_user = user_model.objects.create_user(
                    username=form.cleaned_data['admin_username'],
                    email=form.cleaned_data['admin_email'],
                    password=form.cleaned_data['admin_password'],
                    role='schooladmin',
                    school=school,
                )

            log_audit_event(
                request=request,
                action='school.onboarded',
                school=school,
                target=school,
                details=f"School admin created: {admin_user.username}",
            )
            messages.success(request, 'School onboarded successfully.')
            return redirect('school_list')
    else:
        form = SchoolOnboardingForm()

    return render(request, 'schools/school_onboard.html', {'form': form})
