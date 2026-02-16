from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.schools.models import School


class RoleAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Alpha School')

        self.teacher = self.user_model.objects.create_user(
            username='teacher1',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.school_admin = self.user_model.objects.create_user(
            username='schooladmin1',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )

    def test_teacher_cannot_access_school_admin_dashboard(self):
        self.client.login(username='teacher1', password='pass12345')
        response = self.client.get(reverse('school_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_school_admin_can_access_school_admin_dashboard(self):
        self.client.login(username='schooladmin1', password='pass12345')
        response = self.client.get(reverse('school_dashboard'))
        self.assertEqual(response.status_code, 200)


class ParentDashboardTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Parent School')
        self.parent = self.user_model.objects.create_user(
            username='parent_user_1',
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
        school_class = SchoolClass.objects.create(school=self.school, name='Class 4')
        section = Section.objects.create(school_class=school_class, name='A')
        self.student = Student.objects.create(
            school=self.school,
            admission_number='P-1001',
            first_name='Riya',
            last_name='Shah',
            academic_session=self.session,
            school_class=school_class,
            section=section,
            parent_user=self.parent,
        )

    def test_parent_dashboard_loads_linked_students(self):
        self.client.login(username='parent_user_1', password='pass12345')
        response = self.client.get(reverse('parent_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Riya')
