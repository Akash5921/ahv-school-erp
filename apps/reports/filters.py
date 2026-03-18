from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta

from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.exams.models import Exam
from apps.core.hr.models import Staff
from apps.core.students.models import Student, StudentSessionRecord


@dataclass
class ReportFilters:
    school: object
    session: AcademicSession | None
    school_class: SchoolClass | None
    section: Section | None
    student: Student | None
    staff: Staff | None
    exam: Exam | None
    date_from: object
    date_to: object
    month: int
    year: int
    export_format: str
    sessions: object
    classes: object
    sections: object
    students: object
    staff_members: object
    exams: object

    @property
    def read_only(self):
        return bool(self.session and (self.session.attendance_locked or self.session.is_locked))


def _pick(queryset, raw_value):
    if raw_value and str(raw_value).isdigit():
        return queryset.filter(id=int(raw_value)).first()
    return None


def _to_int(raw_value, default):
    if str(raw_value or '').isdigit():
        return int(raw_value)
    return default


def build_report_filters(request, school):
    today = timezone.localdate()
    date_from = today - timedelta(days=30)
    date_to = today

    if request.GET.get('date_from'):
        parsed = datetime.strptime(request.GET['date_from'], '%Y-%m-%d').date()
        date_from = parsed
    if request.GET.get('date_to'):
        parsed = datetime.strptime(request.GET['date_to'], '%Y-%m-%d').date()
        date_to = parsed
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    month = _to_int(request.GET.get('month'), today.month)
    year = _to_int(request.GET.get('year'), today.year)

    sessions = AcademicSession.objects.filter(school=school).order_by('-start_date')
    session = _pick(sessions, request.GET.get('session'))
    if not session and school.current_session_id:
        session = sessions.filter(id=school.current_session_id).first()

    classes = SchoolClass.objects.filter(
        school=school,
        session=session,
        is_active=True,
    ).order_by('display_order', 'name') if session else SchoolClass.objects.none()
    school_class = _pick(classes, request.GET.get('school_class'))

    sections = Section.objects.filter(
        school_class=school_class,
        is_active=True,
    ).order_by('name') if school_class else Section.objects.none()
    section = _pick(sections, request.GET.get('section'))

    students = Student.objects.filter(
        school=school,
        session=session,
        is_archived=False,
        is_active=True,
    ).select_related('current_class', 'current_section').order_by('admission_number') if session else Student.objects.none()
    if school_class:
        students = students.filter(current_class=school_class)
    if section:
        students = students.filter(current_section=section)
    student = _pick(students, request.GET.get('student'))

    staff_members = Staff.objects.filter(
        school=school,
        is_active=True,
        status=Staff.STATUS_ACTIVE,
    ).select_related('user').order_by('employee_id')
    staff = _pick(staff_members, request.GET.get('staff'))

    exams = Exam.objects.filter(
        school=school,
        session=session,
        is_active=True,
    ).select_related('exam_type', 'school_class', 'section').order_by('-start_date', '-id') if session else Exam.objects.none()
    if school_class:
        exams = exams.filter(school_class=school_class)
    if section:
        exams = exams.filter(section=section)
    exam = _pick(exams, request.GET.get('exam'))

    return ReportFilters(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        student=student,
        staff=staff,
        exam=exam,
        date_from=date_from,
        date_to=date_to,
        month=month,
        year=year,
        export_format=(request.GET.get('export') or '').lower(),
        sessions=sessions,
        classes=classes,
        sections=sections,
        students=students[:200],
        staff_members=staff_members[:200],
        exams=exams[:100],
    )


def scoped_student_records(filters: ReportFilters):
    rows = StudentSessionRecord.objects.filter(
        school=filters.school,
        student__is_archived=False,
        student__is_active=True,
    ).select_related(
        'student',
        'school_class',
        'section',
    )
    if filters.session:
        rows = rows.filter(session=filters.session)
    if filters.school_class:
        rows = rows.filter(school_class=filters.school_class)
    if filters.section:
        rows = rows.filter(section=filters.section)
    if filters.student:
        rows = rows.filter(student=filters.student)
    return rows


def scoped_students(filters: ReportFilters):
    rows = Student.objects.filter(
        school=filters.school,
        is_archived=False,
        is_active=True,
    ).select_related('current_class', 'current_section')
    if filters.session:
        rows = rows.filter(session=filters.session)
    if filters.school_class:
        rows = rows.filter(current_class=filters.school_class)
    if filters.section:
        rows = rows.filter(current_section=filters.section)
    if filters.student:
        rows = rows.filter(id=filters.student.id)
    return rows


def scoped_staff(filters: ReportFilters):
    rows = Staff.objects.filter(
        school=filters.school,
        is_active=True,
        status=Staff.STATUS_ACTIVE,
    ).select_related('user', 'designation')
    if filters.staff:
        rows = rows.filter(id=filters.staff.id)
    return rows
