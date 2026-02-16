from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from apps.core.users.audit import log_audit_event


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    log_audit_event(
        request=request,
        action='user.login',
        school=getattr(user, 'school', None),
        target=user,
        details=f"Role={user.role}",
    )


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is None:
        return

    log_audit_event(
        request=request,
        action='user.logout',
        school=getattr(user, 'school', None),
        target=user,
        details=f"Role={user.role}",
    )
