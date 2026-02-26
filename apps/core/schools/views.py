from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect, render

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academic_sessions.services import activate_session
from apps.core.academics.models import AcademicConfig, ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required
from apps.core.users.models import AuditLog

from .forms import SchoolOnboardingForm
from .models import School, SchoolDomain


@login_required
@role_required('schooladmin')
def school_admin_dashboard(request):
    school = request.user.school
    user_model = get_user_model()

    users_queryset = user_model.objects.filter(school=school)
    users_by_role = users_queryset.values('role').annotate(total=Count('id')).order_by('role')

    role_counts = {row['role']: row['total'] for row in users_by_role}
    sessions = AcademicSession.objects.filter(school=school).order_by('-start_date')
    domains = SchoolDomain.objects.filter(school=school).order_by('-is_primary', 'domain')
    current_session = school.current_session

    class_count = 0
    section_count = 0
    mapping_count = 0
    period_count = 0
    has_config = False
    if current_session:
        class_count = SchoolClass.objects.filter(school=school, session=current_session, is_active=True).count()
        section_count = Section.objects.filter(
            school_class__school=school,
            school_class__session=current_session,
            is_active=True,
        ).count()
        mapping_count = ClassSubject.objects.filter(school_class__school=school, school_class__session=current_session).count()
        period_count = Period.objects.filter(school=school, session=current_session, is_active=True).count()
        has_config = AcademicConfig.objects.filter(school=school, session=current_session).exists()

    return render(request, 'schools/school_admin_dashboard.html', {
        'school': school,
        'total_users': users_queryset.count(),
        'active_users': users_queryset.filter(is_active=True).count(),
        'total_subjects': Subject.objects.filter(school=school, is_active=True).count(),
        'class_count': class_count,
        'section_count': section_count,
        'mapping_count': mapping_count,
        'period_count': period_count,
        'has_config': has_config,
        'role_counts': role_counts,
        'total_sessions': sessions.count(),
        'active_session': current_session,
        'domains': domains,
        'recent_logs': AuditLog.objects.filter(school=school).select_related('user')[:8],
    })


@login_required
@role_required('superadmin')
def school_list(request):
    schools = School.objects.select_related('current_session').prefetch_related('domains').annotate(
        total_users=Count('users', distinct=True),
        total_sessions=Count('academic_sessions', distinct=True),
    ).order_by('name')
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
                    code=form.cleaned_data['school_code'],
                    subdomain=form.cleaned_data['school_subdomain'] or None,
                    timezone=form.cleaned_data['school_timezone'] or 'UTC',
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
                activate_session(school=school, session=session)

                admin_user = user_model.objects.create_user(
                    username=form.cleaned_data['admin_username'],
                    email=form.cleaned_data['admin_email'],
                    password=form.cleaned_data['admin_password'],
                    role='schooladmin',
                    school=school,
                )

                if form.cleaned_data['school_domain']:
                    SchoolDomain.objects.create(
                        school=school,
                        domain=form.cleaned_data['school_domain'],
                        is_primary=True,
                        is_active=True,
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
