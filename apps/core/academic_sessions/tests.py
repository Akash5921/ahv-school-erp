from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School


class AcademicSessionLifecycleTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Session School', code='session_school')
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
        response = self.client.post(reverse('session_activate', args=[self.session_two.id]))
        self.assertEqual(response.status_code, 302)

        self.session_one.refresh_from_db()
        self.session_two.refresh_from_db()
        self.school.refresh_from_db()

        self.assertFalse(self.session_one.is_active)
        self.assertTrue(self.session_two.is_active)
        self.assertEqual(self.school.current_session_id, self.session_two.id)

    def test_session_create_with_active_true_deactivates_existing_active_session(self):
        self.client.login(username='session_admin', password='pass12345')
        response = self.client.post(reverse('session_create'), {
            'name': '2027-28',
            'start_date': '2027-04-01',
            'end_date': '2028-03-31',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)

        self.session_one.refresh_from_db()
        new_session = AcademicSession.objects.get(school=self.school, name='2027-28')
        self.school.refresh_from_db()

        self.assertFalse(self.session_one.is_active)
        self.assertTrue(new_session.is_active)
        self.assertEqual(self.school.current_session_id, new_session.id)

    def test_session_activate_rejects_get(self):
        self.client.login(username='session_admin', password='pass12345')
        response = self.client.get(reverse('session_activate', args=[self.session_two.id]))
        self.assertEqual(response.status_code, 405)

    def test_session_delete_requires_post(self):
        self.client.login(username='session_admin', password='pass12345')
        response = self.client.get(reverse('session_delete', args=[self.session_two.id]))
        self.assertEqual(response.status_code, 405)

        response = self.client.post(reverse('session_delete', args=[self.session_two.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AcademicSession.objects.filter(pk=self.session_two.id).exists())


class AcademicSessionConstraintTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Constraint School', code='constraint_school')

    def test_only_one_active_session_allowed_per_school(self):
        AcademicSession.objects.create(
            school=self.school,
            name='2025-26',
            start_date='2025-04-01',
            end_date='2026-03-31',
            is_active=True,
        )
        with self.assertRaises(IntegrityError):
            AcademicSession.objects.create(
                school=self.school,
                name='2026-27',
                start_date='2026-04-01',
                end_date='2027-03-31',
                is_active=True,
            )
