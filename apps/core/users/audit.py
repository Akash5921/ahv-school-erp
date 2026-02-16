from apps.core.users.models import AuditLog


def _extract_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit_event(request, action, school=None, target=None, details=''):
    try:
        target_model = ''
        target_id = ''

        if target is not None:
            target_model = target.__class__.__name__
            target_id = str(getattr(target, 'pk', ''))

        user = request.user if request.user.is_authenticated else None

        AuditLog.objects.create(
            school=school or getattr(user, 'school', None),
            user=user,
            action=action,
            target_model=target_model,
            target_id=target_id,
            details=details,
            method=request.method,
            path=request.path,
            ip_address=_extract_ip(request),
        )
    except Exception:
        # Logging must never break business actions.
        pass
