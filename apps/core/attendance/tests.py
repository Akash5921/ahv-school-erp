from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import AcademicConfig, ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.hr.models import ClassTeacher, Designation, Staff, Substitution, TeacherSubjectAssignment
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.timetable.models import TimetableEntry

from .models import StudentAttendance, StudentAttendanceSummary, StudentPeriodAttendance
from .services import (
    calculate_student_monthly_summary,
    lock_attendance_records,
    mark_student_daily_attendance_bulk,
    mark_student_period_attendance_bulk,
)


class AttendanceBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()
        self.session_start = self.today - timedelta(days=90)
        self.session_end = self.today + timedelta(days=90)
        self.monday = self.today - timedelta(days=self.today.weekday())
        if self.monday < self.session_start:
            self.monday = self.session_start

        self.school = School.objects.create(name='Attendance School', code='attendance_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.session_start,
            end_date=self.session_end,
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='8th',
            code='VIII',
            display_order=8,
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A')

        self.subject = Subject.objects.create(school=self.school, name='Math', code='MTH')
        ClassSubject.objects.create(school_class=self.school_class, subject=self.subject)

        self.period_1 = Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:40',
            is_active=True,
        )

        self.admin_user = user_model.objects.create_user(
            username='attendance_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher_user_1 = user_model.objects.create_user(
            username='attendance_teacher_1',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.teacher_user_2 = user_model.objects.create_user(
            username='attendance_teacher_2',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

        designation = Designation.objects.create(school=self.school, name='Teacher')
        self.teacher_1 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_1,
            employee_id='AT-T1',
            joining_date=self.session_start,
            designation=designation,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )
        self.teacher_2 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_2,
            employee_id='AT-T2',
            joining_date=self.session_start,
            designation=designation,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )

        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_1,
            school_class=self.school_class,
            subject=self.subject,
            is_active=True,
        )
        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_2,
            school_class=self.school_class,
            subject=self.subject,
            is_active=True,
        )
        ClassTeacher.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            teacher=self.teacher_1,
            is_active=True,
        )

        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject,
            teacher=self.teacher_1,
            is_active=True,
        )

        self.student_1 = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='AT-S1',
            first_name='Aarav',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number='1',
        )
        self.student_2 = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='AT-S2',
            first_name='Diya',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number='2',
        )

        StudentSessionRecord.objects.create(
            student=self.student_1,
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            roll_number='1',
            is_current=True,
        )
        StudentSessionRecord.objects.create(
            student=self.student_2,
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            roll_number='2',
            is_current=True,
        )


class AttendanceServiceTests(AttendanceBaseTestCase):
    def test_class_teacher_can_mark_daily_attendance(self):
        records = mark_student_daily_attendance_bulk(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            target_date=self.today,
            status_by_student_id={
                self.student_1.id: StudentAttendance.STATUS_PRESENT,
                self.student_2.id: StudentAttendance.STATUS_ABSENT,
            },
            marked_by=self.teacher_user_1,
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(
            StudentAttendance.objects.filter(
                school=self.school,
                session=self.session,
                date=self.today,
            ).count(),
            2,
        )

    def test_non_class_teacher_cannot_mark_daily_attendance(self):
        with self.assertRaises(ValidationError):
            mark_student_daily_attendance_bulk(
                school=self.school,
                session=self.session,
                school_class=self.school_class,
                section=self.section,
                target_date=self.today,
                status_by_student_id={
                    self.student_1.id: StudentAttendance.STATUS_PRESENT,
                    self.student_2.id: StudentAttendance.STATUS_PRESENT,
                },
                marked_by=self.teacher_user_2,
            )

    def test_substitute_teacher_can_mark_period_attendance(self):
        Substitution.objects.create(
            school=self.school,
            session=self.session,
            date=self.monday,
            period=self.period_1,
            school_class=self.school_class,
            section=self.section,
            subject=self.subject,
            original_teacher=self.teacher_1,
            substitute_teacher=self.teacher_2,
            is_active=True,
        )

        records, _ = mark_student_period_attendance_bulk(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            target_date=self.monday,
            period=self.period_1,
            status_by_student_id={
                self.student_1.id: StudentAttendance.STATUS_PRESENT,
                self.student_2.id: StudentAttendance.STATUS_LATE,
            },
            marked_by=self.teacher_user_2,
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(
            StudentPeriodAttendance.objects.filter(
                school=self.school,
                session=self.session,
                date=self.monday,
                period=self.period_1,
            ).count(),
            2,
        )

        with self.assertRaises(ValidationError):
            mark_student_period_attendance_bulk(
                school=self.school,
                session=self.session,
                school_class=self.school_class,
                section=self.section,
                target_date=self.monday,
                period=self.period_1,
                status_by_student_id={
                    self.student_1.id: StudentAttendance.STATUS_PRESENT,
                    self.student_2.id: StudentAttendance.STATUS_PRESENT,
                },
                marked_by=self.teacher_user_1,
            )

    def test_lock_blocks_teacher_edit_but_admin_override_works(self):
        mark_student_daily_attendance_bulk(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            target_date=self.today,
            status_by_student_id={
                self.student_1.id: StudentAttendance.STATUS_PRESENT,
                self.student_2.id: StudentAttendance.STATUS_PRESENT,
            },
            marked_by=self.teacher_user_1,
        )

        lock_attendance_records(
            school=self.school,
            session=self.session,
            target_date=self.today,
            school_class=self.school_class,
            section=self.section,
        )

        with self.assertRaises(ValidationError):
            mark_student_daily_attendance_bulk(
                school=self.school,
                session=self.session,
                school_class=self.school_class,
                section=self.section,
                target_date=self.today,
                status_by_student_id={
                    self.student_1.id: StudentAttendance.STATUS_ABSENT,
                    self.student_2.id: StudentAttendance.STATUS_PRESENT,
                },
                marked_by=self.teacher_user_1,
                allow_override=False,
            )

        mark_student_daily_attendance_bulk(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            target_date=self.today,
            status_by_student_id={
                self.student_1.id: StudentAttendance.STATUS_ABSENT,
                self.student_2.id: StudentAttendance.STATUS_PRESENT,
            },
            marked_by=self.admin_user,
            allow_override=True,
        )

        record = StudentAttendance.objects.get(student=self.student_1, date=self.today)
        self.assertEqual(record.status, StudentAttendance.STATUS_ABSENT)

    def test_monthly_summary_creation(self):
        day_one = self.today - timedelta(days=2)
        day_two = self.today - timedelta(days=1)
        StudentAttendance.objects.create(
            school=self.school,
            session=self.session,
            student=self.student_1,
            school_class=self.school_class,
            section=self.section,
            date=day_one,
            status=StudentAttendance.STATUS_PRESENT,
            marked_by=self.teacher_user_1,
        )
        StudentAttendance.objects.create(
            school=self.school,
            session=self.session,
            student=self.student_1,
            school_class=self.school_class,
            section=self.section,
            date=day_two,
            status=StudentAttendance.STATUS_LATE,
            marked_by=self.teacher_user_1,
        )

        summary = calculate_student_monthly_summary(
            student=self.student_1,
            session=self.session,
            year=self.today.year,
            month=self.today.month,
        )
        self.assertIsInstance(summary, StudentAttendanceSummary)
        self.assertGreaterEqual(summary.present_days, 2)


class AttendanceViewTests(AttendanceBaseTestCase):
    def test_schooladmin_can_mark_daily_attendance_from_view(self):
        self.client.login(username='attendance_admin', password='pass12345')
        response = self.client.post(
            reverse('attendance_student_daily_mark'),
            {
                'session': self.session.id,
                'school_class': self.school_class.id,
                'section': self.section.id,
                'target_date': self.today.isoformat(),
                f'status_{self.student_1.id}': StudentAttendance.STATUS_PRESENT,
                f'status_{self.student_2.id}': StudentAttendance.STATUS_ABSENT,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            StudentAttendance.objects.filter(
                school=self.school,
                session=self.session,
                date=self.today,
                student=self.student_1,
            ).exists()
        )

    def test_teacher_cannot_access_lock_management(self):
        self.client.login(username='attendance_teacher_1', password='pass12345')
        response = self.client.get(reverse('attendance_lock_manage'))
        self.assertEqual(response.status_code, 403)

    def test_class_report_csv_export(self):
        AcademicConfig.objects.create(
            school=self.school,
            session=self.session,
            total_periods_per_day=6,
            working_days=['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'],
            grading_enabled=True,
            attendance_type=AcademicConfig.ATTENDANCE_DAILY,
            marks_decimal_allowed=False,
        )
        StudentAttendance.objects.create(
            school=self.school,
            session=self.session,
            student=self.student_1,
            school_class=self.school_class,
            section=self.section,
            date=self.today,
            status=StudentAttendance.STATUS_PRESENT,
            marked_by=self.teacher_user_1,
        )

        self.client.login(username='attendance_admin', password='pass12345')
        response = self.client.get(
            reverse('attendance_report_class'),
            {
                'session': self.session.id,
                'school_class': self.school_class.id,
                'section': self.section.id,
                'date_from': self.today.isoformat(),
                'date_to': self.today.isoformat(),
                'export': 'csv',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
