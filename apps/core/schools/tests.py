from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School, SchoolDomain
from apps.core.schools.services import resolve_school_by_host
from apps.core.users.models import AuditLog


class SchoolOnboardingTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.superadmin = self.user_model.objects.create_user(
            username='superadmin1',
            password='pass12345',
            role='superadmin',
        )

    def test_superadmin_can_onboard_school_with_admin_session_and_domain(self):
        self.client.login(username='superadmin1', password='pass12345')
        response = self.client.post(reverse('school_onboard'), {
            'school_name': 'Beta School',
            'school_code': 'beta_main',
            'school_subdomain': 'beta',
            'school_domain': 'erp.beta-school.edu',
            'school_timezone': 'UTC',
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
        school = School.objects.get(name='Beta School')
        school_admin = self.user_model.objects.get(username='beta_admin')
        session = AcademicSession.objects.get(school=school, name='2026-27')

        self.assertEqual(school.code, 'beta_main')
        self.assertEqual(school.subdomain, 'beta')
        self.assertEqual(school.current_session_id, session.id)
        self.assertTrue(session.is_active)
        self.assertEqual(school_admin.role, 'schooladmin')
        self.assertEqual(school_admin.school_id, school.id)
        self.assertTrue(
            SchoolDomain.objects.filter(
                school=school,
                domain='erp.beta-school.edu',
                is_primary=True,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action='school.onboarded', school=school).exists()
        )


class SchoolDashboardTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Dashboard School', code='dash_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])
        self.school_admin = self.user_model.objects.create_user(
            username='dashboard_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.user_model.objects.create_user(
            username='dashboard_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        SchoolDomain.objects.create(
            school=self.school,
            domain='dashboard.school.local',
            is_primary=True,
        )

    def test_school_admin_dashboard_loads_core_metrics(self):
        self.client.login(username='dashboard_admin', password='pass12345')
        response = self.client.get(reverse('school_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'School Foundation Dashboard')
        self.assertContains(response, 'Total Users')
        self.assertContains(response, 'Tenant Domains')


class SchoolResolutionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Resolve School',
            code='resolve_school',
            subdomain='resolve',
        )
        SchoolDomain.objects.create(
            school=self.school,
            domain='erp.resolve.edu',
            is_primary=True,
            is_active=True,
        )

    def test_resolve_school_by_custom_domain(self):
        resolved = resolve_school_by_host('erp.resolve.edu:443')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, self.school.id)

    def test_resolve_school_by_subdomain(self):
        resolved = resolve_school_by_host('resolve.localhost:8000')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, self.school.id)
