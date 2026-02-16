from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


@login_required
def role_redirect(request):

    role = request.user.role

    if role == 'superadmin':
        return redirect('/admin/')

    elif role == 'schooladmin':
        return redirect('/schools/school-dashboard/')

    elif role == 'teacher':
        return redirect('/teacher/dashboard/')

    elif role == 'accountant':
        return redirect('/accounts/accountant/dashboard/')

    else:
        return redirect('/login/')
