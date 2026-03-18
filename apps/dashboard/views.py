from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.users.decorators import role_required

from .services import (
    build_accountant_dashboard_context,
    build_parent_dashboard_context,
    build_principal_dashboard_context,
    build_super_admin_dashboard_context,
    build_teacher_dashboard_context,
)


@login_required
@role_required('superadmin')
def dashboard_super_admin(request):
    return render(request, 'dashboard/super_admin_dashboard.html', build_super_admin_dashboard_context(request.user))


@login_required
@role_required('principal')
def dashboard_principal(request):
    return render(request, 'dashboard/school_role_dashboard.html', build_principal_dashboard_context(request.user))


@login_required
@role_required('accountant')
def dashboard_accountant(request):
    return render(request, 'dashboard/school_role_dashboard.html', build_accountant_dashboard_context(request.user))


@login_required
@role_required('teacher')
def dashboard_teacher(request):
    return render(request, 'dashboard/teacher_dashboard.html', build_teacher_dashboard_context(request.user))


@login_required
@role_required('parent')
def dashboard_parent(request):
    return render(request, 'dashboard/parent_dashboard.html', build_parent_dashboard_context(request.user))
