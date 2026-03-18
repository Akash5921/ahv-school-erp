from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.core.communication.models import Message, Notification
from apps.core.communication.services import visible_announcements_for_user
from apps.core.users.decorators import role_required


@login_required
def role_redirect(request):
    role = request.user.role

    if role == 'superadmin':
        return redirect('dashboard_super_admin')
    if role == 'schooladmin':
        return redirect('school_dashboard')
    if role == 'principal':
        return redirect('dashboard_principal')
    if role == 'accountant':
        return redirect('dashboard_accountant')
    if role == 'teacher':
        return redirect('dashboard_teacher')
    if role == 'parent':
        return redirect('dashboard_parent')

    return redirect('role_workspace')


@login_required
@role_required(['teacher', 'accountant', 'parent', 'staff', 'principal'])
def role_workspace(request):
    school = request.user.school
    current_session = getattr(school, 'current_session', None)
    announcements = visible_announcements_for_user(user=request.user, session=current_session)[:5]
    unread_notifications = Notification.objects.filter(
        school=school,
        user=request.user,
        is_read=False,
    ).count()
    unread_messages = Message.objects.filter(
        thread__school=school,
        receiver=request.user,
        is_read=False,
    ).count()

    return render(request, 'users/role_workspace.html', {
        'role': request.user.role,
        'announcements': announcements,
        'unread_notifications': unread_notifications,
        'unread_messages': unread_messages,
    })
