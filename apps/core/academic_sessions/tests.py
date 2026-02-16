from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School


class AcademicSessionTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Session School')
        self.school_admin = self.user_model.objects.create_user(
            username='session_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )

        self.session_one = AcademicSession.objects.create(
            school=self.school,
            name='2025-26',
            start_date='2025-04-01',
            end_date='2026-03-31',
            is_active=True,
        )
        self.session_two = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=False,
        )

        self.school.current_session = self.session_one
        self.school.save(update_fields=['current_session'])

    def test_session_activate_switches_active_and_current_session(self):
        self.client.login(username='session_admin', password='pass12345')
        response = self.client.get(reverse('session_activate', args=[self.session_two.id]))
        self.assertEqual(response.status_code, 302)

        self.session_one.refresh_from_db()
        self.session_two.refresh_from_db()
        self.school.refresh_from_db()

        self.assertFalse(self.session_one.is_active)
        self.assertTrue(self.session_two.is_active)
        self.assertEqual(self.school.current_session_id, self.session_two.id)
