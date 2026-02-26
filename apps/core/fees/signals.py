from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.academic_sessions.models import AcademicSession
from apps.core.students.models import Student

from .services import sync_student_fees_for_student


def _safe_sync(student_id, previous_session_id=None):
    student = Student.objects.select_related('school', 'session', 'current_class').filter(
        pk=student_id,
        is_archived=False,
    ).first()
    if not student:
        return

    previous_session = None
    if previous_session_id:
        previous_session = AcademicSession.objects.filter(
            pk=previous_session_id,
            school=student.school,
        ).first()

    try:
        sync_student_fees_for_student(student=student, previous_session=previous_session)
    except Exception:
        # Fee sync should not block student save operations.
        pass


@receiver(pre_save, sender=Student)
def capture_previous_student_session(sender, instance: Student, **kwargs):
    if not instance.pk:
        instance._fees_previous_session_id = None
        return

    previous = sender.objects.filter(pk=instance.pk).values('session_id').first()
    instance._fees_previous_session_id = previous['session_id'] if previous else None


@receiver(post_save, sender=Student)
def sync_student_fees_after_student_save(sender, instance: Student, **kwargs):
    if not instance.school_id or not instance.session_id:
        return

    previous_session_id = getattr(instance, '_fees_previous_session_id', None)
    if previous_session_id == instance.session_id:
        previous_session_id = None

    transaction.on_commit(lambda: _safe_sync(instance.id, previous_session_id=previous_session_id))
