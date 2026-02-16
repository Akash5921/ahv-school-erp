from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.core.users.models import AuditLog


class SchoolOnboardingTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.superadmin = self.user_model.objects.create_user(
            username='superadmin1',
            password='pass12345',
            role='superadmin',
        )

    def test_superadmin_can_onboard_school_with_admin_and_session(self):
        self.client.login(username='superadmin1', password='pass12345')
        response = self.client.post(reverse('school_onboard'), {
            'school_name': 'Beta School',
            'school_address': 'Main Road',
            'school_phone': '1234567890',
            'school_email': 'beta@example.com',
            'admin_username': 'beta_admin',
            'admin_email': 'beta_admin@example.com',
            'admin_password': 'pass12345',
            'session_name': '2026-27',
            'session_start_date': '2026-04-01',
            'session_end_date': '2027-03-31',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(School.objects.filter(name='Beta School').exists())

        school = School.objects.get(name='Beta School')
        self.assertIsNotNone(school.current_session)
        self.assertTrue(AcademicSession.objects.filter(school=school, name='2026-27').exists())

        school_admin = self.user_model.objects.get(username='beta_admin')
        self.assertEqual(school_admin.role, 'schooladmin')
        self.assertEqual(school_admin.school, school)

        self.assertTrue(
            AuditLog.objects.filter(
                action='school.onboarded',
                school=school
            ).exists()
        )
