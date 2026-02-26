from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.schools.models import School

from .models import (
    ClassTeacher,
    Designation,
    LeaveRequest,
    SalaryHistory,
    SalaryStructure,
    Staff,
    StaffAttendance,
    TeacherSubjectAssignment,
)
from .services import mark_staff_attendance, review_leave_request, set_salary_structure, submit_leave_request


class HRBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.school = School.objects.create(name='HR School', code='hr_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='9th',
            code='IX',
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A')

        self.subject_math = Subject.objects.create(school=self.school, name='Math', code='MTH')
        self.subject_science = Subject.objects.create(school=self.school, name='Science', code='SCI')
        ClassSubject.objects.create(school_class=self.school_class, subject=self.subject_math)

        self.period = Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            is_active=True,
        )

        self.admin = user_model.objects.create_user(
            username='hr_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher_user_1 = user_model.objects.create_user(
            username='teacher1',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.teacher_user_2 = user_model.objects.create_user(
            username='teacher2',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.accountant_user = user_model.objects.create_user(
            username='account1',
            password='pass12345',
            role='accountant',
            school=self.school,
        )

        self.designation_teacher = Designation.objects.create(school=self.school, name='Teacher')
        self.designation_accountant = Designation.objects.create(school=self.school, name='Accountant')

        self.staff_teacher_1 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_1,
            employee_id='EMP-T1',
            joining_date='2026-04-10',
            designation=self.designation_teacher,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )
        self.staff_teacher_2 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_2,
            employee_id='EMP-T2',
            joining_date='2026-04-11',
            designation=self.designation_teacher,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )
        self.staff_accountant = Staff.objects.create(
            school=self.school,
            user=self.accountant_user,
            employee_id='EMP-A1',
            joining_date='2026-04-12',
            designation=self.designation_accountant,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )


class HRModelRulesTests(HRBaseTestCase):
    def test_employee_id_unique_per_school(self):
        with self.assertRaises(IntegrityError):
            Staff.objects.create(
                school=self.school,
                user=self.admin,
                employee_id='EMP-T1',
                joining_date='2026-04-15',
                designation=self.designation_teacher,
                status=Staff.STATUS_ACTIVE,
                is_active=True,
            )

    def test_teacher_subject_assignment_requires_class_subject_mapping(self):
        assignment = TeacherSubjectAssignment(
            school=self.school,
            session=self.session,
            teacher=self.staff_teacher_1,
            school_class=self.school_class,
            subject=self.subject_science,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_class_teacher_reassignment_auto_deactivates_old_assignment(self):
        first = ClassTeacher.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            teacher=self.staff_teacher_1,
            is_active=True,
        )
        second = ClassTeacher.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            teacher=self.staff_teacher_2,
            is_active=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)

    def test_leave_request_cannot_overlap(self):
        LeaveRequest.objects.create(
            school=self.school,
            staff=self.staff_teacher_1,
            leave_type=LeaveRequest.TYPE_CASUAL,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 22),
            reason='Personal',
            status=LeaveRequest.STATUS_PENDING,
        )

        leave = LeaveRequest(
            school=self.school,
            staff=self.staff_teacher_1,
            leave_type=LeaveRequest.TYPE_SICK,
            start_date=date(2026, 4, 21),
            end_date=date(2026, 4, 23),
            reason='Health',
            status=LeaveRequest.STATUS_PENDING,
        )
        with self.assertRaises(ValidationError):
            leave.full_clean()


class HRServiceTests(HRBaseTestCase):
    def test_mark_attendance_blocks_edit_after_window_without_override(self):
        attendance, created = mark_staff_attendance(
            school=self.school,
            staff=self.staff_teacher_1,
            date=date(2026, 4, 15),
            status=StaffAttendance.STATUS_PRESENT,
            marked_by=self.staff_teacher_1.user,
            check_in_time=timezone.datetime.strptime('09:00', '%H:%M').time(),
            check_out_time=timezone.datetime.strptime('17:00', '%H:%M').time(),
        )
        self.assertTrue(created)

        attendance.created_at = timezone.now() - timedelta(hours=7)
        attendance.save(update_fields=['created_at'])

        with self.assertRaises(ValidationError):
            mark_staff_attendance(
                school=self.school,
                staff=self.staff_teacher_1,
                date=date(2026, 4, 15),
                status=StaffAttendance.STATUS_HALF_DAY,
                marked_by=self.admin,
                check_in_time=timezone.datetime.strptime('09:00', '%H:%M').time(),
                check_out_time=timezone.datetime.strptime('13:00', '%H:%M').time(),
                allow_override=False,
            )

    def test_approved_leave_auto_adjusts_attendance(self):
        leave = submit_leave_request(
            school=self.school,
            staff=self.staff_teacher_1,
            leave_type=LeaveRequest.TYPE_CASUAL,
            start_date=date(2026, 4, 16),
            end_date=date(2026, 4, 17),
            reason='Family event',
        )
        review_leave_request(
            leave_request=leave,
            approved_by=self.admin,
            decision=LeaveRequest.STATUS_APPROVED,
        )

        records = StaffAttendance.objects.filter(
            school=self.school,
            staff=self.staff_teacher_1,
            date__range=(date(2026, 4, 16), date(2026, 4, 17)),
        )
        self.assertEqual(records.count(), 2)
        self.assertTrue(all(rec.status == StaffAttendance.STATUS_LEAVE for rec in records))

    def test_set_salary_structure_keeps_one_active_and_logs_history(self):
        first_structure, _ = set_salary_structure(
            school=self.school,
            staff=self.staff_teacher_1,
            basic_salary=Decimal('30000.00'),
            allowances={'hra': 1000},
            deductions={'pf': 500},
            effective_from=date(2026, 4, 1),
            changed_by=self.admin,
            reason='Initial setup',
        )
        second_structure, _ = set_salary_structure(
            school=self.school,
            staff=self.staff_teacher_1,
            basic_salary=Decimal('35000.00'),
            allowances={'hra': 1500},
            deductions={'pf': 600},
            effective_from=date(2026, 7, 1),
            changed_by=self.admin,
            reason='Increment',
        )

        first_structure.refresh_from_db()
        second_structure.refresh_from_db()

        self.assertFalse(first_structure.is_active)
        self.assertTrue(second_structure.is_active)
        self.assertEqual(SalaryHistory.objects.filter(staff=self.staff_teacher_1).count(), 2)


class HRViewTests(HRBaseTestCase):
    def test_schooladmin_can_create_staff(self):
        user_model = get_user_model()
        new_user = user_model.objects.create_user(
            username='teacher3',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

        self.client.login(username='hr_admin', password='pass12345')
        response = self.client.post(reverse('hr_staff_create'), {
            'user': new_user.id,
            'employee_id': 'EMP-T3',
            'joining_date': '2026-04-20',
            'designation': self.designation_teacher.id,
            'department': 'Academics',
            'qualification': 'B.Ed',
            'experience_years': '2.0',
            'phone': '9999999999',
            'address': 'City',
            'status': Staff.STATUS_ACTIVE,
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Staff.objects.filter(school=self.school, employee_id='EMP-T3').exists())

    def test_teacher_can_mark_own_attendance(self):
        self.client.login(username='teacher1', password='pass12345')
        response = self.client.post(reverse('hr_staff_attendance_mark'), {
            'staff': self.staff_teacher_1.id,
            'date': '2026-04-18',
            'check_in_time': '09:00',
            'check_out_time': '17:00',
            'status': StaffAttendance.STATUS_PRESENT,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            StaffAttendance.objects.filter(
                school=self.school,
                staff=self.staff_teacher_1,
                date='2026-04-18',
            ).exists()
        )

    def test_teacher_cannot_access_staff_management_pages(self):
        self.client.login(username='teacher1', password='pass12345')
        response = self.client.get(reverse('hr_staff_list'))
        self.assertEqual(response.status_code, 403)

    def test_schooladmin_can_review_leave_request(self):
        leave = LeaveRequest.objects.create(
            school=self.school,
            staff=self.staff_teacher_1,
            leave_type=LeaveRequest.TYPE_SICK,
            start_date='2026-04-25',
            end_date='2026-04-25',
            reason='Fever',
            status=LeaveRequest.STATUS_PENDING,
        )

        self.client.login(username='hr_admin', password='pass12345')
        response = self.client.post(reverse('hr_leave_request_review', args=[leave.id]), {
            'decision': LeaveRequest.STATUS_APPROVED,
        })

        self.assertEqual(response.status_code, 302)
        leave.refresh_from_db()
        self.assertEqual(leave.status, LeaveRequest.STATUS_APPROVED)
