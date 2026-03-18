from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from urllib import error as url_error
from urllib import request as url_request

from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.utils import timezone

from apps.core.hr.models import ClassTeacher, Staff, TeacherSubjectAssignment
from apps.core.students.models import Student
from apps.core.users.models import User

from .models import (
    Announcement,
    EmailLog,
    GlobalSettings,
    Message,
    MessageThread,
    MessageThreadParticipant,
    Notification,
    ParentStudentLink,
    ParentUser,
    SMSLog,
)


PHONE_RE = re.compile(r'^\+?[0-9]{10,15}$')


def _resolve_session(school, session=None):
    resolved = session or school.current_session
    if resolved and resolved.school_id != school.id:
        raise ValidationError('Session does not belong to selected school.')
    return resolved


def _event_key(key):
    return (key or '').strip()[:150]


def _is_expired(ts):
    return bool(ts and ts <= timezone.now())


def _parent_users_for_student(student):
    links = ParentStudentLink.objects.filter(
        student=student,
        parent_user__is_active=True,
    ).select_related('parent_user', 'parent_user__user', 'parent_user__parent_info')
    return [link.parent_user for link in links]


def _parent_contacts(parent_user):
    emails = set()
    phones = set()
    if parent_user.user.email:
        emails.add(parent_user.user.email.strip())
    if parent_user.parent_info_id:
        if parent_user.parent_info.email:
            emails.add(parent_user.parent_info.email.strip())
        if parent_user.parent_info.phone:
            phones.add(parent_user.parent_info.phone.strip())
    return sorted(email for email in emails if email), sorted(phone for phone in phones if phone)


def _normalize_phone_number(number):
    raw = (number or '').strip()
    normalized = ''.join(ch for ch in raw if ch.isdigit() or ch == '+')
    if not PHONE_RE.match(normalized):
        raise ValidationError('Recipient number must be a valid phone number.')
    if normalized.startswith('+'):
        return f"+{normalized[1:]}"
    return normalized


def _announcement_targets_parent_user(*, announcement, user):
    links = ParentStudentLink.objects.filter(
        parent_user__user=user,
        parent_user__is_active=True,
        student__school_id=announcement.school_id,
        student__session_id=announcement.session_id,
    )
    if announcement.school_class_id:
        links = links.filter(student__current_class_id=announcement.school_class_id)
    if announcement.section_id:
        links = links.filter(student__current_section_id=announcement.section_id)
    return links.exists()


def _announcement_targets_staff_user(*, announcement, user):
    staff = Staff.objects.filter(
        user=user,
        school_id=announcement.school_id,
        is_active=True,
    ).first()
    if not staff:
        return False

    class_teacher_qs = ClassTeacher.objects.filter(
        school_id=announcement.school_id,
        session_id=announcement.session_id,
        school_class_id=announcement.school_class_id,
        teacher=staff,
        is_active=True,
    )
    if announcement.section_id:
        class_teacher_qs = class_teacher_qs.filter(section_id=announcement.section_id)

    if class_teacher_qs.exists():
        return True

    return TeacherSubjectAssignment.objects.filter(
        school_id=announcement.school_id,
        session_id=announcement.session_id,
        school_class_id=announcement.school_class_id,
        teacher=staff,
        is_active=True,
    ).exists()


def _announcement_targets_user(announcement, user):
    if not announcement.is_active or _is_expired(announcement.expires_at):
        return False

    if announcement.target_role == Announcement.ROLE_ALL:
        target_match = True
    elif announcement.target_role == Announcement.ROLE_STUDENT:
        # Student-role announcements are delivered to linked parent portal users.
        target_match = user.role == 'parent'
    else:
        target_match = announcement.target_role == user.role

    if not target_match:
        return False

    if not announcement.school_class_id:
        return True

    if user.role == 'parent':
        return _announcement_targets_parent_user(announcement=announcement, user=user)

    if user.role in {'teacher', 'staff'}:
        return _announcement_targets_staff_user(announcement=announcement, user=user)

    return True


def visible_announcements_for_user(*, user, session=None):
    if not user.school_id:
        return Announcement.objects.none()

    session = _resolve_session(user.school, session)
    queryset = Announcement.objects.filter(
        school=user.school,
        is_active=True,
    ).order_by('-created_at')

    if session:
        queryset = queryset.filter(session=session)

    return [row for row in queryset if _announcement_targets_user(row, user)]


def _users_for_announcement(announcement: Announcement):
    school = announcement.school
    role = announcement.target_role

    if role in {Announcement.ROLE_PARENT, Announcement.ROLE_STUDENT}:
        links = ParentStudentLink.objects.filter(
            parent_user__school=school,
            parent_user__is_active=True,
            student__session=announcement.session,
            student__school=school,
        ).select_related('parent_user__user')

        if announcement.school_class_id:
            links = links.filter(student__current_class_id=announcement.school_class_id)
        if announcement.section_id:
            links = links.filter(student__current_section_id=announcement.section_id)

        users = []
        seen = set()
        for link in links:
            if link.parent_user.user_id in seen:
                continue
            seen.add(link.parent_user.user_id)
            users.append(link.parent_user.user)
        return users

    users = User.objects.filter(school=school).exclude(role='superadmin')
    if role != Announcement.ROLE_ALL:
        users = users.filter(role=role)
    return list(users.order_by('username'))


def _teacher_linked_to_parent(*, teacher_user, parent_user):
    teacher_staff = Staff.objects.filter(
        school=teacher_user.school,
        user=teacher_user,
        is_active=True,
    ).first()
    if not teacher_staff:
        return False

    linked_students = Student.objects.filter(
        parent_links__parent_user__user=parent_user,
        parent_links__parent_user__is_active=True,
        school=teacher_user.school,
        is_active=True,
        is_archived=False,
    ).values_list('current_class_id', 'current_section_id', 'session_id')

    for class_id, section_id, session_id in linked_students:
        if not class_id or not session_id:
            continue

        if ClassTeacher.objects.filter(
            school=teacher_user.school,
            session_id=session_id,
            school_class_id=class_id,
            section_id=section_id,
            teacher=teacher_staff,
            is_active=True,
        ).exists():
            return True

        if TeacherSubjectAssignment.objects.filter(
            school=teacher_user.school,
            session_id=session_id,
            school_class_id=class_id,
            teacher=teacher_staff,
            is_active=True,
        ).exists():
            return True

    return False


def can_user_message(*, sender, receiver):
    if not sender.school_id or sender.school_id != receiver.school_id:
        return False
    if sender.id == receiver.id:
        return False
    if sender.role == 'superadmin' or receiver.role == 'superadmin':
        return False

    if sender.role == 'schooladmin' or receiver.role == 'schooladmin':
        return True

    parent_pair = {'parent', 'teacher'} == {sender.role, receiver.role}
    if parent_pair:
        teacher_user = sender if sender.role == 'teacher' else receiver
        parent_user = sender if sender.role == 'parent' else receiver
        return _teacher_linked_to_parent(teacher_user=teacher_user, parent_user=parent_user)

    if sender.role == 'parent' or receiver.role == 'parent':
        return False

    return False


def ensure_email_channel_ready(*, school):
    config = getattr(school, 'communication_settings', None)
    if not config:
        raise ValidationError('Communication settings are not configured for this school.')
    config.full_clean()
    if not config.email_enabled:
        raise ValidationError('Email channel is disabled.')
    return config


def ensure_sms_channel_ready(*, school):
    config = getattr(school, 'communication_settings', None)
    if not config:
        raise ValidationError('Communication settings are not configured for this school.')
    config.full_clean()
    if not config.sms_enabled:
        raise ValidationError('SMS channel is disabled.')
    return config


@transaction.atomic
def create_message_thread(*, school, session, subject, created_by, initial_receiver, message_text='', attachment=None):
    if created_by.school_id != school.id or initial_receiver.school_id != school.id:
        raise ValidationError('Users must belong to selected school.')
    if session and session.school_id != school.id:
        raise ValidationError('Session must belong to selected school.')
    if not can_user_message(sender=created_by, receiver=initial_receiver):
        raise ValidationError('Messaging permission denied for selected users.')

    thread = MessageThread(
        school=school,
        session=session,
        subject=subject,
        created_by=created_by,
    )
    thread.full_clean()
    thread.save()

    MessageThreadParticipant.objects.bulk_create([
        MessageThreadParticipant(thread=thread, user=created_by),
        MessageThreadParticipant(thread=thread, user=initial_receiver),
    ])

    if message_text or attachment:
        send_message(
            thread=thread,
            sender=created_by,
            receiver=initial_receiver,
            message_text=message_text,
            attachment=attachment,
        )
    return thread


@transaction.atomic
def send_message(*, thread, sender, receiver, message_text='', attachment=None):
    if sender.school_id != thread.school_id or receiver.school_id != thread.school_id:
        raise ValidationError('Sender and receiver must belong to thread school.')
    if not can_user_message(sender=sender, receiver=receiver):
        raise ValidationError('Messaging permission denied for selected users.')

    participant_ids = set(thread.thread_participants.values_list('user_id', flat=True))
    if sender.id not in participant_ids or receiver.id not in participant_ids:
        raise ValidationError('Sender/receiver must be thread participants.')

    msg = Message(
        thread=thread,
        sender=sender,
        receiver=receiver,
        message_text=message_text,
        attachment=attachment,
    )
    msg.full_clean()
    msg.save()

    thread.updated_at = timezone.now()
    thread.save(update_fields=['updated_at'])

    MessageThreadParticipant.objects.filter(
        thread=thread,
        user=sender,
    ).update(last_read_at=timezone.now())
    return msg


@transaction.atomic
def mark_message_read(*, message, user):
    if message.receiver_id != user.id:
        raise ValidationError('Only receiver can mark message as read.')
    if message.is_read:
        return message

    message.is_read = True
    message.read_at = timezone.now()
    message.save(update_fields=['is_read', 'read_at'])

    MessageThreadParticipant.objects.filter(
        thread=message.thread,
        user=user,
    ).update(last_read_at=timezone.now())
    return message


@transaction.atomic
def edit_message(*, message, editor, message_text):
    if message.sender_id != editor.id:
        raise ValidationError('Only sender can edit message.')
    if message.is_read:
        raise ValidationError('Cannot edit a message after it is read.')

    message.message_text = (message_text or '').strip()
    if not message.message_text and not message.attachment:
        raise ValidationError('Message text or attachment is required.')

    message.edited_at = timezone.now()
    message.edited_by = editor
    message.full_clean()
    message.save(update_fields=['message_text', 'edited_at', 'edited_by'])
    return message


@transaction.atomic
def create_notification(*, user, title, message, school=None, session=None, related_model='', related_id='', event_key=''):
    school = school or user.school
    if not school or user.school_id != school.id:
        raise ValidationError('Notification user/school mismatch.')

    session = _resolve_session(school, session)
    key = _event_key(event_key)

    defaults = {
        'school': school,
        'session': session,
        'title': (title or '')[:150],
        'message': message or '',
        'related_model': (related_model or '')[:120],
        'related_id': str(related_id or '')[:64],
    }

    if key:
        notification, _ = Notification.objects.get_or_create(
            user=user,
            event_key=key,
            defaults=defaults,
        )
        return notification

    notification = Notification(
        user=user,
        event_key='',
        **defaults,
    )
    notification.full_clean()
    notification.save()
    return notification


@transaction.atomic
def mark_notification_read(*, notification, user):
    if notification.user_id != user.id:
        raise ValidationError('Cannot mark another user notification.')
    if notification.is_read:
        return notification

    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=['is_read', 'read_at'])
    return notification


def _smtp_connection(config: GlobalSettings):
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        fail_silently=False,
    )


def send_email_notification(
    *,
    school,
    session,
    recipient,
    subject,
    message,
    related_model='',
    related_id='',
    triggered_by=None,
):
    status = EmailLog.STATUS_FAILED
    error_message = ''

    try:
        config = ensure_email_channel_ready(school=school)
        if not recipient:
            raise ValidationError('Recipient email is required.')

        email = EmailMessage(
            subject=(subject or '')[:200],
            body=message or '',
            from_email=config.smtp_from_email,
            to=[recipient],
            connection=_smtp_connection(config),
        )
        email.send(fail_silently=False)
        status = EmailLog.STATUS_SENT
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)[:255]

    return EmailLog.objects.create(
        school=school,
        session=session,
        recipient=(recipient or '')[:254],
        subject=(subject or '')[:200],
        body=message or '',
        status=status,
        error_message=error_message,
        related_model=(related_model or '')[:120],
        related_id=str(related_id or '')[:64],
        triggered_by=triggered_by,
    )


def send_sms_notification(
    *,
    school,
    session,
    recipient_number,
    message,
    related_model='',
    related_id='',
    triggered_by=None,
):
    status = SMSLog.STATUS_FAILED
    error_message = ''
    normalized_number = (recipient_number or '')[:20]

    try:
        config = ensure_sms_channel_ready(school=school)
        normalized_number = _normalize_phone_number(recipient_number)

        payload = json.dumps({
            'api_key': config.sms_api_key,
            'sender_id': config.sms_sender_id,
            'recipient': normalized_number,
            'message': message,
        }).encode('utf-8')
        req = url_request.Request(
            config.sms_api_url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with url_request.urlopen(req, timeout=10) as response:  # noqa: S310
            if response.status >= 400:
                raise ValidationError(f'SMS gateway returned {response.status}.')
        status = SMSLog.STATUS_SENT
    except (ValidationError, url_error.URLError, TimeoutError, Exception) as exc:  # noqa: BLE001
        error_message = str(exc)[:255]

    return SMSLog.objects.create(
        school=school,
        session=session,
        recipient_number=normalized_number[:20],
        message=message or '',
        status=status,
        error_message=error_message,
        related_model=(related_model or '')[:120],
        related_id=str(related_id or '')[:64],
        triggered_by=triggered_by,
    )


def notify_users(
    *,
    users,
    school,
    session,
    title,
    message,
    related_model='',
    related_id='',
    event_key_prefix='',
    send_email=False,
    send_sms=False,
    triggered_by=None,
):
    created = []
    seen = set()

    for user in users:
        if user.id in seen:
            continue
        seen.add(user.id)

        event_key = ''
        if event_key_prefix:
            event_key = f'{event_key_prefix}:{user.id}'

        notification = create_notification(
            user=user,
            school=school,
            session=session,
            title=title,
            message=message,
            related_model=related_model,
            related_id=related_id,
            event_key=event_key,
        )
        created.append(notification)

        if send_email:
            send_email_notification(
                school=school,
                session=session,
                recipient=user.email,
                subject=title,
                message=message,
                related_model=related_model,
                related_id=related_id,
                triggered_by=triggered_by,
            )

        if send_sms and user.role == 'parent':
            parent_profile = ParentUser.objects.filter(user=user, school=school, is_active=True).first()
            if parent_profile:
                _, phones = _parent_contacts(parent_profile)
                for phone in phones:
                    send_sms_notification(
                        school=school,
                        session=session,
                        recipient_number=phone,
                        message=message,
                        related_model=related_model,
                        related_id=related_id,
                        triggered_by=triggered_by,
                    )

    return created


def trigger_announcement_notifications(*, announcement: Announcement):
    users = _users_for_announcement(announcement)
    return notify_users(
        users=users,
        school=announcement.school,
        session=announcement.session,
        title=announcement.title,
        message=announcement.message,
        related_model='Announcement',
        related_id=announcement.id,
        event_key_prefix=f'announcement:{announcement.id}',
        send_email=False,
        send_sms=False,
        triggered_by=announcement.created_by,
    )


def trigger_student_absent_notifications(*, attendance):
    student = attendance.student
    parent_users = _parent_users_for_student(student)
    if not parent_users:
        return []

    title = 'Attendance Alert'
    message = (
        f"{student.full_name} ({student.admission_number}) was marked absent on "
        f"{attendance.date}."
    )
    return notify_users(
        users=[p.user for p in parent_users],
        school=attendance.school,
        session=attendance.session,
        title=title,
        message=message,
        related_model='StudentAttendance',
        related_id=attendance.id,
        event_key_prefix=f'attendance_absent:{attendance.id}',
        send_email=True,
        send_sms=True,
    )


def trigger_leave_decision_notifications(*, leave_request):
    if leave_request.status not in {'approved', 'rejected'}:
        return []

    staff_user = leave_request.staff.user
    title = f"Leave {leave_request.status.title()}"
    message = (
        f"Your leave request from {leave_request.start_date} to {leave_request.end_date} "
        f"was {leave_request.status}."
    )
    return notify_users(
        users=[staff_user],
        school=leave_request.school,
        session=None,
        title=title,
        message=message,
        related_model='LeaveRequest',
        related_id=leave_request.id,
        event_key_prefix=f'leave_decision:{leave_request.id}:{leave_request.status}',
        send_email=True,
        send_sms=False,
        triggered_by=leave_request.approved_by,
    )


def trigger_payroll_processed_notifications(*, payroll):
    title = 'Payroll Processed'
    message = (
        f"Payroll for {payroll.month:02d}/{payroll.year} has been processed. "
        f"Net Salary: {payroll.net_salary}."
    )
    return notify_users(
        users=[payroll.staff.user],
        school=payroll.school,
        session=payroll.session,
        title=title,
        message=message,
        related_model='Payroll',
        related_id=payroll.id,
        event_key_prefix=f'payroll_processed:{payroll.id}',
        send_email=True,
        send_sms=False,
        triggered_by=payroll.processed_by,
    )


def trigger_exam_result_published_notifications(*, exam):
    from apps.core.exams.services import eligible_students_for_exam

    students = eligible_students_for_exam(exam)
    users = []
    seen = set()
    for student in students:
        for parent in _parent_users_for_student(student):
            if parent.user_id in seen:
                continue
            seen.add(parent.user_id)
            users.append(parent.user)

    if not users:
        return []

    title = 'Exam Result Published'
    section_name = exam.section.name if exam.section_id else 'All Sections'
    message = (
        f"Results have been published for {exam.exam_type.name} - "
        f"{exam.school_class.name} ({section_name})."
    )
    return notify_users(
        users=users,
        school=exam.school,
        session=exam.session,
        title=title,
        message=message,
        related_model='Exam',
        related_id=exam.id,
        event_key_prefix=f'exam_locked:{exam.id}',
        send_email=True,
        send_sms=False,
    )


def run_fee_overdue_notifications(*, school, session=None, as_of_date: date | None = None):
    from apps.core.fees.services import student_outstanding_summary

    session = _resolve_session(school, session)
    if not session:
        return {'students': 0, 'notifications': 0}

    as_of_date = as_of_date or timezone.localdate()
    students = Student.objects.filter(
        school=school,
        session=session,
        is_active=True,
        is_archived=False,
    ).order_by('admission_number')

    total_notifications = 0
    student_count = 0

    for student in students:
        summary = student_outstanding_summary(
            student=student,
            session=session,
            as_of_date=as_of_date,
        )
        if summary['total_due'] <= 0:
            continue

        student_count += 1
        parent_users = _parent_users_for_student(student)
        if not parent_users:
            continue

        title = 'Fee Due Reminder'
        message = (
            f"Outstanding fee for {student.full_name} ({student.admission_number}) is "
            f"{summary['total_due']} as of {as_of_date}."
        )
        created = notify_users(
            users=[p.user for p in parent_users],
            school=school,
            session=session,
            title=title,
            message=message,
            related_model='StudentFee',
            related_id=student.id,
            event_key_prefix=f'fee_due:{student.id}:{as_of_date.isoformat()}',
            send_email=True,
            send_sms=True,
        )
        total_notifications += len(created)

    return {
        'students': student_count,
        'notifications': total_notifications,
    }


def bulk_email_for_class_section(*, school, session, school_class, section=None, subject='', message='', triggered_by=None):
    ensure_email_channel_ready(school=school)
    students = Student.objects.filter(
        school=school,
        session=session,
        current_class=school_class,
        is_active=True,
        is_archived=False,
    )
    if section:
        students = students.filter(current_section=section)

    recipients = set()
    for student in students:
        for parent in _parent_users_for_student(student):
            emails, _ = _parent_contacts(parent)
            recipients.update(emails)

    logs = []
    for recipient in sorted(recipients):
        logs.append(
            send_email_notification(
                school=school,
                session=session,
                recipient=recipient,
                subject=subject,
                message=message,
                related_model='Announcement',
                related_id='bulk',
                triggered_by=triggered_by,
            )
        )
    return logs


def bulk_sms_for_class_section(*, school, session, school_class, section=None, message='', triggered_by=None):
    ensure_sms_channel_ready(school=school)
    students = Student.objects.filter(
        school=school,
        session=session,
        current_class=school_class,
        is_active=True,
        is_archived=False,
    )
    if section:
        students = students.filter(current_section=section)

    recipients = set()
    for student in students:
        for parent in _parent_users_for_student(student):
            _, phones = _parent_contacts(parent)
            recipients.update(phones)

    logs = []
    for recipient in sorted(recipients):
        logs.append(
            send_sms_notification(
                school=school,
                session=session,
                recipient_number=recipient,
                message=message,
                related_model='Announcement',
                related_id='bulk',
                triggered_by=triggered_by,
            )
        )
    return logs


def unread_notification_count(*, user):
    return Notification.objects.filter(user=user, is_read=False).count()


def message_stats(*, school, session=None):
    rows = Message.objects.filter(thread__school=school)
    if session:
        rows = rows.filter(thread__session=session)

    total = rows.count()
    unread = rows.filter(is_read=False).count()
    by_sender = defaultdict(int)

    for row in rows.select_related('sender'):
        by_sender[row.sender.username] += 1

    return {
        'total': total,
        'unread': unread,
        'by_sender': dict(sorted(by_sender.items(), key=lambda item: item[0])),
    }
