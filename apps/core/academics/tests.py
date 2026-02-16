from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.academics.models import SchoolClass, Subject
from apps.core.schools.models import School


class SubjectIsolationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

        self.school_a = School.objects.create(name='School A')
        self.school_b = School.objects.create(name='School B')

        self.admin_a = self.user_model.objects.create_user(
            username='academics_admin_a',
            password='pass12345',
            role='schooladmin',
            school=self.school_a,
        )

        self.class_a = SchoolClass.objects.create(
            school=self.school_a,
            name='Class 5'
        )
        self.class_b = SchoolClass.objects.create(
            school=self.school_b,
            name='Class 9'
        )

    def test_cannot_create_subject_for_other_school_class(self):
        self.client.login(username='academics_admin_a', password='pass12345')
        response = self.client.post(reverse('subject_create'), {
            'name': 'Science',
            'code': 'SCI',
            'school_class': self.class_b.id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subject.objects.filter(school=self.school_a, name='Science').exists())

    def test_can_create_subject_for_own_school_class(self):
        self.client.login(username='academics_admin_a', password='pass12345')
        response = self.client.post(reverse('subject_create'), {
            'name': 'Mathematics',
            'code': 'MTH',
            'school_class': self.class_a.id,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Subject.objects.filter(school=self.school_a, name='Mathematics').exists())
