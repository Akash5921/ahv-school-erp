from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School
from apps.finance.accounts.models import Ledger


class ReportsDashboardTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Reports School')
        self.admin = self.user_model.objects.create_user(
            username='reports_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.parent = self.user_model.objects.create_user(
            username='reports_parent',
            password='pass12345',
            role='parent',
            school=self.school,
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

        Ledger.objects.create(
            school=self.school,
            academic_session=self.session,
            entry_type='income',
            description='Test Income',
            amount=1000,
            transaction_date='2026-05-01',
        )

    def test_school_admin_can_open_reports_dashboard(self):
        self.client.login(username='reports_admin', password='pass12345')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Buses')
        self.assertContains(response, 'Total Inventory Items')

    def test_parent_cannot_open_reports_dashboard(self):
        self.client.login(username='reports_parent', password='pass12345')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 403)
