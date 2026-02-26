from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.core.users.decorators import role_required


@login_required
def role_redirect(request):
    role = request.user.role

    if role == 'superadmin':
        return redirect('school_list')
    if role == 'schooladmin':
        return redirect('school_dashboard')

    # Non-admin role workspaces are intentionally minimal in Phase 0.
    return redirect('role_workspace')


@login_required
@role_required(['teacher', 'accountant', 'parent', 'staff'])
def role_workspace(request):
    return render(request, 'users/role_workspace.html', {
        'role': request.user.role,
    })
