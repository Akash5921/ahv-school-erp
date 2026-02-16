from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.staff.models import Staff
from apps.core.schools.models import School


class StaffMappingTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Staff School')
        self.admin = self.user_model.objects.create_user(
            username='staff_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.staff = Staff.objects.create(
            school=self.school,
            staff_id='SF-001',
            first_name='Ravi',
            last_name='Sharma',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
        )

    def test_staff_assign_user_creates_linked_user(self):
        self.client.login(username='staff_admin', password='pass12345')
        response = self.client.post(reverse('staff_assign_user', args=[self.staff.id]), {
            'username': 'ravi_sf001',
            'email': 'ravi@example.com',
            'password': 'pass12345',
            'role': 'teacher',
        })

        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertIsNotNone(self.staff.user)
        self.assertEqual(self.staff.user.school, self.school)
        self.assertEqual(self.staff.user.role, 'teacher')
