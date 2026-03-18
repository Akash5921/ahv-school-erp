from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import AcademicConfig, ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.attendance.models import StudentAttendance
from apps.core.exams.models import Exam, ExamResultSummary, ExamType
from apps.core.fees.models import CarryForwardDue, ClassFeeStructure, FeeType, StudentFee
from apps.core.fees.services import sync_student_fees_for_student
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.students.services import sync_student_academic_links

from .models import PromotionRecord
from .services import (
    bulk_promote_students,
    close_session,
    initialize_new_session,
    unlock_session,
)


class PromotionLifecycleTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()

        self.school = School.objects.create(name='Promotion School', code='promotion_school')
        self.school_admin = user_model.objects.create_user(
            username='promotion_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.superadmin = user_model.objects.create_superuser(
            username='promotion_super',
            password='pass12345',
        )

        self.from_session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.today - timedelta(days=120),
            end_date=self.today + timedelta(days=60),
            is_active=True,
        )
        self.school.current_session = self.from_session
        self.school.save(update_fields=['current_session'])

        self.from_class = SchoolClass.objects.create(
            school=self.school,
            session=self.from_session,
            name='8th',
            code='VIII',
            display_order=8,
            is_active=True,
        )
        self.from_section = Section.objects.create(
            school_class=self.from_class,
            name='A',
            capacity=35,
            is_active=True,
        )
        self.subject = Subject.objects.create(
            school=self.school,
            name='Mathematics',
            code='MTH',
            is_active=True,
        )
        ClassSubject.objects.create(
            school_class=self.from_class,
            subject=self.subject,
        )
        Period.objects.create(
            school=self.school,
            session=self.from_session,
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            is_active=True,
        )
        AcademicConfig.objects.create(
            school=self.school,
            session=self.from_session,
            total_periods_per_day=8,
            working_days=['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'],
            grading_enabled=True,
            attendance_type=AcademicConfig.ATTENDANCE_DAILY,
            marks_decimal_allowed=False,
        )

        self.fee_type = FeeType.objects.create(
            school=self.school,
            name='Tuition',
            category=FeeType.CATEGORY_ACADEMIC,
            is_active=True,
        )
        ClassFeeStructure.objects.create(
            school=self.school,
            session=self.from_session,
            school_class=self.from_class,
            fee_type=self.fee_type,
            amount=Decimal('1500.00'),
            is_active=True,
        )

        self.student = Student.objects.create(
            school=self.school,
            session=self.from_session,
            admission_number='PR-001',
            first_name='Aanya',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.from_class,
            current_section=self.from_section,
            roll_number='1',
        )
        sync_student_academic_links(self.student)

        StudentAttendance.objects.create(
            school=self.school,
            session=self.from_session,
            student=self.student,
            school_class=self.from_class,
            section=self.from_section,
            date=self.today - timedelta(days=2),
            status=StudentAttendance.STATUS_PRESENT,
            marked_by=self.school_admin,
        )

        self.to_session = AcademicSession.objects.create(
            school=self.school,
            name='2027-28',
            start_date=self.from_session.end_date + timedelta(days=1),
            end_date=self.from_session.end_date + timedelta(days=365),
            is_active=False,
        )
        self.to_class = SchoolClass.objects.create(
            school=self.school,
            session=self.to_session,
            name='9th',
            code='IX',
            display_order=9,
            is_active=True,
        )
        self.to_section = Section.objects.create(
            school_class=self.to_class,
            name='A',
            capacity=40,
            is_active=True,
        )

    def _finalize_for_promotion(self):
        sync_student_fees_for_student(student=self.student)
        exam_type = ExamType.objects.create(
            school=self.school,
            session=self.from_session,
            name='Final Exam',
            is_active=True,
        )
        exam = Exam.objects.create(
            school=self.school,
            session=self.from_session,
            exam_type=exam_type,
            school_class=self.from_class,
            section=self.from_section,
            start_date=self.today - timedelta(days=7),
            end_date=self.today - timedelta(days=1),
            total_marks=Decimal('100.00'),
            is_locked=True,
            created_by=self.school_admin,
            is_active=True,
        )
        ExamResultSummary.objects.create(
            school=self.school,
            session=self.from_session,
            student=self.student,
            exam=exam,
            total_marks=Decimal('420.00'),
            percentage=Decimal('84.00'),
            grade='A',
            rank=1,
            attendance_percentage=Decimal('95.00'),
            result_status=ExamResultSummary.STATUS_PASS,
            is_locked=True,
        )
        self.from_session.attendance_locked = True
        self.from_session.save(update_fields=['attendance_locked'])


class SessionInitializationTests(PromotionLifecycleTestCase):
    def test_initialize_new_session_copies_setup_and_fee_structure(self):
        result = initialize_new_session(
            school=self.school,
            name='2028-29',
            start_date=self.to_session.end_date + timedelta(days=1),
            end_date=self.to_session.end_date + timedelta(days=365),
            created_by=self.school_admin,
            source_session=self.from_session,
            copy_academic_structure=True,
            copy_fee_structure=True,
            make_current=False,
        )

        new_session = result['session']
        self.assertTrue(SchoolClass.objects.filter(session=new_session, name='8th').exists())
        cloned_class = SchoolClass.objects.get(session=new_session, name='8th')
        self.assertTrue(Section.objects.filter(school_class=cloned_class, name='A').exists())
        self.assertTrue(ClassSubject.objects.filter(school_class=cloned_class, subject=self.subject).exists())
        self.assertTrue(Period.objects.filter(session=new_session, period_number=1).exists())
        self.assertTrue(AcademicConfig.objects.filter(session=new_session).exists())
        self.assertTrue(ClassFeeStructure.objects.filter(session=new_session, school_class=cloned_class).exists())
        self.assertFalse(StudentAttendance.objects.filter(session=new_session).exists())
        self.assertFalse(Exam.objects.filter(session=new_session).exists())

    def test_lifecycle_dashboard_can_create_session(self):
        self.client.login(username='promotion_admin', password='pass12345')
        response = self.client.post(reverse('promotion_lifecycle'), {
            'source_session': self.from_session.id,
            'name': '2028-29',
            'start_date': str(self.to_session.end_date + timedelta(days=1)),
            'end_date': str(self.to_session.end_date + timedelta(days=365)),
            'copy_academic_structure': 'on',
            'copy_fee_structure': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AcademicSession.objects.filter(school=self.school, name='2028-29').exists())


class PromotionFlowTests(PromotionLifecycleTestCase):
    def test_bulk_promotion_creates_record_carry_forward_and_keeps_history(self):
        self._finalize_for_promotion()

        processed, errors = bulk_promote_students(
            school=self.school,
            from_session=self.from_session,
            to_session=self.to_session,
            actions=[{
                'student_id': self.student.id,
                'status': PromotionRecord.STATUS_PROMOTED,
                'to_class_id': self.to_class.id,
                'to_section_id': self.to_section.id,
                'remarks': 'Promoted to next grade',
            }],
            promoted_by=self.school_admin,
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(processed), 1)

        self.student.refresh_from_db()
        self.assertEqual(self.student.session_id, self.to_session.id)
        self.assertEqual(self.student.current_class_id, self.to_class.id)
        self.assertEqual(self.student.current_section_id, self.to_section.id)
        self.assertTrue(
            PromotionRecord.objects.filter(
                student=self.student,
                from_session=self.from_session,
                to_session=self.to_session,
                status=PromotionRecord.STATUS_PROMOTED,
            ).exists()
        )
        self.assertTrue(
            CarryForwardDue.objects.filter(
                student=self.student,
                from_session=self.from_session,
                to_session=self.to_session,
            ).exists()
        )
        self.assertTrue(
            StudentFee.objects.filter(
                student=self.student,
                session=self.to_session,
                is_carry_forward=True,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            StudentSessionRecord.objects.filter(
                student=self.student,
                session=self.from_session,
                status=Student.STATUS_PASSED,
                is_current=False,
            ).exists()
        )
        self.assertTrue(
            StudentSessionRecord.objects.filter(
                student=self.student,
                session=self.to_session,
                school_class=self.to_class,
                section=self.to_section,
                is_current=True,
            ).exists()
        )
        self.assertTrue(StudentAttendance.objects.filter(session=self.from_session, student=self.student).exists())
        self.assertFalse(StudentAttendance.objects.filter(session=self.to_session, student=self.student).exists())

    def test_bulk_promotion_blocks_when_results_are_not_finalized(self):
        self.from_session.attendance_locked = True
        self.from_session.save(update_fields=['attendance_locked'])

        processed, errors = bulk_promote_students(
            school=self.school,
            from_session=self.from_session,
            to_session=self.to_session,
            actions=[{
                'student_id': self.student.id,
                'status': PromotionRecord.STATUS_PROMOTED,
                'to_class_id': self.to_class.id,
                'to_section_id': self.to_section.id,
                'remarks': '',
            }],
            promoted_by=self.school_admin,
        )

        self.assertEqual(processed, [])
        self.assertEqual(PromotionRecord.objects.count(), 0)
        self.assertIn('Results must be finalized', errors[0])

    def test_promotion_dashboard_view_loads(self):
        self.client.login(username='promotion_admin', password='pass12345')
        response = self.client.get(reverse('promotion_dashboard'), {
            'from_session': self.from_session.id,
            'to_session': self.to_session.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Promotion Dashboard')
        self.assertContains(response, self.student.admission_number)


class SessionCloseTests(PromotionLifecycleTestCase):
    def test_close_session_locks_previous_session_and_blocks_edits(self):
        self.from_session.attendance_locked = True
        self.from_session.save(update_fields=['attendance_locked'])

        result = close_session(
            session=self.from_session,
            closed_by=self.school_admin,
            next_session=self.to_session,
        )

        self.from_session.refresh_from_db()
        self.to_session.refresh_from_db()
        self.school.refresh_from_db()

        self.assertTrue(self.from_session.is_locked)
        self.assertFalse(self.from_session.is_active)
        self.assertTrue(self.to_session.is_active)
        self.assertEqual(self.school.current_session_id, self.to_session.id)
        self.assertEqual(result['payroll_locked'], 0)

        fee_row = ClassFeeStructure.objects.get(session=self.from_session, school_class=self.from_class)
        fee_row.amount = Decimal('1800.00')
        with self.assertRaises(ValidationError):
            fee_row.full_clean()

        self.from_class.name = '8th Updated'
        with self.assertRaises(ValidationError):
            self.from_class.full_clean()

    def test_unlock_session_requires_superadmin_override(self):
        self.from_session.attendance_locked = True
        self.from_session.save(update_fields=['attendance_locked'])
        close_session(
            session=self.from_session,
            closed_by=self.school_admin,
            next_session=self.to_session,
        )

        with self.assertRaises(ValidationError):
            unlock_session(
                session=self.from_session,
                unlocked_by=self.school_admin,
                allow_override=False,
            )

        unlock_session(
            session=self.from_session,
            unlocked_by=self.superadmin,
            allow_override=True,
        )
        self.from_session.refresh_from_db()
        self.assertFalse(self.from_session.is_locked)
        self.assertFalse(self.from_session.attendance_locked)
