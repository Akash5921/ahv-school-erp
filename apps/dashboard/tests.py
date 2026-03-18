from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.attendance.models import StudentAttendanceSummary
from apps.core.communication.models import (
    Announcement,
    Message,
    MessageThread,
    MessageThreadParticipant,
    Notification,
    ParentStudentLink,
    ParentUser,
)
from apps.core.exams.models import Exam, ExamResultSummary, ExamSubject, ExamType, StudentMark
from apps.core.fees.models import FeePayment, FeePaymentAllocation, FeeReceipt, FeeType, Installment, LedgerEntry, StudentFee
from apps.core.hr.models import ClassTeacher, Designation, Payroll, Staff, TeacherSubjectAssignment
from apps.core.schools.models import School
from apps.core.students.models import Parent, Student, StudentSessionRecord
from apps.core.timetable.models import TimetableEntry


class DashboardBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()

        self.school = School.objects.create(name='Phase 11 School', code='phase11_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.today - timedelta(days=90),
            end_date=self.today + timedelta(days=240),
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_admin = user_model.objects.create_user(
            username='phase11_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.principal = user_model.objects.create_user(
            username='phase11_principal',
            password='pass12345',
            role='principal',
            school=self.school,
        )
        self.teacher_user = user_model.objects.create_user(
            username='phase11_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
            email='teacher@example.com',
        )
        self.accountant_user = user_model.objects.create_user(
            username='phase11_accountant',
            password='pass12345',
            role='accountant',
            school=self.school,
        )
        self.parent_user = user_model.objects.create_user(
            username='phase11_parent',
            password='pass12345',
            role='parent',
            school=self.school,
            email='parent@example.com',
        )
        self.superadmin = user_model.objects.create_user(
            username='phase11_superadmin',
            password='pass12345',
            role='superadmin',
        )

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='8th',
            code='VIII',
            display_order=8,
            is_active=True,
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A', is_active=True)
        self.subject = Subject.objects.create(school=self.school, name='Mathematics', code='MTH')
        ClassSubject.objects.create(school_class=self.school_class, subject=self.subject)
        self.period = Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            is_active=True,
        )

        teacher_designation = Designation.objects.create(school=self.school, name='Teacher')
        accountant_designation = Designation.objects.create(school=self.school, name='Accountant')
        self.teacher_staff = Staff.objects.create(
            school=self.school,
            user=self.teacher_user,
            employee_id='T-001',
            joining_date=self.today - timedelta(days=60),
            designation=teacher_designation,
            department='Academics',
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )
        self.accountant_staff = Staff.objects.create(
            school=self.school,
            user=self.accountant_user,
            employee_id='A-001',
            joining_date=self.today - timedelta(days=60),
            designation=accountant_designation,
            department='Accounts',
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )

        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_staff,
            school_class=self.school_class,
            subject=self.subject,
            is_active=True,
        )
        ClassTeacher.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            teacher=self.teacher_staff,
            is_active=True,
        )
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            day_of_week=['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][self.today.weekday()],
            period=self.period,
            subject=self.subject,
            teacher=self.teacher_staff,
            is_active=True,
        )

        self.student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='STU-001',
            first_name='Aarav',
            current_class=self.school_class,
            current_section=self.section,
            roll_number='1',
            admission_type=Student.ADMISSION_FRESH,
        )
        StudentSessionRecord.objects.create(
            student=self.student,
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            roll_number='1',
            is_current=True,
        )
        StudentAttendanceSummary.objects.create(
            school=self.school,
            session=self.session,
            student=self.student,
            year=self.today.year,
            month=self.today.month,
            total_working_days=20,
            present_days=18,
            attendance_percentage=Decimal('90.00'),
        )

        parent_info = Parent.objects.create(
            student=self.student,
            father_name='Guardian',
            phone='9999999999',
            email='family@example.com',
        )
        parent_profile = ParentUser.objects.create(
            school=self.school,
            user=self.parent_user,
            parent_info=parent_info,
            is_active=True,
        )
        ParentStudentLink.objects.create(
            parent_user=parent_profile,
            student=self.student,
            is_primary=True,
        )

        Announcement.objects.create(
            school=self.school,
            session=self.session,
            title='Welcome Back',
            message='Dashboard announcement',
            target_role=Announcement.ROLE_ALL,
            created_by=self.school_admin,
        )
        Notification.objects.create(
            school=self.school,
            session=self.session,
            user=self.teacher_user,
            title='Teacher Notification',
            message='Unread notification',
        )
        Notification.objects.create(
            school=self.school,
            session=self.session,
            user=self.parent_user,
            title='Parent Notification',
            message='Unread parent notification',
        )

        thread = MessageThread.objects.create(
            school=self.school,
            session=self.session,
            subject='Parent concern',
            created_by=self.parent_user,
        )
        MessageThreadParticipant.objects.create(thread=thread, user=self.parent_user)
        MessageThreadParticipant.objects.create(thread=thread, user=self.teacher_user)
        Message.objects.create(
            thread=thread,
            sender=self.parent_user,
            receiver=self.teacher_user,
            message_text='Please share the homework plan.',
        )

        exam_type = ExamType.objects.create(
            school=self.school,
            session=self.session,
            name='Mid Term',
            is_active=True,
        )
        self.exam = Exam.objects.create(
            school=self.school,
            session=self.session,
            exam_type=exam_type,
            school_class=self.school_class,
            section=self.section,
            start_date=self.today + timedelta(days=7),
            end_date=self.today + timedelta(days=10),
            is_locked=True,
            is_active=True,
            created_by=self.school_admin,
        )
        ExamSubject.objects.create(
            exam=self.exam,
            subject=self.subject,
            max_marks=Decimal('100.00'),
            pass_marks=Decimal('35.00'),
            is_active=True,
        )
        StudentMark.objects.create(
            school=self.school,
            session=self.session,
            student=self.student,
            exam=self.exam,
            subject=self.subject,
            marks_obtained=Decimal('88.00'),
            grade='A',
            entered_by=self.teacher_user,
            is_locked=True,
        )
        ExamResultSummary.objects.create(
            school=self.school,
            session=self.session,
            student=self.student,
            exam=self.exam,
            total_marks=Decimal('88.00'),
            percentage=Decimal('88.00'),
            grade='A',
            rank=1,
            attendance_percentage=Decimal('90.00'),
            result_status=ExamResultSummary.STATUS_PASS,
            is_locked=True,
        )

        fee_type = FeeType.objects.create(
            school=self.school,
            name='Tuition',
            category=FeeType.CATEGORY_ACADEMIC,
            is_active=True,
        )
        installment = Installment.objects.create(
            school=self.school,
            session=self.session,
            name='Quarter 1',
            due_date=self.today,
            fine_per_day=Decimal('0.00'),
            is_active=True,
        )
        student_fee = StudentFee.objects.create(
            school=self.school,
            session=self.session,
            student=self.student,
            fee_type=fee_type,
            assigned_class=self.school_class,
            total_amount=Decimal('1000.00'),
            concession_amount=Decimal('0.00'),
            final_amount=Decimal('1000.00'),
            is_active=True,
        )
        payment = FeePayment.objects.create(
            school=self.school,
            session=self.session,
            student=self.student,
            installment=installment,
            amount_paid=Decimal('400.00'),
            fine_amount=Decimal('0.00'),
            payment_date=self.today,
            payment_mode=FeePayment.MODE_CASH,
            received_by=self.accountant_user,
        )
        FeePaymentAllocation.objects.create(
            payment=payment,
            student_fee=student_fee,
            amount=Decimal('400.00'),
        )
        FeeReceipt.objects.create(
            receipt_number='RCP-1',
            school=self.school,
            session=self.session,
            student=self.student,
            payment=payment,
        )
        LedgerEntry.objects.create(
            school=self.school,
            session=self.session,
            transaction_type=LedgerEntry.TYPE_INCOME,
            reference_model='FeePayment',
            reference_id=str(payment.id),
            amount=Decimal('400.00'),
            date=self.today,
            description='Fee payment',
            created_by=self.accountant_user,
        )

        payroll = Payroll.objects.create(
            school=self.school,
            session=self.session,
            staff=self.accountant_staff,
            month=self.today.month,
            year=self.today.year,
            gross_salary=Decimal('3000.00'),
            attendance_deduction=Decimal('0.00'),
            leave_deduction=Decimal('0.00'),
            advance_deduction=Decimal('0.00'),
            total_deductions=Decimal('0.00'),
            net_salary=Decimal('3000.00'),
            total_working_days=Decimal('20.00'),
            present_days=Decimal('20.00'),
            absent_days=Decimal('0.00'),
            processed_by=self.school_admin,
            is_locked=True,
            is_paid=False,
            is_on_hold=False,
            attendance_snapshot={},
            salary_snapshot={},
        )
        LedgerEntry.objects.create(
            school=self.school,
            session=self.session,
            transaction_type=LedgerEntry.TYPE_EXPENSE,
            reference_model='Payroll',
            reference_id=str(payroll.id),
            amount=Decimal('3000.00'),
            date=self.today,
            description='Payroll expense',
            created_by=self.school_admin,
        )


class DashboardViewTests(DashboardBaseTestCase):
    def test_school_admin_dashboard_shows_phase11_metrics(self):
        self.client.login(username='phase11_admin', password='pass12345')
        response = self.client.get(reverse('school_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fee Collection Trend')
        self.assertContains(response, 'Class Strength')
        self.assertContains(response, 'Welcome Back')

    def test_teacher_dashboard_shows_timetable_and_parent_messages(self):
        self.client.login(username='phase11_teacher', password='pass12345')
        response = self.client.get(reverse('dashboard_teacher'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teacher Dashboard')
        self.assertContains(response, 'Mathematics')
        self.assertContains(response, 'Please share the homework plan.')

    def test_parent_dashboard_shows_child_overview(self):
        self.client.login(username='phase11_parent', password='pass12345')
        response = self.client.get(reverse('dashboard_parent'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Parent Dashboard')
        self.assertContains(response, 'Aarav')
        self.assertContains(response, '600.00')

    def test_principal_and_accountant_dashboards_are_accessible(self):
        self.client.login(username='phase11_principal', password='pass12345')
        principal_response = self.client.get(reverse('dashboard_principal'))
        self.assertEqual(principal_response.status_code, 200)
        self.assertContains(principal_response, 'Principal Dashboard')

        self.client.login(username='phase11_accountant', password='pass12345')
        accountant_response = self.client.get(reverse('dashboard_accountant'))
        self.assertEqual(accountant_response.status_code, 200)
        self.assertContains(accountant_response, 'Accountant Dashboard')

    def test_superadmin_dashboard_loads(self):
        self.client.login(username='phase11_superadmin', password='pass12345')
        response = self.client.get(reverse('dashboard_super_admin'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Platform Dashboard')
