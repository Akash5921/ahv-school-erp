from django.db import transaction

from apps.core.academic_sessions.models import AcademicSession


def activate_session(*, school, session):
    if session.school_id != school.id:
        raise ValueError('Session does not belong to the provided school.')

    with transaction.atomic():
        AcademicSession.objects.filter(
            school=school,
            is_active=True,
        ).exclude(pk=session.pk).update(is_active=False)

        if not session.is_active:
            session.is_active = True
            session.save(update_fields=['is_active'])

        if school.current_session_id != session.id:
            school.current_session = session
            school.save(update_fields=['current_session'])

    return session
