from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.core.academic_sessions.models import AcademicSession
from apps.core.attendance.services import student_monthly_report
from apps.core.exams.models import ExamResultSummary, StudentMark
from apps.core.fees.models import FeePayment, FeeReceipt
from apps.core.fees.services import student_outstanding_summary
from apps.core.students.models import Student
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    AnnouncementForm,
    BulkEmailForm,
    BulkSMSForm,
    GlobalSettingsForm,
    MessageEditForm,
    MessageReplyForm,
    MessageThreadCreateForm,
    MonthYearForm,
    NotificationFilterForm,
    ParentStudentLinkForm,
    ParentUserForm,
)
from .models import (
    Announcement,
    EmailLog,
    GlobalSettings,
    Message,
    MessageThread,
    Notification,
    ParentStudentLink,
    ParentUser,
    SMSLog,
)
from .services import (
    bulk_email_for_class_section,
    bulk_sms_for_class_section,
    create_message_thread,
    edit_message,
    mark_message_read,
    mark_notification_read,
    message_stats,
    send_message,
    visible_announcements_for_user,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('session')

    selected_session = None
    if session_id and str(session_id).isdigit():
        selected_session = sessions.filter(id=int(session_id)).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


def _status_counts(logs):
    sent = sum(1 for row in logs if row.status == 'sent')
    failed = len(logs) - sent
    return sent, failed


def _thread_for_user_or_404(user, thread_id):
    return get_object_or_404(
        MessageThread.objects.filter(thread_participants__user=user).distinct().select_related('school', 'session', 'created_by'),
        pk=thread_id,
        school=user.school,
    )


def _parent_profile_or_none(user):
    return ParentUser.objects.filter(
        school=user.school,
        user=user,
        is_active=True,
    ).select_related('parent_info').first()


def _linked_student_or_404(*, user, student_id):
    parent_profile = _parent_profile_or_none(user)
    if not parent_profile:
        return None, None

    link = get_object_or_404(
        ParentStudentLink.objects.select_related('student', 'student__session', 'student__current_class', 'student__current_section'),
        parent_user=parent_profile,
        student_id=student_id,
    )
    return parent_profile, link.student


@login_required
@role_required('schooladmin')
def communication_announcement_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        form = AnnouncementForm(
            request.POST,
            request.FILES,
            school=school,
            default_session=selected_session,
        )
        if form.is_valid():
            row = form.save(commit=False)
            row.school = school
            row.created_by = request.user
            row.save()
            log_audit_event(
                request=request,
                action='communication.announcement_created',
                school=school,
                target=row,
                details=f"Role={row.target_role}, Session={row.session_id}",
            )
            messages.success(request, 'Announcement created successfully.')
            return redirect(f"{reverse('communication_announcement_list_core')}?session={row.session_id}")
    else:
        form = AnnouncementForm(school=school, default_session=selected_session)

    rows = Announcement.objects.filter(school=school)
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'communication_core/announcement_list.html', {
        'form': form,
        'rows': rows.order_by('-created_at'),
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def communication_announcement_update(request, pk):
    school = request.user.school
    row = get_object_or_404(Announcement, pk=pk, school=school)
    if row.is_expired:
        messages.error(request, 'Expired announcements cannot be edited.')
        return redirect(f"{reverse('communication_announcement_list_core')}?session={row.session_id}")

    if request.method == 'POST':
        form = AnnouncementForm(request.POST, request.FILES, instance=row, school=school, default_session=row.session)
        if form.is_valid():
            row = form.save()
            log_audit_event(
                request=request,
                action='communication.announcement_updated',
                school=school,
                target=row,
                details=f"Role={row.target_role}",
            )
            messages.success(request, 'Announcement updated successfully.')
            return redirect(f"{reverse('communication_announcement_list_core')}?session={row.session_id}")
    else:
        form = AnnouncementForm(instance=row, school=school, default_session=row.session)

    return render(request, 'communication_core/announcement_form.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required('schooladmin')
@require_POST
def communication_announcement_deactivate(request, pk):
    row = get_object_or_404(Announcement, pk=pk, school=request.user.school)
    row.delete()
    log_audit_event(
        request=request,
        action='communication.announcement_deactivated',
        school=request.user.school,
        target=row,
        details=f"Title={row.title}",
    )
    messages.success(request, 'Announcement deactivated.')
    return redirect('communication_announcement_list_core')


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
def communication_announcement_feed(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)
    announcements = visible_announcements_for_user(user=request.user, session=selected_session)

    return render(request, 'communication_core/announcement_feed.html', {
        'rows': announcements,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def communication_parent_users(request):
    school = request.user.school

    parent_form = ParentUserForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'create_parent_user' else None,
        school=school,
    )
    link_form = ParentStudentLinkForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'link_student' else None,
        school=school,
    )

    if request.method == 'POST' and request.POST.get('action') == 'create_parent_user':
        if parent_form.is_valid():
            parent_user = parent_form.save(commit=False)
            parent_user.school = school
            parent_user.save()
            log_audit_event(
                request=request,
                action='communication.parent_user_created',
                school=school,
                target=parent_user,
                details=f"User={parent_user.user_id}",
            )
            messages.success(request, 'Parent portal user created.')
            return redirect('communication_parent_users_core')

    if request.method == 'POST' and request.POST.get('action') == 'link_student':
        if link_form.is_valid():
            link = link_form.save()
            log_audit_event(
                request=request,
                action='communication.parent_student_linked',
                school=school,
                target=link,
                details=f"ParentUser={link.parent_user_id}, Student={link.student_id}",
            )
            messages.success(request, 'Parent-student link saved.')
            return redirect('communication_parent_users_core')

    parent_users = ParentUser.objects.filter(school=school).select_related('user', 'parent_info', 'parent_info__student')
    links = ParentStudentLink.objects.filter(
        parent_user__school=school,
    ).select_related('parent_user', 'parent_user__user', 'student').order_by('parent_user__user__username', '-is_primary')

    return render(request, 'communication_core/parent_user_list.html', {
        'parent_form': parent_form,
        'link_form': link_form,
        'parent_users': parent_users,
        'links': links,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
def communication_thread_list(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    create_form = MessageThreadCreateForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'create_thread' else None,
        request.FILES if request.method == 'POST' and request.POST.get('action') == 'create_thread' else None,
        school=school,
        sender=request.user,
        default_session=selected_session,
    )

    if request.method == 'POST' and request.POST.get('action') == 'create_thread':
        if create_form.is_valid():
            try:
                thread = create_message_thread(
                    school=school,
                    session=create_form.cleaned_data['session'],
                    subject=create_form.cleaned_data['subject'],
                    created_by=request.user,
                    initial_receiver=create_form.cleaned_data['receiver'],
                    message_text=create_form.cleaned_data['message_text'],
                    attachment=create_form.cleaned_data['attachment'],
                )
            except ValidationError as exc:
                create_form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='communication.thread_created',
                    school=school,
                    target=thread,
                    details=f"Receiver={create_form.cleaned_data['receiver'].id}",
                )
                messages.success(request, 'Conversation created successfully.')
                return redirect('communication_thread_detail_core', thread_id=thread.id)

    threads = MessageThread.objects.filter(
        school=school,
        thread_participants__user=request.user,
    ).distinct().select_related('session', 'created_by')
    if selected_session:
        threads = threads.filter(session=selected_session)

    unread_map = {
        row['thread_id']: row['count']
        for row in Message.objects.filter(
            thread__school=school,
            receiver=request.user,
            is_read=False,
        ).values('thread_id').annotate(count=Count('id'))
    }
    thread_rows = list(threads.order_by('-updated_at'))
    for row in thread_rows:
        row.unread_count = unread_map.get(row.id, 0)

    return render(request, 'communication_core/thread_list.html', {
        'threads': thread_rows,
        'create_form': create_form,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
def communication_thread_detail(request, thread_id):
    thread = _thread_for_user_or_404(request.user, thread_id)

    reply_form = MessageReplyForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'reply' else None,
        request.FILES if request.method == 'POST' and request.POST.get('action') == 'reply' else None,
        thread=thread,
        sender=request.user,
    )

    if request.method == 'POST' and request.POST.get('action') == 'reply':
        if reply_form.is_valid():
            try:
                msg = send_message(
                    thread=thread,
                    sender=request.user,
                    receiver=reply_form.cleaned_data['receiver'],
                    message_text=reply_form.cleaned_data['message_text'],
                    attachment=reply_form.cleaned_data['attachment'],
                )
            except ValidationError as exc:
                reply_form.add_error(None, '; '.join(exc.messages))
            else:
                log_audit_event(
                    request=request,
                    action='communication.message_sent',
                    school=request.user.school,
                    target=msg,
                    details=f"Thread={thread.id}, Receiver={msg.receiver_id}",
                )
                messages.success(request, 'Message sent.')
                return redirect('communication_thread_detail_core', thread_id=thread.id)

    unread_messages = Message.objects.filter(thread=thread, receiver=request.user, is_read=False)
    for row in unread_messages:
        try:
            mark_message_read(message=row, user=request.user)
        except ValidationError:
            continue

    rows = Message.objects.filter(thread=thread).select_related('sender', 'receiver', 'edited_by').order_by('sent_at', 'id')

    return render(request, 'communication_core/thread_detail.html', {
        'thread': thread,
        'rows': rows,
        'reply_form': reply_form,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
def communication_message_edit(request, message_id):
    row = get_object_or_404(
        Message.objects.select_related('thread', 'sender', 'receiver'),
        pk=message_id,
        sender=request.user,
        thread__school=request.user.school,
    )

    form = MessageEditForm(request.POST or None, initial={'message_text': row.message_text})
    if request.method == 'POST' and form.is_valid():
        try:
            updated = edit_message(
                message=row,
                editor=request.user,
                message_text=form.cleaned_data['message_text'],
            )
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            log_audit_event(
                request=request,
                action='communication.message_edited',
                school=request.user.school,
                target=updated,
                details=f"Thread={updated.thread_id}",
            )
            messages.success(request, 'Message updated.')
            return redirect('communication_thread_detail_core', thread_id=updated.thread_id)

    return render(request, 'communication_core/message_edit.html', {
        'form': form,
        'row': row,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
@require_POST
def communication_message_mark_read(request, message_id):
    row = get_object_or_404(
        Message.objects.select_related('thread'),
        pk=message_id,
        receiver=request.user,
        thread__school=request.user.school,
    )
    try:
        mark_message_read(message=row, user=request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('communication_thread_detail_core', thread_id=row.thread_id)


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
def communication_notification_list(request):
    form = NotificationFilterForm(request.GET or None)
    rows = Notification.objects.filter(
        school=request.user.school,
        user=request.user,
    ).order_by('-created_at')

    unread_only = False
    if form.is_valid():
        unread_only = form.cleaned_data.get('unread_only', False)
        if unread_only:
            rows = rows.filter(is_read=False)

    unread_count = Notification.objects.filter(
        school=request.user.school,
        user=request.user,
        is_read=False,
    ).count()

    return render(request, 'communication_core/notification_list.html', {
        'rows': rows,
        'form': form,
        'unread_count': unread_count,
        'unread_only': unread_only,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
@require_POST
def communication_notification_mark_read(request, pk):
    row = get_object_or_404(Notification, pk=pk, user=request.user, school=request.user.school)
    try:
        mark_notification_read(notification=row, user=request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('communication_notification_list_core')


@login_required
@role_required(['schooladmin', 'teacher', 'staff', 'accountant', 'parent'])
@require_POST
def communication_notification_mark_all_read(request):
    Notification.objects.filter(user=request.user, school=request.user.school, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
    messages.success(request, 'All notifications marked as read.')
    return redirect('communication_notification_list_core')


@login_required
@role_required('schooladmin')
def communication_settings_manage(request):
    school = request.user.school
    settings_obj, _ = GlobalSettings.objects.get_or_create(school=school)

    if request.method == 'POST':
        form = GlobalSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            settings_obj = form.save()
            log_audit_event(
                request=request,
                action='communication.settings_updated',
                school=school,
                target=settings_obj,
                details=f"EmailEnabled={settings_obj.email_enabled}, SMSEnabled={settings_obj.sms_enabled}",
            )
            messages.success(request, 'Communication settings updated.')
            return redirect('communication_settings_core')
    else:
        form = GlobalSettingsForm(instance=settings_obj)

    return render(request, 'communication_core/settings.html', {
        'form': form,
        'settings_obj': settings_obj,
    })


@login_required
@role_required('schooladmin')
def communication_bulk_dispatch(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    email_form = BulkEmailForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'email' else None,
        school=school,
        default_session=selected_session,
    )
    sms_form = BulkSMSForm(
        request.POST if request.method == 'POST' and request.POST.get('action') == 'sms' else None,
        school=school,
        default_session=selected_session,
    )

    if request.method == 'POST' and request.POST.get('action') == 'email':
        if email_form.is_valid():
            try:
                logs = bulk_email_for_class_section(
                    school=school,
                    session=email_form.cleaned_data['session'],
                    school_class=email_form.cleaned_data['school_class'],
                    section=email_form.cleaned_data['section'],
                    subject=email_form.cleaned_data['subject'],
                    message=email_form.cleaned_data['message'],
                    triggered_by=request.user,
                )
            except ValidationError as exc:
                email_form.add_error(None, '; '.join(exc.messages))
            else:
                sent, failed = _status_counts(logs)
                log_audit_event(
                    request=request,
                    action='communication.bulk_email_sent',
                    school=school,
                    details=f"Sent={sent}, Failed={failed}",
                )
                messages.success(request, f'Bulk email completed. Sent={sent}, Failed={failed}.')
                return redirect('communication_bulk_dispatch_core')

    if request.method == 'POST' and request.POST.get('action') == 'sms':
        if sms_form.is_valid():
            try:
                logs = bulk_sms_for_class_section(
                    school=school,
                    session=sms_form.cleaned_data['session'],
                    school_class=sms_form.cleaned_data['school_class'],
                    section=sms_form.cleaned_data['section'],
                    message=sms_form.cleaned_data['message'],
                    triggered_by=request.user,
                )
            except ValidationError as exc:
                sms_form.add_error(None, '; '.join(exc.messages))
            else:
                sent, failed = _status_counts(logs)
                log_audit_event(
                    request=request,
                    action='communication.bulk_sms_sent',
                    school=school,
                    details=f"Sent={sent}, Failed={failed}",
                )
                messages.success(request, f'Bulk SMS completed. Sent={sent}, Failed={failed}.')
                return redirect('communication_bulk_dispatch_core')

    recent_email_logs = EmailLog.objects.filter(school=school).order_by('-timestamp')[:20]
    recent_sms_logs = SMSLog.objects.filter(school=school).order_by('-timestamp')[:20]

    return render(request, 'communication_core/bulk_dispatch.html', {
        'email_form': email_form,
        'sms_form': sms_form,
        'recent_email_logs': recent_email_logs,
        'recent_sms_logs': recent_sms_logs,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def communication_report_dashboard(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    msg = message_stats(school=school, session=selected_session)

    email_qs = EmailLog.objects.filter(school=school)
    sms_qs = SMSLog.objects.filter(school=school)
    notif_qs = Notification.objects.filter(school=school)

    if selected_session:
        email_qs = email_qs.filter(session=selected_session)
        sms_qs = sms_qs.filter(session=selected_session)
        notif_qs = notif_qs.filter(session=selected_session)

    email_stats = {
        row['status']: row['count']
        for row in email_qs.values('status').annotate(count=Count('id'))
    }
    sms_stats = {
        row['status']: row['count']
        for row in sms_qs.values('status').annotate(count=Count('id'))
    }

    total_notifications = notif_qs.count()
    read_notifications = notif_qs.filter(is_read=True).count()
    unread_notifications = total_notifications - read_notifications

    return render(request, 'communication_core/report_dashboard.html', {
        'sessions': sessions,
        'selected_session': selected_session,
        'message_stats': msg,
        'email_stats': email_stats,
        'sms_stats': sms_stats,
        'total_notifications': total_notifications,
        'read_notifications': read_notifications,
        'unread_notifications': unread_notifications,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def communication_report_messages(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    rows = Message.objects.filter(thread__school=school).select_related('thread', 'sender', 'receiver')
    if selected_session:
        rows = rows.filter(thread__session=selected_session)

    return render(request, 'communication_core/report_messages.html', {
        'rows': rows.order_by('-sent_at')[:500],
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def communication_report_emails(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    rows = EmailLog.objects.filter(school=school)
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'communication_core/report_emails.html', {
        'rows': rows.order_by('-timestamp')[:500],
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def communication_report_sms(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    rows = SMSLog.objects.filter(school=school)
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'communication_core/report_sms.html', {
        'rows': rows.order_by('-timestamp')[:500],
        'selected_session': selected_session,
    })


@login_required
@role_required(['schooladmin', 'accountant'])
def communication_report_notifications(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    rows = Notification.objects.filter(school=school).select_related('user', 'session')
    if selected_session:
        rows = rows.filter(session=selected_session)

    return render(request, 'communication_core/report_notifications.html', {
        'rows': rows.order_by('-created_at')[:500],
        'selected_session': selected_session,
    })


@login_required
@role_required('parent')
def communication_parent_portal(request):
    school = request.user.school
    sessions, selected_session = _resolve_selected_session(request, school)

    parent_profile = _parent_profile_or_none(request.user)
    if not parent_profile:
        messages.error(request, 'Parent portal profile is not configured for your account.')
        return render(request, 'communication_core/parent_portal.html', {
            'rows': [],
            'sessions': sessions,
            'selected_session': selected_session,
        })

    links = ParentStudentLink.objects.filter(parent_user=parent_profile).select_related(
        'student',
        'student__current_class',
        'student__current_section',
    )
    if selected_session:
        links = links.filter(student__session=selected_session)

    rows = []
    for link in links:
        student = link.student
        session = selected_session or student.session

        attendance_summary = None
        if session:
            attendance_summary = student.attendance_summaries.filter(session=session).order_by('-year', '-month').first()

        latest_result = ExamResultSummary.objects.filter(
            school=school,
            student=student,
            session=session,
        ).select_related('exam', 'exam__exam_type').order_by('-exam__start_date').first() if session else None

        fee_summary = {'total_due': 0, 'principal_due': 0, 'fine_due': 0}
        if session:
            fee_summary = student_outstanding_summary(student=student, session=session)

        receipt_count = FeeReceipt.objects.filter(
            school=school,
            student=student,
            session=session,
        ).count() if session else 0

        rows.append({
            'student': student,
            'is_primary': link.is_primary,
            'attendance_summary': attendance_summary,
            'latest_result': latest_result,
            'fee_summary': fee_summary,
            'receipt_count': receipt_count,
        })

    return render(request, 'communication_core/parent_portal.html', {
        'rows': rows,
        'sessions': sessions,
        'selected_session': selected_session,
    })


@login_required
@role_required('parent')
def communication_parent_student_attendance(request, student_id):
    parent_profile, student = _linked_student_or_404(user=request.user, student_id=student_id)
    if not parent_profile:
        messages.error(request, 'Parent portal profile is not configured.')
        return redirect('communication_parent_portal_core')

    month_form = MonthYearForm(request.GET or None)
    today = timezone.localdate()
    month = today.month
    year = today.year
    if month_form.is_valid():
        month = month_form.cleaned_data['month']
        year = month_form.cleaned_data['year']

    summary, records = student_monthly_report(
        student=student,
        session=student.session,
        year=year,
        month=month,
    )

    return render(request, 'communication_core/parent_student_attendance.html', {
        'student': student,
        'summary': summary,
        'records': records,
        'month_form': month_form,
        'month': month,
        'year': year,
    })


@login_required
@role_required('parent')
def communication_parent_student_marks(request, student_id):
    parent_profile, student = _linked_student_or_404(user=request.user, student_id=student_id)
    if not parent_profile:
        messages.error(request, 'Parent portal profile is not configured.')
        return redirect('communication_parent_portal_core')

    summaries = ExamResultSummary.objects.filter(
        school=student.school,
        student=student,
        session=student.session,
    ).select_related('exam', 'exam__exam_type').order_by('-exam__start_date')

    selected_summary = None
    summary_id = request.GET.get('summary')
    if summary_id and str(summary_id).isdigit():
        selected_summary = summaries.filter(id=int(summary_id)).first()
    if not selected_summary:
        selected_summary = summaries.first()

    marks = StudentMark.objects.none()
    if selected_summary:
        marks = StudentMark.objects.filter(
            school=student.school,
            session=student.session,
            student=student,
            exam=selected_summary.exam,
        ).select_related('subject').order_by('subject__name')

    return render(request, 'communication_core/parent_student_marks.html', {
        'student': student,
        'summaries': summaries,
        'selected_summary': selected_summary,
        'marks': marks,
    })


@login_required
@role_required('parent')
def communication_parent_student_fees(request, student_id):
    parent_profile, student = _linked_student_or_404(user=request.user, student_id=student_id)
    if not parent_profile:
        messages.error(request, 'Parent portal profile is not configured.')
        return redirect('communication_parent_portal_core')

    summary = student_outstanding_summary(student=student, session=student.session)

    payments = FeePayment.objects.filter(
        school=student.school,
        session=student.session,
        student=student,
    ).select_related('installment', 'receipt').order_by('-payment_date', '-id')

    receipts = FeeReceipt.objects.filter(
        school=student.school,
        session=student.session,
        student=student,
    ).select_related('payment').order_by('-generated_at')

    return render(request, 'communication_core/parent_student_fees.html', {
        'student': student,
        'summary': summary,
        'payments': payments,
        'receipts': receipts,
    })

