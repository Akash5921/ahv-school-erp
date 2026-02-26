from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.schools.models import School
from apps.operations.communication.models import Notice, NoticeRead


class CommunicationFlowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Comm School')

        self.school_admin = self.user_model.objects.create_user(
            username='comm_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.parent = self.user_model.objects.create_user(
            username='comm_parent',
            password='pass12345',
            role='parent',
            school=self.school,
        )
        self.teacher = self.user_model.objects.create_user(
            username='comm_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

    def test_school_admin_can_create_notice(self):
        self.client.login(username='comm_admin', password='pass12345')
        response = self.client.post(reverse('notice_manage'), {
            'title': 'PTM Notice',
            'message': 'Parent-teacher meeting on Saturday.',
            'target_role': 'parent',
            'priority': 'important',
            'is_published': 'on',
            'publish_at': '2026-03-01T10:00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notice.objects.filter(
                school=self.school,
                title='PTM Notice',
                target_role='parent'
            ).exists()
        )

    def test_parent_sees_targeted_notice_and_can_mark_read(self):
        notice = Notice.objects.create(
            school=self.school,
            title='Fee Reminder',
            message='Please clear dues.',
            target_role='parent',
            priority='urgent',
            is_published=True,
            created_by=self.school_admin,
        )

        self.client.login(username='comm_parent', password='pass12345')
        response = self.client.get(reverse('notice_feed'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fee Reminder')

        response = self.client.post(reverse('notice_mark_read', args=[notice.id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            NoticeRead.objects.filter(notice=notice, user=self.parent).exists()
        )

    def test_parent_does_not_see_teacher_only_notice(self):
        Notice.objects.create(
            school=self.school,
            title='Teacher Circular',
            message='Internal note.',
            target_role='teacher',
            is_published=True,
            created_by=self.school_admin,
        )
        self.client.login(username='comm_parent', password='pass12345')
        response = self.client.get(reverse('notice_feed'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Teacher Circular')

    def test_teacher_cannot_access_notice_manage(self):
        self.client.login(username='comm_teacher', password='pass12345')
        response = self.client.get(reverse('notice_manage'))
        self.assertEqual(response.status_code, 403)

    def test_notice_toggle_publish_requires_post(self):
        notice = Notice.objects.create(
            school=self.school,
            title='Publish Toggle',
            message='Toggle me.',
            target_role='all',
            is_published=True,
            created_by=self.school_admin,
        )

        self.client.login(username='comm_admin', password='pass12345')
        response = self.client.get(reverse('notice_toggle_publish', args=[notice.id]))
        self.assertEqual(response.status_code, 405)
        notice.refresh_from_db()
        self.assertTrue(notice.is_published)

        response = self.client.post(reverse('notice_toggle_publish', args=[notice.id]))
        self.assertEqual(response.status_code, 302)
        notice.refresh_from_db()
        self.assertFalse(notice.is_published)

    def test_notice_mark_read_requires_post(self):
        notice = Notice.objects.create(
            school=self.school,
            title='Read Via Post',
            message='Must be post.',
            target_role='parent',
            is_published=True,
            created_by=self.school_admin,
        )

        self.client.login(username='comm_parent', password='pass12345')
        response = self.client.get(reverse('notice_mark_read', args=[notice.id]))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(NoticeRead.objects.filter(notice=notice, user=self.parent).exists())

        response = self.client.post(reverse('notice_mark_read', args=[notice.id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(NoticeRead.objects.filter(notice=notice, user=self.parent).exists())
