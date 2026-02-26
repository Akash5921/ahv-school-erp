from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.schools.models import School
from apps.core.students.models import Student

from .models import (
    CarryForwardDue,
    ClassFeeStructure,
    FeePayment,
    FeeReceipt,
    FeeType,
    Installment,
    LedgerEntry,
    StudentConcession,
    StudentFee,
)
from .services import (
    collect_fee_payment,
    create_fee_refund,
    generate_carry_forward_due,
    recalculate_student_fee_concessions,
    sync_student_fees_for_student,
)


class FeesBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()

        self.school = School.objects.create(name='Fee School', code='fee_school')
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
            name='8th',
            code='VIII',
            display_order=8,
            is_active=True,
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A', is_active=True)

        self.student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='FEE-001',
            first_name='Riya',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number='1',
        )

        self.school_admin = user_model.objects.create_user(
            username='fees_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.accountant = user_model.objects.create_user(
            username='fees_accountant',
            password='pass12345',
            role='accountant',
            school=self.school,
        )

        self.tuition = FeeType.objects.create(
            school=self.school,
            name='Tuition',
            category=FeeType.CATEGORY_ACADEMIC,
            is_active=True,
        )
        self.exam_fee = FeeType.objects.create(
            school=self.school,
            name='Exam Fee',
            category=FeeType.CATEGORY_ACADEMIC,
            is_active=True,
        )

        ClassFeeStructure.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            fee_type=self.tuition,
            amount=Decimal('1200.00'),
            is_active=True,
        )
        ClassFeeStructure.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            fee_type=self.exam_fee,
            amount=Decimal('300.00'),
            is_active=True,
        )

        self.installment = Installment.objects.create(
            school=self.school,
            session=self.session,
            name='Quarter 1',
            due_date=self.today - timedelta(days=10),
            fine_per_day=Decimal('5.00'),
            is_active=True,
        )


class FeeServiceTests(FeesBaseTestCase):
    def test_sync_student_fees_creates_rows(self):
        rows = sync_student_fees_for_student(student=self.student)
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            StudentFee.objects.filter(
                school=self.school,
                session=self.session,
                student=self.student,
                fee_type=self.tuition,
                is_active=True,
            ).exists()
        )

    def test_concession_recalculation_updates_final_amount(self):
        sync_student_fees_for_student(student=self.student)
        StudentConcession.objects.create(
            school=self.school,
            session=self.session,
            student=self.student,
            percentage=Decimal('10.00'),
            reason='Scholarship',
            approved_by=self.school_admin,
            is_active=True,
        )

        recalculate_student_fee_concessions(student=self.student, session=self.session)

        tuition_fee = StudentFee.objects.get(student=self.student, fee_type=self.tuition)
        self.assertEqual(tuition_fee.concession_amount, Decimal('120.00'))
        self.assertEqual(tuition_fee.final_amount, Decimal('1080.00'))

    def test_collect_payment_creates_receipt_and_ledger(self):
        sync_student_fees_for_student(student=self.student)

        result = collect_fee_payment(
            school=self.school,
            session=self.session,
            student=self.student,
            installment=self.installment,
            amount_paid=Decimal('500.00'),
            payment_mode=FeePayment.MODE_CASH,
            received_by=self.accountant,
            payment_date=self.today,
            reference_number='CASH-1',
        )

        payment = result['payment']
        self.assertEqual(payment.fine_amount, Decimal('50.00'))
        self.assertTrue(FeeReceipt.objects.filter(payment=payment).exists())
        self.assertTrue(
            LedgerEntry.objects.filter(
                school=self.school,
                transaction_type=LedgerEntry.TYPE_INCOME,
                reference_model='FeePayment',
                reference_id=str(payment.id),
            ).exists()
        )

    def test_collect_payment_blocks_when_exceeding_outstanding(self):
        sync_student_fees_for_student(student=self.student)
        with self.assertRaises(ValidationError):
            collect_fee_payment(
                school=self.school,
                session=self.session,
                student=self.student,
                installment=self.installment,
                amount_paid=Decimal('2000.00'),
                payment_mode=FeePayment.MODE_CASH,
                received_by=self.accountant,
                payment_date=self.today,
            )

    def test_refund_cannot_exceed_payment_balance(self):
        sync_student_fees_for_student(student=self.student)
        result = collect_fee_payment(
            school=self.school,
            session=self.session,
            student=self.student,
            installment=self.installment,
            amount_paid=Decimal('400.00'),
            payment_mode=FeePayment.MODE_CASH,
            received_by=self.accountant,
            payment_date=self.today,
        )

        with self.assertRaises(ValidationError):
            create_fee_refund(
                payment=result['payment'],
                refund_amount=Decimal('500.00'),
                reason='Too much',
                approved_by=self.school_admin,
                refund_date=self.today,
            )

    def test_generate_carry_forward_due_creates_due_and_student_fee(self):
        sync_student_fees_for_student(student=self.student)

        next_session = AcademicSession.objects.create(
            school=self.school,
            name='2027-28',
            start_date=self.session.end_date + timedelta(days=1),
            end_date=self.session.end_date + timedelta(days=365),
            is_active=False,
        )
        next_class = SchoolClass.objects.create(
            school=self.school,
            session=next_session,
            name='9th',
            code='IX',
            display_order=9,
            is_active=True,
        )
        next_section = Section.objects.create(school_class=next_class, name='A', is_active=True)

        self.student.session = next_session
        self.student.current_class = next_class
        self.student.current_section = next_section
        self.student.save(update_fields=['session', 'current_class', 'current_section'])

        result = generate_carry_forward_due(
            student=self.student,
            from_session=self.session,
            to_session=next_session,
        )

        self.assertTrue(CarryForwardDue.objects.filter(pk=result['carry_forward_due'].id).exists())
        self.assertTrue(
            StudentFee.objects.filter(
                school=self.school,
                student=self.student,
                session=next_session,
                is_carry_forward=True,
                is_active=True,
            ).exists()
        )


class FeeViewTests(FeesBaseTestCase):
    def test_accountant_can_open_payment_manage(self):
        self.client.login(username='fees_accountant', password='pass12345')
        response = self.client.get(reverse('payment_manage_core'))
        self.assertEqual(response.status_code, 200)
