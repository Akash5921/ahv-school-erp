from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.attendance.models import StudentAttendance
from apps.core.exams.models import Exam
from apps.core.hr.models import LeaveRequest, Payroll

from .models import Announcement
from .services import (
    trigger_announcement_notifications,
    trigger_exam_result_published_notifications,
    trigger_leave_decision_notifications,
    trigger_payroll_processed_notifications,
    trigger_student_absent_notifications,
)


def _safe_on_commit(func, **kwargs):
    def _runner():
        try:
            func(**kwargs)
        except Exception:
            # Communication events must not block core workflows.
            pass

    transaction.on_commit(_runner)


@receiver(post_save, sender=Announcement)
def communication_announcement_created(sender, instance: Announcement, created, **kwargs):
    if not created:
        return
    if not instance.is_active or instance.is_expired:
        return
    _safe_on_commit(trigger_announcement_notifications, announcement=instance)


@receiver(pre_save, sender=StudentAttendance)
def communication_capture_previous_attendance_status(sender, instance: StudentAttendance, **kwargs):
    if not instance.pk:
        instance._communication_previous_status = None
        return
    previous = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    instance._communication_previous_status = previous


@receiver(post_save, sender=StudentAttendance)
def communication_student_absent_alert(sender, instance: StudentAttendance, created, **kwargs):
    if instance.status != StudentAttendance.STATUS_ABSENT:
        return

    previous_status = getattr(instance, '_communication_previous_status', None)
    if not created and previous_status == StudentAttendance.STATUS_ABSENT:
        return

    _safe_on_commit(trigger_student_absent_notifications, attendance=instance)


@receiver(pre_save, sender=LeaveRequest)
def communication_capture_previous_leave_status(sender, instance: LeaveRequest, **kwargs):
    if not instance.pk:
        instance._communication_previous_status = None
        return
    previous = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    instance._communication_previous_status = previous


@receiver(post_save, sender=LeaveRequest)
def communication_leave_decision_alert(sender, instance: LeaveRequest, created, **kwargs):
    if instance.status not in {LeaveRequest.STATUS_APPROVED, LeaveRequest.STATUS_REJECTED}:
        return

    previous_status = getattr(instance, '_communication_previous_status', None)
    if not created and previous_status == instance.status:
        return

    _safe_on_commit(trigger_leave_decision_notifications, leave_request=instance)


@receiver(pre_save, sender=Exam)
def communication_capture_previous_exam_lock(sender, instance: Exam, **kwargs):
    if not instance.pk:
        instance._communication_previous_locked = False
        return
    previous = sender.objects.filter(pk=instance.pk).values_list('is_locked', flat=True).first()
    instance._communication_previous_locked = bool(previous)


@receiver(post_save, sender=Exam)
def communication_exam_locked_alert(sender, instance: Exam, created, **kwargs):
    if not instance.is_locked:
        return

    previous_locked = getattr(instance, '_communication_previous_locked', False)
    if not created and previous_locked:
        return

    _safe_on_commit(trigger_exam_result_published_notifications, exam=instance)


@receiver(post_save, sender=Payroll)
def communication_payroll_processed_alert(sender, instance: Payroll, created, **kwargs):
    if not created:
        return
    _safe_on_commit(trigger_payroll_processed_notifications, payroll=instance)
