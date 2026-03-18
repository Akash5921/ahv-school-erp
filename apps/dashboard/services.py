from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.attendance.models import StudentAttendance, StudentAttendanceSummary
from apps.core.communication.models import Message, Notification, ParentStudentLink, ParentUser
from apps.core.communication.services import visible_announcements_for_user
from apps.core.exams.models import Exam, ExamResultSummary, StudentMark
from apps.core.fees.models import FeePaymentAllocation, FeeReceipt, FeeRefund, LedgerEntry, StudentFee
from apps.core.fees.services import student_outstanding_summary
from apps.core.hr.models import ClassTeacher, Payroll, Staff
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.timetable.models import TimetableEntry
from apps.core.users.models import AuditLog, User

from .analytics import build_bar_chart, build_line_chart, build_pie_chart, month_labels


def _to_decimal(value):
    return Decimal(str(value or '0'))


def _money(value):
    return _to_decimal(value).quantize(Decimal('0.01'))


def _weekday_key(target_date):
    return [
        'monday',
        'tuesday',
        'wednesday',
        'thursday',
        'friday',
        'saturday',
        'sunday',
    ][target_date.weekday()]


def _teacher_profile(user):
    if not getattr(user, 'school_id', None):
        return None
    return Staff.objects.filter(
        school=user.school,
        user=user,
        is_active=True,
    ).select_related('designation', 'user').first()


def _parent_profile(user):
    if not getattr(user, 'school_id', None):
        return None
    return ParentUser.objects.filter(
        school=user.school,
        user=user,
        is_active=True,
    ).select_related('parent_info', 'parent_info__student').first()


def _unread_counts(user):
    if not getattr(user, 'school_id', None):
        return {'unread_notifications': 0, 'unread_messages': 0}
    return {
        'unread_notifications': Notification.objects.filter(
            school=user.school,
            user=user,
            is_read=False,
        ).count(),
        'unread_messages': Message.objects.filter(
            thread__school=user.school,
            receiver=user,
            is_read=False,
        ).count(),
    }


def _attendance_rate(*, school, session, target_date):
    total_students = StudentSessionRecord.objects.filter(
        school=school,
        session=session,
        student__is_archived=False,
        student__is_active=True,
    ).values('student_id').distinct().count()
    if total_students == 0:
        return Decimal('0.00')

    present_count = StudentAttendance.objects.filter(
        school=school,
        session=session,
        date=target_date,
        status__in=[StudentAttendance.STATUS_PRESENT, StudentAttendance.STATUS_LATE],
    ).count()
    return _money((Decimal(present_count) / Decimal(total_students)) * Decimal('100'))


def _school_snapshot(*, school, session):
    today = timezone.localdate()
    key = f"phase11:dashboard:snapshot:{school.id}:{session.id if session else 0}:{today.isoformat()}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    month_end = next_month - timedelta(days=1)

    total_students = Student.objects.filter(
        school=school,
        session=session,
        is_archived=False,
        is_active=True,
    ).count() if session else Student.objects.filter(
        school=school,
        is_archived=False,
        is_active=True,
    ).count()

    total_staff = Staff.objects.filter(
        school=school,
        is_active=True,
        status=Staff.STATUS_ACTIVE,
    ).count()

    total_users = User.objects.filter(school=school).count()
    active_users = User.objects.filter(school=school, is_active=True).count()

    fee_assigned = _to_decimal(
        StudentFee.objects.filter(
            school=school,
            session=session,
            is_active=True,
        ).aggregate(total=Sum('final_amount')).get('total')
    ) if session else Decimal('0.00')
    fee_paid = _to_decimal(
        FeePaymentAllocation.objects.filter(
            student_fee__school=school,
            student_fee__session=session,
            student_fee__is_active=True,
            payment__is_reversed=False,
        ).aggregate(total=Sum('amount')).get('total')
    ) if session else Decimal('0.00')
    pending_fee_amount = _money(max(fee_assigned - fee_paid, Decimal('0.00')))

    fee_collected_this_month = _money(
        LedgerEntry.objects.filter(
            school=school,
            session=session,
            transaction_type=LedgerEntry.TYPE_INCOME,
            reference_model='FeePayment',
            date__range=(month_start, month_end),
        ).aggregate(total=Sum('amount')).get('total')
    ) if session else Decimal('0.00')

    monthly_salary_expense = _money(
        LedgerEntry.objects.filter(
            school=school,
            session=session,
            transaction_type=LedgerEntry.TYPE_EXPENSE,
            reference_model='Payroll',
            date__range=(month_start, month_end),
        ).aggregate(total=Sum('amount')).get('total')
    ) if session else Decimal('0.00')

    upcoming_exam = None
    if session:
        upcoming_exam = Exam.objects.filter(
            school=school,
            session=session,
            is_active=True,
            start_date__gte=today,
        ).select_related('exam_type', 'school_class', 'section').order_by('start_date', 'id').first()

    trend_labels = month_labels(end_date=today, months=6)
    trend_lookup = {}
    if session:
        trend_rows = LedgerEntry.objects.filter(
            school=school,
            session=session,
            transaction_type=LedgerEntry.TYPE_INCOME,
            reference_model='FeePayment',
        ).annotate(month_bucket=TruncMonth('date')).values('month_bucket').annotate(
            total=Sum('amount')
        ).order_by('month_bucket')
        for row in trend_rows:
            month_bucket = row['month_bucket']
            trend_lookup[(month_bucket.year, month_bucket.month)] = float(row['total'] or 0)

    line_labels = []
    line_values = []
    for year, month, label in trend_labels:
        line_labels.append(label)
        line_values.append(trend_lookup.get((year, month), 0))
    fee_trend_chart = build_line_chart(labels=line_labels, values=line_values)

    class_strength_rows = []
    if session:
        class_counts = StudentSessionRecord.objects.filter(
            school=school,
            session=session,
            student__is_archived=False,
            student__is_active=True,
        ).values('school_class__name').annotate(
            total=Count('student_id', distinct=True)
        ).order_by('school_class__display_order', 'school_class__name')
        class_strength_rows = build_bar_chart([
            {'label': row['school_class__name'], 'value': row['total']}
            for row in class_counts
        ])

    fee_split_chart = build_pie_chart([
        {'label': 'Collected', 'value': fee_paid, 'color': '#2563eb'},
        {'label': 'Pending', 'value': pending_fee_amount, 'color': '#f59e0b'},
    ])

    snapshot = {
        'school': school,
        'active_session': session,
        'total_students': total_students,
        'total_staff': total_staff,
        'total_users': total_users,
        'active_users': active_users,
        'today_attendance_pct': _attendance_rate(school=school, session=session, target_date=today) if session else Decimal('0.00'),
        'fee_collected_this_month': fee_collected_this_month,
        'pending_fee_amount': pending_fee_amount,
        'monthly_salary_expense': monthly_salary_expense,
        'upcoming_exam': upcoming_exam,
        'fee_trend_chart': fee_trend_chart,
        'class_strength_chart': class_strength_rows,
        'fee_split_chart': fee_split_chart,
        'role_counts': {
            row['role']: row['total']
            for row in User.objects.filter(school=school).values('role').annotate(total=Count('id')).order_by('role')
        },
        'total_sessions': AcademicSession.objects.filter(school=school).count(),
        'recent_receipts': list(
            FeeReceipt.objects.filter(
                school=school,
                session=session,
            ).select_related('student', 'payment').order_by('-generated_at')[:5]
        ) if session else [],
        'refunds_this_month': _money(
            FeeRefund.objects.filter(
                school=school,
                session=session,
                refund_date__range=(month_start, month_end),
                is_reversed=False,
            ).aggregate(total=Sum('refund_amount')).get('total')
        ) if session else Decimal('0.00'),
        'unpaid_payroll_count': Payroll.objects.filter(
            school=school,
            session=session,
            is_paid=False,
        ).count() if session else 0,
    }
    cache.set(key, snapshot, 120)
    return snapshot


def build_school_admin_dashboard_context(user):
    school = user.school
    session = getattr(school, 'current_session', None)
    context = dict(_school_snapshot(school=school, session=session))
    context.update(_unread_counts(user))
    context.update({
        'recent_announcements': visible_announcements_for_user(user=user, session=session)[:6],
        'domains': school.domains.order_by('-is_primary', 'domain'),
        'recent_logs': AuditLog.objects.filter(school=school).select_related('user')[:8],
    })
    return context


def build_principal_dashboard_context(user):
    school = user.school
    session = getattr(school, 'current_session', None)
    context = dict(_school_snapshot(school=school, session=session))
    context.update(_unread_counts(user))

    latest_locked_exam = None
    pass_rate = Decimal('0.00')
    if session:
        latest_locked_exam = Exam.objects.filter(
            school=school,
            session=session,
            is_locked=True,
        ).select_related('exam_type', 'school_class', 'section').order_by('-start_date', '-id').first()
        if latest_locked_exam:
            summaries = ExamResultSummary.objects.filter(
                school=school,
                session=session,
                exam=latest_locked_exam,
            )
            total = summaries.count()
            passed = summaries.filter(result_status=ExamResultSummary.STATUS_PASS).count()
            if total:
                pass_rate = _money((Decimal(passed) / Decimal(total)) * Decimal('100'))

    context.update({
        'page_title': 'Principal Dashboard',
        'page_intro': 'Academic oversight, attendance health, and exam readiness in one view.',
        'recent_announcements': visible_announcements_for_user(user=user, session=session)[:6],
        'latest_locked_exam': latest_locked_exam,
        'latest_exam_pass_rate': pass_rate,
        'recent_parent_messages': Message.objects.filter(
            thread__school=school,
            sender__role='parent',
        ).select_related('sender', 'receiver').order_by('-sent_at')[:5],
    })
    return context


def build_accountant_dashboard_context(user):
    school = user.school
    session = getattr(school, 'current_session', None)
    context = dict(_school_snapshot(school=school, session=session))
    context.update(_unread_counts(user))

    today = timezone.localdate()
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    month_end = next_month - timedelta(days=1)

    recent_ledger_entries = LedgerEntry.objects.filter(
        school=school,
        session=session,
    ).select_related('created_by').order_by('-date', '-id')[:8] if session else []

    context.update({
        'page_title': 'Accountant Dashboard',
        'page_intro': 'Fee inflow, dues exposure, payroll expense, and recent ledger movement.',
        'recent_announcements': visible_announcements_for_user(user=user, session=session)[:4],
        'recent_ledger_entries': recent_ledger_entries,
        'monthly_income_total': _money(
            LedgerEntry.objects.filter(
                school=school,
                session=session,
                transaction_type=LedgerEntry.TYPE_INCOME,
                date__range=(month_start, month_end),
            ).aggregate(total=Sum('amount')).get('total')
        ) if session else Decimal('0.00'),
        'monthly_expense_total': _money(
            LedgerEntry.objects.filter(
                school=school,
                session=session,
                transaction_type__in=[LedgerEntry.TYPE_EXPENSE, LedgerEntry.TYPE_REFUND],
                date__range=(month_start, month_end),
            ).aggregate(total=Sum('amount')).get('total')
        ) if session else Decimal('0.00'),
    })
    return context


def build_teacher_dashboard_context(user):
    school = user.school
    session = getattr(school, 'current_session', None)
    today = timezone.localdate()
    staff = _teacher_profile(user)

    timetable_rows = TimetableEntry.objects.none()
    pending_sections = []
    performance_rows = []
    if session and staff:
        timetable_rows = TimetableEntry.objects.filter(
            school=school,
            session=session,
            teacher=staff,
            day_of_week=_weekday_key(today),
            is_active=True,
        ).select_related('school_class', 'section', 'subject', 'period').order_by('period__period_number')

        assignments = ClassTeacher.objects.filter(
            school=school,
            session=session,
            teacher=staff,
            is_active=True,
        ).select_related('school_class', 'section').order_by('school_class__display_order', 'section__name')
        for assignment in assignments:
            already_marked = StudentAttendance.objects.filter(
                school=school,
                session=session,
                school_class=assignment.school_class,
                section=assignment.section,
                date=today,
            ).exists()
            if not already_marked:
                pending_sections.append(assignment)

        performance_rows = list(
            StudentMark.objects.filter(
                school=school,
                session=session,
                subject__teacher_subject_assignments__teacher=staff,
                subject__teacher_subject_assignments__session=session,
                subject__teacher_subject_assignments__is_active=True,
            ).values('subject__name').annotate(
                average_marks=Avg('marks_obtained'),
                entry_count=Count('id'),
            ).order_by('subject__name')
        )[:6]

    context = {
        'staff_profile': staff,
        'today_timetable': timetable_rows,
        'pending_attendance_sections': pending_sections,
        'performance_rows': performance_rows,
        'parent_messages': Message.objects.filter(
            thread__school=school,
            receiver=user,
            sender__role='parent',
        ).select_related('sender').order_by('-sent_at')[:6],
        'recent_announcements': visible_announcements_for_user(user=user, session=session)[:6],
    }
    context.update(_unread_counts(user))
    return context


def build_parent_dashboard_context(user):
    school = user.school
    session = getattr(school, 'current_session', None)
    parent_profile = _parent_profile(user)
    child_rows = []
    total_due = Decimal('0.00')
    total_attendance = Decimal('0.00')
    attendance_items = 0

    if parent_profile:
        links = ParentStudentLink.objects.filter(
            parent_user=parent_profile,
        ).select_related(
            'student',
            'student__current_class',
            'student__current_section',
        ).order_by('-is_primary', 'student__admission_number')
        if session:
            links = links.filter(student__session=session)

        for link in links:
            student = link.student
            active_session = session or student.session
            latest_summary = StudentAttendanceSummary.objects.filter(
                school=school,
                session=active_session,
                student=student,
            ).order_by('-year', '-month').first()
            latest_result = ExamResultSummary.objects.filter(
                school=school,
                session=active_session,
                student=student,
            ).select_related('exam', 'exam__exam_type').order_by('-exam__start_date', '-id').first()
            upcoming_exams = Exam.objects.filter(
                school=school,
                session=active_session,
                school_class=student.current_class,
                is_active=True,
                start_date__gte=timezone.localdate(),
            ).filter(
                Q(section__isnull=True) | Q(section=student.current_section)
            ).select_related('exam_type', 'section').order_by('start_date', 'id')[:4]
            fee_summary = student_outstanding_summary(student=student, session=active_session) if active_session else {
                'total_due': Decimal('0.00'),
                'principal_due': Decimal('0.00'),
                'fine_due': Decimal('0.00'),
            }

            total_due += fee_summary['total_due']
            if latest_summary:
                total_attendance += latest_summary.attendance_percentage
                attendance_items += 1

            child_rows.append({
                'student': student,
                'is_primary': link.is_primary,
                'attendance_summary': latest_summary,
                'latest_result': latest_result,
                'upcoming_exams': list(upcoming_exams),
                'fee_summary': fee_summary,
                'receipt_count': FeeReceipt.objects.filter(
                    school=school,
                    session=active_session,
                    student=student,
                ).count(),
            })

    average_attendance = Decimal('0.00')
    if attendance_items:
        average_attendance = _money(total_attendance / attendance_items)

    context = {
        'child_rows': child_rows,
        'average_attendance': average_attendance,
        'total_due': _money(total_due),
        'recent_announcements': visible_announcements_for_user(user=user, session=session)[:6],
        'parent_profile': parent_profile,
    }
    context.update(_unread_counts(user))
    return context


def build_super_admin_dashboard_context(user):
    school_rows = School.objects.select_related('current_session').annotate(
        total_users=Count('users', distinct=True),
        total_students=Count('students_core', distinct=True),
    ).order_by('name')

    schools_by_month = {}
    for school in school_rows:
        key = (school.created_at.year, school.created_at.month)
        schools_by_month[key] = schools_by_month.get(key, 0) + 1

    labels = []
    values = []
    for year, month, label in month_labels(end_date=timezone.localdate(), months=6):
        labels.append(label)
        values.append(schools_by_month.get((year, month), 0))

    return {
        'total_schools': School.objects.count(),
        'active_schools': School.objects.filter(is_active=True).count(),
        'total_platform_users': User.objects.count(),
        'active_sessions': AcademicSession.objects.filter(is_active=True).count(),
        'recent_schools': school_rows[:8],
        'recent_audit_logs': AuditLog.objects.select_related('school', 'user').order_by('-created_at')[:8],
        'school_growth_chart': build_line_chart(labels=labels, values=values),
        'school_activity_chart': build_bar_chart([
            {'label': row.name[:12], 'value': row.total_users, 'sub_label': f"{row.total_students} students"}
            for row in school_rows[:6]
        ]),
    }
