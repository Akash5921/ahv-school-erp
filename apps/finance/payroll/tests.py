from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.staff.models import Staff
from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School
from apps.finance.payroll.models import SalaryPayment, SalaryStructure


class PayrollIsolationTests(TestCase):
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

        self.accountant_a = self.user_model.objects.create_user(
            username='pay_acc_a',
            password='pass12345',
            role='accountant',
            school=self.school_a,
        )

        self.staff_b = Staff.objects.create(
            school=self.school_b,
            staff_id='ST-B-1',
            first_name='Driver',
            last_name='One',
            staff_type='driver',
            joining_date='2025-01-01',
            is_active=True,
        )
        self.salary_structure_b = SalaryStructure.objects.create(
            school=self.school_b,
            staff=self.staff_b,
            monthly_salary='15000',
        )

    def test_accountant_cannot_pay_salary_for_other_school_structure(self):
        self.client.login(username='pay_acc_a', password='pass12345')
        response = self.client.post(reverse('pay_salary'), {
            'salary_structure': self.salary_structure_b.id,
            'amount': '15000',
            'month': 'February 2026',
        })

        self.assertEqual(response.status_code, 404)


class PayrollConfigurationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Payroll Config School')
        self.school_admin = self.user_model.objects.create_user(
            username='pay_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.accountant = self.user_model.objects.create_user(
            username='pay_acc',
            password='pass12345',
            role='accountant',
            school=self.school,
        )
        self.staff_member = Staff.objects.create(
            school=self.school,
            staff_id='ST-CFG-1',
            first_name='Mehul',
            last_name='Shah',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
        )
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

    def test_school_admin_can_configure_salary_structure(self):
        self.client.login(username='pay_admin', password='pass12345')
        response = self.client.post(reverse('salary_structure_manage'), {
            'staff': self.staff_member.id,
            'monthly_salary': '28000.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SalaryStructure.objects.filter(
                school=self.school,
                staff=self.staff_member,
                monthly_salary='28000.00'
            ).exists()
        )

    def test_accountant_cannot_access_salary_structure_manage(self):
        self.client.login(username='pay_acc', password='pass12345')
        response = self.client.get(reverse('salary_structure_manage'))
        self.assertEqual(response.status_code, 403)

    def test_salary_payment_prevents_duplicate_month(self):
        SalaryStructure.objects.create(
            school=self.school,
            staff=self.staff_member,
            monthly_salary='28000.00'
        )
        self.client.login(username='pay_acc', password='pass12345')
        first = self.client.post(reverse('pay_salary'), {
            'salary_structure': SalaryStructure.objects.get(staff=self.staff_member).id,
            'month': 'May 2026',
        })
        second = self.client.post(reverse('pay_salary'), {
            'salary_structure': SalaryStructure.objects.get(staff=self.staff_member).id,
            'month': 'May 2026',
        })
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'already paid')
        self.assertEqual(
            SalaryPayment.objects.filter(
                salary_structure__staff=self.staff_member,
                month='May 2026',
                academic_session=self.session
            ).count(),
            1
        )
