from functools import wraps

from django.shortcuts import redirect, render


def _normalize_roles(allowed_roles):
    if isinstance(allowed_roles, str):
        return {allowed_roles}
    return set(allowed_roles)


def role_required(allowed_roles):
    normalized_roles = _normalize_roles(allowed_roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if request.user.role not in normalized_roles:
                return render(request, 'reports/forbidden.html', status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
