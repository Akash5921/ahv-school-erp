from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import NoticeForm
from .models import Notice, NoticeRead


def _audience_queryset(user):
    return Notice.objects.filter(
        school=user.school,
        is_published=True
    ).filter(
        Q(target_role='all') | Q(target_role=user.role)
    )


@login_required
@role_required('schooladmin')
def notice_manage(request):
    school = request.user.school
    notices = Notice.objects.filter(school=school).select_related('created_by').order_by('-publish_at', '-id')
    error = None

    if request.method == 'POST':
        form = NoticeForm(request.POST)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.school = school
            notice.created_by = request.user
            notice.save()
            log_audit_event(
                request=request,
                action='notice.created',
                school=school,
                target=notice,
                details=f"Role={notice.target_role}, Published={notice.is_published}",
            )
            return redirect('notice_manage')
        error = 'Please correct notice details.'
    else:
        form = NoticeForm()

    return render(request, 'communication/notice_manage.html', {
        'notices': notices,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def notice_toggle_publish(request, notice_id):
    notice = get_object_or_404(Notice, id=notice_id, school=request.user.school)
    if request.method == 'POST':
        notice.is_published = not notice.is_published
        notice.save(update_fields=['is_published'])
        log_audit_event(
            request=request,
            action='notice.publish_toggled',
            school=request.user.school,
            target=notice,
            details=f"Published={notice.is_published}",
        )
    return redirect('notice_manage')


@login_required
@role_required(['schooladmin', 'teacher', 'accountant', 'staff', 'parent'])
def notice_feed(request):
    notices = _audience_queryset(request.user)
    read_notice_ids = set(
        NoticeRead.objects.filter(
            user=request.user,
            notice__in=notices
        ).values_list('notice_id', flat=True)
    )

    rows = []
    unread_count = 0
    for notice in notices:
        is_read = notice.id in read_notice_ids
        if not is_read:
            unread_count += 1
        rows.append({
            'notice': notice,
            'is_read': is_read,
        })

    return render(request, 'communication/notice_feed.html', {
        'rows': rows,
        'unread_count': unread_count,
    })


@login_required
@role_required(['schooladmin', 'teacher', 'accountant', 'staff', 'parent'])
def notice_mark_read(request, notice_id):
    notice = get_object_or_404(_audience_queryset(request.user), id=notice_id)
    if request.method == 'POST':
        read_entry, created = NoticeRead.objects.get_or_create(
            notice=notice,
            user=request.user
        )
        if created:
            log_audit_event(
                request=request,
                action='notice.read',
                school=request.user.school,
                target=notice,
                details=f"User={request.user.id}",
            )
    return redirect('notice_feed')
