from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.academics.models import SchoolClass
from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School
from apps.finance.accounts.models import Ledger
from apps.finance.fees.models import FeePayment, FeeStructure, StudentFee


class FeeIsolationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

        self.school_a = School.objects.create(name='School A')
        self.school_b = School.objects.create(name='School B')

        self.session_a = AcademicSession.objects.create(
            school=self.school_a,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school_a.current_session = self.session_a
        self.school_a.save(update_fields=['current_session'])

        self.class_a = SchoolClass.objects.create(
            school=self.school_a,
            name='Class 4',
            order=4,
        )
        self.class_b = SchoolClass.objects.create(
            school=self.school_b,
            name='Class 4',
            order=4,
        )

        self.accountant_a = self.user_model.objects.create_user(
            username='acc_a',
            password='pass12345',
            role='accountant',
            school=self.school_a,
        )

        self.student_a = Student.objects.create(
            school=self.school_a,
            admission_number='A-001',
            first_name='Asha',
            last_name='Mehra',
            school_class=self.class_a,
            academic_session=self.session_a,
        )
        self.student_b = Student.objects.create(
            school=self.school_b,
            admission_number='B-001',
            first_name='John',
            last_name='Doe',
        )

        self.fee_structure_a = FeeStructure.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            school_class=self.class_a,
            name='Tuition',
            amount='3000.00',
        )
        self.student_fee_a = StudentFee.objects.create(
            student=self.student_a,
            fee_structure=self.fee_structure_a,
            total_amount='3000.00',
            concession_amount='500.00',
        )

        self.session_b = AcademicSession.objects.create(
            school=self.school_b,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school_b.current_session = self.session_b
        self.school_b.save(update_fields=['current_session'])
        self.fee_structure_b = FeeStructure.objects.create(
            school=self.school_b,
            academic_session=self.session_b,
            school_class=self.class_b,
            name='Tuition',
            amount='2500.00',
        )
        self.student_fee_b = StudentFee.objects.create(
            student=self.student_b,
            fee_structure=self.fee_structure_b,
            total_amount='2500.00',
        )

    def test_collect_fee_updates_paid_amount_and_creates_receipt(self):
        self.client.login(username='acc_a', password='pass12345')
        response = self.client.post(reverse('collect_fee'), {
            'student_fee': self.student_fee_a.id,
            'amount': '1200.00',
            'note': 'Installment 1',
        })

        self.assertEqual(response.status_code, 302)
        self.student_fee_a.refresh_from_db()
        self.assertEqual(str(self.student_fee_a.paid_amount), '1200.00')
        self.assertEqual(str(self.student_fee_a.due_amount), '1300.00')

        payment = FeePayment.objects.get(student_fee=self.student_fee_a)
        self.assertTrue(payment.receipt_number.startswith(f'RCP-{self.school_a.id}-'))
        self.assertTrue(
            Ledger.objects.filter(
                school=self.school_a,
                academic_session=self.session_a,
                entry_type='income',
                amount='1200.00',
            ).exists()
        )

    def test_collect_fee_blocks_overpayment(self):
        self.client.login(username='acc_a', password='pass12345')
        response = self.client.post(reverse('collect_fee'), {
            'student_fee': self.student_fee_a.id,
            'amount': '2600.00',
            'note': 'Too high',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Amount exceeds due amount')
        self.assertFalse(FeePayment.objects.filter(student_fee=self.student_fee_a).exists())

    def test_accountant_cannot_collect_fee_for_other_school_student(self):
        self.client.login(username='acc_a', password='pass12345')
        response = self.client.post(reverse('collect_fee'), {
            'student_fee': self.student_fee_b.id,
            'amount': '500.00',
            'note': 'Test',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(FeePayment.objects.filter(student=self.student_b).exists())


class FeeConfigurationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Config School')
        self.school_admin = self.user_model.objects.create_user(
            username='fee_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school,
            name='Class 6',
            order=6,
        )
        self.student = Student.objects.create(
            school=self.school,
            admission_number='CFG-001',
            first_name='Neha',
            last_name='Rao',
            school_class=self.school_class,
            academic_session=self.session,
        )

    def test_school_admin_can_create_fee_structure_and_student_fee(self):
        self.client.login(username='fee_admin', password='pass12345')
        response = self.client.post(reverse('fee_structure_list'), {
            'academic_session': self.session.id,
            'school_class': self.school_class.id,
            'name': 'Annual Fee',
            'amount': '8000.00',
        })
        self.assertEqual(response.status_code, 302)

        fee_structure = FeeStructure.objects.get(
            school=self.school,
            name='Annual Fee'
        )

        response = self.client.post(reverse('student_fee_manage'), {
            'student': self.student.id,
            'fee_structure': fee_structure.id,
            'total_amount': '8000.00',
            'concession_amount': '1000.00',
            'concession_note': 'Sibling discount',
        })
        self.assertEqual(response.status_code, 302)
        student_fee = StudentFee.objects.get(
            student=self.student,
            fee_structure=fee_structure
        )
        self.assertEqual(str(student_fee.due_amount), '7000.00')
