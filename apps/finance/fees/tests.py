from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School


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

        self.accountant_a = self.user_model.objects.create_user(
            username='acc_a',
            password='pass12345',
            role='accountant',
            school=self.school_a,
        )

        self.student_b = Student.objects.create(
            school=self.school_b,
            admission_number='B-001',
            first_name='John',
            last_name='Doe',
        )

    def test_accountant_cannot_collect_fee_for_other_school_student(self):
        self.client.login(username='acc_a', password='pass12345')
        response = self.client.post(reverse('collect_fee'), {
            'student': self.student_b.id,
            'amount': '1000',
            'note': 'Test',
        })

        self.assertEqual(response.status_code, 404)
