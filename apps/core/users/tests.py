from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.schools.models import School


class UserModelRulesTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_non_superadmin_requires_school(self):
        with self.assertRaises(ValueError):
            self.user_model.objects.create_user(
                username='teacher_without_school',
                password='pass12345',
                role='teacher',
            )

    def test_create_superuser_defaults_to_superadmin_without_school(self):
        superuser = self.user_model.objects.create_superuser(
            username='root_user',
            email='root@example.com',
            password='pass12345',
        )
        self.assertEqual(superuser.role, 'superadmin')
        self.assertIsNone(superuser.school)
        self.assertTrue(superuser.is_superuser)


class RoleRoutingTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Routing School')
        self.superadmin = self.user_model.objects.create_user(
            username='routing_superadmin',
            password='pass12345',
            role='superadmin',
        )
        self.school_admin = self.user_model.objects.create_user(
            username='routing_schooladmin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher = self.user_model.objects.create_user(
            username='routing_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

    def test_superadmin_redirects_to_school_list(self):
        self.client.login(username='routing_superadmin', password='pass12345')
        response = self.client.get(reverse('role_redirect'))
        self.assertRedirects(response, reverse('school_list'))

    def test_school_admin_redirects_to_school_dashboard(self):
        self.client.login(username='routing_schooladmin', password='pass12345')
        response = self.client.get(reverse('role_redirect'))
        self.assertRedirects(response, reverse('school_dashboard'))

    def test_non_admin_roles_redirect_to_workspace(self):
        self.client.login(username='routing_teacher', password='pass12345')
        response = self.client.get(reverse('role_redirect'))
        self.assertRedirects(response, reverse('role_workspace'))


class WorkspaceAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Workspace School')
        self.teacher = self.user_model.objects.create_user(
            username='workspace_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.school_admin = self.user_model.objects.create_user(
            username='workspace_schooladmin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )

    def test_teacher_can_access_workspace(self):
        self.client.login(username='workspace_teacher', password='pass12345')
        response = self.client.get(reverse('role_workspace'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teacher')

    def test_school_admin_cannot_access_workspace(self):
        self.client.login(username='workspace_schooladmin', password='pass12345')
        response = self.client.get(reverse('role_workspace'))
        self.assertEqual(response.status_code, 403)
