from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.attendance.models import StudentAttendance
from apps.core.exams.models import Exam, ExamType
from apps.core.fees.models import ClassFeeStructure, FeeType
from apps.core.fees.services import sync_student_fees_for_student
from apps.core.hr.models import ClassTeacher, Designation, LeaveRequest, Payroll, Staff
from apps.core.schools.models import School
from apps.core.students.models import Parent, Student, StudentSessionRecord

from .models import Announcement, EmailLog, GlobalSettings, Notification, ParentStudentLink, ParentUser, SMSLog
from .services import (
    bulk_email_for_class_section,
    bulk_sms_for_class_section,
    can_user_message,
    create_message_thread,
    run_fee_overdue_notifications,
    send_sms_notification,
)


class CommunicationBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()

        self.school = School.objects.create(name='Comm School', code='comm_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.today - timedelta(days=90),
            end_date=self.today + timedelta(days=270),
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='7th',
            code='VII',
            display_order=7,
            is_active=True,
        )
        self.section = Section.objects.create(
            school_class=self.school_class,
            name='A',
            is_active=True,
        )

        self.admin_user = user_model.objects.create_user(
            username='comm_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher_user = user_model.objects.create_user(
            username='comm_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
            email='teacher@example.com',
        )
        self.parent_user = user_model.objects.create_user(
            username='comm_parent',
            password='pass12345',
            role='parent',
            school=self.school,
            email='parent@example.com',
        )
        self.accountant_user = user_model.objects.create_user(
            username='comm_accountant',
            password='pass12345',
            role='accountant',
            school=self.school,
        )

        designation = Designation.objects.create(school=self.school, name='Teacher')
        self.teacher_staff = Staff.objects.create(
            school=self.school,
            user=self.teacher_user,
            employee_id='COMM-T1',
            joining_date=self.today - timedelta(days=30),
            designation=designation,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )

        self.student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='COMM-001',
            first_name='Anaya',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number='1',
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

        self.parent_info = Parent.objects.create(
            student=self.student,
            father_name='Father Name',
            phone='9999999999',
            email='family@example.com',
        )

        self.parent_profile = ParentUser.objects.create(
            school=self.school,
            user=self.parent_user,
            parent_info=self.parent_info,
            is_active=True,
        )
        ParentStudentLink.objects.create(
            parent_user=self.parent_profile,
            student=self.student,
            is_primary=True,
        )

        ClassTeacher.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            teacher=self.teacher_staff,
            is_active=True,
        )


class CommunicationSignalsTests(CommunicationBaseTestCase):
    def test_student_absent_signal_creates_parent_notification(self):
        with self.captureOnCommitCallbacks(execute=True):
            StudentAttendance.objects.create(
                school=self.school,
                session=self.session,
                student=self.student,
                school_class=self.school_class,
                section=self.section,
                date=self.today,
                status=StudentAttendance.STATUS_ABSENT,
                marked_by=self.teacher_user,
            )

        self.assertTrue(
            Notification.objects.filter(
                school=self.school,
                user=self.parent_user,
                related_model='StudentAttendance',
            ).exists()
        )

    def test_leave_approved_signal_creates_staff_notification(self):
        leave = LeaveRequest.objects.create(
            school=self.school,
            staff=self.teacher_staff,
            leave_type=LeaveRequest.TYPE_CASUAL,
            start_date=self.today,
            end_date=self.today,
            reason='Personal',
            status=LeaveRequest.STATUS_PENDING,
        )

        with self.captureOnCommitCallbacks(execute=True):
            leave.status = LeaveRequest.STATUS_APPROVED
            leave.approved_by = self.admin_user
            leave.approved_at = timezone.now()
            leave.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        self.assertTrue(
            Notification.objects.filter(
                school=self.school,
                user=self.teacher_user,
                related_model='LeaveRequest',
            ).exists()
        )

    def test_exam_locked_signal_creates_parent_notification(self):
        exam_type = ExamType.objects.create(
            school=self.school,
            session=self.session,
            name='Mid Term',
            is_active=True,
        )
        exam = Exam.objects.create(
            school=self.school,
            session=self.session,
            exam_type=exam_type,
            school_class=self.school_class,
            section=self.section,
            start_date=self.today,
            end_date=self.today,
            is_locked=False,
            created_by=self.admin_user,
        )

        with self.captureOnCommitCallbacks(execute=True):
            exam.is_locked = True
            exam.save(update_fields=['is_locked', 'updated_at'])

        self.assertTrue(
            Notification.objects.filter(
                school=self.school,
                user=self.parent_user,
                related_model='Exam',
            ).exists()
        )

    def test_payroll_created_signal_creates_staff_notification(self):
        with self.captureOnCommitCallbacks(execute=True):
            payroll = Payroll.objects.create(
                school=self.school,
                session=self.session,
                staff=self.teacher_staff,
                month=self.today.month,
                year=self.today.year,
                gross_salary='1000.00',
                attendance_deduction='0.00',
                leave_deduction='0.00',
                advance_deduction='0.00',
                total_deductions='0.00',
                net_salary='1000.00',
                total_working_days='22.00',
                present_days='22.00',
                absent_days='0.00',
                processed_by=self.admin_user,
            )

        self.assertTrue(
            Notification.objects.filter(
                school=self.school,
                user=self.teacher_user,
                related_model='Payroll',
                related_id=str(payroll.id),
            ).exists()
        )


class CommunicationServiceTests(CommunicationBaseTestCase):
    def test_parent_teacher_can_message(self):
        self.assertTrue(can_user_message(sender=self.parent_user, receiver=self.teacher_user))
        self.assertFalse(can_user_message(sender=self.parent_user, receiver=self.accountant_user))

        thread = create_message_thread(
            school=self.school,
            session=self.session,
            subject='Attendance update',
            created_by=self.parent_user,
            initial_receiver=self.teacher_user,
            message_text='Please share today attendance status.',
        )
        self.assertEqual(thread.messages.count(), 1)

    def test_parent_cannot_message_unlinked_role(self):
        with self.assertRaises(ValidationError):
            create_message_thread(
                school=self.school,
                session=self.session,
                subject='Fee query',
                created_by=self.parent_user,
                initial_receiver=self.accountant_user,
                message_text='Can we discuss fee?',
            )

    def test_teacher_cannot_message_unrelated_accountant(self):
        self.assertFalse(can_user_message(sender=self.teacher_user, receiver=self.accountant_user))

        with self.assertRaises(ValidationError):
            create_message_thread(
                school=self.school,
                session=self.session,
                subject='Internal note',
                created_by=self.teacher_user,
                initial_receiver=self.accountant_user,
                message_text='Please review this.',
            )

    def test_notification_history_cannot_be_deleted(self):
        notification = Notification.objects.create(
            school=self.school,
            session=self.session,
            user=self.parent_user,
            title='History item',
            message='Keep this stored.',
        )

        with self.assertRaises(ValidationError):
            notification.delete()

    def test_bulk_email_requires_configured_channel(self):
        with self.assertRaises(ValidationError):
            bulk_email_for_class_section(
                school=self.school,
                session=self.session,
                school_class=self.school_class,
                subject='Fee reminder',
                message='Please clear the due amount.',
                triggered_by=self.admin_user,
            )

    @patch('apps.core.communication.services.EmailMessage.send', return_value=1)
    def test_bulk_email_creates_sent_logs_when_configured(self, mock_send):
        GlobalSettings.objects.create(
            school=self.school,
            email_enabled=True,
            smtp_host='smtp.example.com',
            smtp_port=587,
            smtp_from_email='noreply@example.com',
        )

        logs = bulk_email_for_class_section(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            subject='Fee reminder',
            message='Please clear the due amount.',
            triggered_by=self.admin_user,
        )

        self.assertEqual(len(logs), 2)
        self.assertTrue(all(row.status == EmailLog.STATUS_SENT for row in logs))
        self.assertEqual(mock_send.call_count, 2)

    @patch('apps.core.communication.services.url_request.urlopen')
    def test_bulk_sms_creates_sent_logs_when_configured(self, mock_urlopen):
        response = MagicMock()
        response.status = 200
        mock_urlopen.return_value.__enter__.return_value = response

        GlobalSettings.objects.create(
            school=self.school,
            sms_enabled=True,
            sms_api_url='https://sms.example.com/send',
            sms_api_key='test-key',
            sms_sender_id='AHVERP',
        )

        logs = bulk_sms_for_class_section(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            message='School transport delayed.',
            triggered_by=self.admin_user,
        )

        self.assertEqual(len(logs), 1)
        self.assertTrue(all(row.status == SMSLog.STATUS_SENT for row in logs))
        self.assertEqual(logs[0].recipient_number, '9999999999')

    def test_invalid_sms_number_logs_failed_status(self):
        GlobalSettings.objects.create(
            school=self.school,
            sms_enabled=True,
            sms_api_url='https://sms.example.com/send',
            sms_api_key='test-key',
            sms_sender_id='AHVERP',
        )

        log = send_sms_notification(
            school=self.school,
            session=self.session,
            recipient_number='bad-number',
            message='Alert',
            triggered_by=self.admin_user,
        )

        self.assertEqual(log.status, SMSLog.STATUS_FAILED)
        self.assertIn('valid phone number', log.error_message.lower())

    @patch('apps.core.communication.services.EmailMessage.send', return_value=1)
    @patch('apps.core.communication.services.url_request.urlopen')
    def test_fee_due_notifications_create_logs_and_notification(self, mock_urlopen, mock_send):
        response = MagicMock()
        response.status = 200
        mock_urlopen.return_value.__enter__.return_value = response

        GlobalSettings.objects.create(
            school=self.school,
            email_enabled=True,
            smtp_host='smtp.example.com',
            smtp_port=587,
            smtp_from_email='noreply@example.com',
            sms_enabled=True,
            sms_api_url='https://sms.example.com/send',
            sms_api_key='test-key',
            sms_sender_id='AHVERP',
        )

        fee_type = FeeType.objects.create(
            school=self.school,
            name='Tuition',
            category=FeeType.CATEGORY_ACADEMIC,
            is_active=True,
        )
        ClassFeeStructure.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            fee_type=fee_type,
            amount='1200.00',
            is_active=True,
        )
        sync_student_fees_for_student(student=self.student)

        result = run_fee_overdue_notifications(
            school=self.school,
            session=self.session,
            as_of_date=self.today,
        )

        self.assertEqual(result['students'], 1)
        self.assertEqual(result['notifications'], 1)
        self.assertTrue(
            Notification.objects.filter(
                school=self.school,
                user=self.parent_user,
                related_model='StudentFee',
            ).exists()
        )
        self.assertTrue(
            EmailLog.objects.filter(
                school=self.school,
                related_model='StudentFee',
                status=EmailLog.STATUS_SENT,
            ).exists()
        )
        self.assertTrue(
            SMSLog.objects.filter(
                school=self.school,
                related_model='StudentFee',
                status=SMSLog.STATUS_SENT,
            ).exists()
        )
        self.assertGreaterEqual(mock_send.call_count, 1)


class CommunicationViewTests(CommunicationBaseTestCase):
    def test_schooladmin_can_open_announcement_manage(self):
        self.client.login(username='comm_admin', password='pass12345')
        response = self.client.get(reverse('communication_announcement_list_core'))
        self.assertEqual(response.status_code, 200)

    def test_expired_announcement_cannot_be_edited(self):
        announcement = Announcement.objects.create(
            school=self.school,
            session=self.session,
            title='Urgent Notice',
            message='Old message',
            target_role=Announcement.ROLE_PARENT,
            created_by=self.admin_user,
            expires_at=timezone.now() + timedelta(days=1),
        )
        Announcement.objects.filter(pk=announcement.pk).update(
            expires_at=timezone.now() - timedelta(hours=1),
        )

        self.client.login(username='comm_admin', password='pass12345')
        response = self.client.get(
            reverse('communication_announcement_update_core', args=[announcement.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Expired announcements cannot be edited.')

    def test_parent_can_open_portal(self):
        self.client.login(username='comm_parent', password='pass12345')
        response = self.client.get(reverse('communication_parent_portal_core'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.admission_number)

    def test_parent_can_open_notification_list(self):
        Notification.objects.create(
            school=self.school,
            session=self.session,
            user=self.parent_user,
            title='Test Notification',
            message='Hello',
            related_model='Test',
            related_id='1',
        )

        self.client.login(username='comm_parent', password='pass12345')
        response = self.client.get(reverse('communication_notification_list_core'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Notification')

    def test_school_dashboard_shows_communication_snapshot(self):
        Announcement.objects.create(
            school=self.school,
            session=self.session,
            title='General Notice',
            message='Dashboard visible announcement',
            target_role=Announcement.ROLE_ALL,
            created_by=self.admin_user,
        )
        Notification.objects.create(
            school=self.school,
            session=self.session,
            user=self.admin_user,
            title='Admin Notification',
            message='Unread item',
        )

        self.client.login(username='comm_admin', password='pass12345')
        response = self.client.get(reverse('school_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Communication Snapshot')
        self.assertContains(response, 'General Notice')
