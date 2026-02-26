from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.homework.models import Homework
from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School


class HomeworkManagementTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school_a = School.objects.create(name='Homework School A')
        self.school_b = School.objects.create(name='Homework School B')

        self.teacher_a = self.user_model.objects.create_user(
            username='homework_teacher_a',
            password='pass12345',
            role='teacher',
            school=self.school_a,
        )
        self.parent_a = self.user_model.objects.create_user(
            username='homework_parent_a',
            password='pass12345',
            role='parent',
            school=self.school_a,
        )

        self.session_a = AcademicSession.objects.create(
            school=self.school_a,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.class_a = SchoolClass.objects.create(
            school=self.school_a,
            name='Class 5',
            order=5,
        )
        self.section_a = Section.objects.create(
            school_class=self.class_a,
            name='A',
        )
        self.subject_a = Subject.objects.create(
            school=self.school_a,
            school_class=self.class_a,
            name='Math',
            code='MTH',
        )

        self.session_b = AcademicSession.objects.create(
            school=self.school_b,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.class_b = SchoolClass.objects.create(
            school=self.school_b,
            name='Class 8',
            order=8,
        )
        self.section_b = Section.objects.create(
            school_class=self.class_b,
            name='B',
        )
        self.subject_b = Subject.objects.create(
            school=self.school_b,
            school_class=self.class_b,
            name='Science',
            code='SCI',
        )
        self.homework_a = Homework.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            title='Initial Homework A',
            description='Initial content.',
            due_date='2026-07-09',
            is_published=True,
            assigned_by=self.teacher_a,
        )
        self.homework_b = Homework.objects.create(
            school=self.school_b,
            academic_session=self.session_b,
            school_class=self.class_b,
            section=self.section_b,
            subject=self.subject_b,
            title='Initial Homework B',
            description='Other school content.',
            due_date='2026-07-12',
            is_published=True,
        )

    def test_teacher_can_create_homework_for_own_school(self):
        self.client.login(username='homework_teacher_a', password='pass12345')
        response = self.client.post(reverse('homework_manage'), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_a.id,
            'title': 'Algebra Practice',
            'description': 'Solve exercises 1 to 10.',
            'due_date': '2026-07-10',
            'is_published': 'on',
        })

        self.assertEqual(response.status_code, 302)
        homework = Homework.objects.get(title='Algebra Practice')
        self.assertEqual(homework.school_id, self.school_a.id)
        self.assertEqual(homework.assigned_by_id, self.teacher_a.id)

    def test_teacher_cannot_create_homework_using_other_school_subject(self):
        self.client.login(username='homework_teacher_a', password='pass12345')
        response = self.client.post(reverse('homework_manage'), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_b.id,
            'title': 'Invalid Homework',
            'description': 'Should fail.',
            'due_date': '2026-07-11',
            'is_published': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(Homework.objects.filter(title='Invalid Homework').exists())

    def test_parent_cannot_access_homework_manage(self):
        self.client.login(username='homework_parent_a', password='pass12345')
        response = self.client.get(reverse('homework_manage'))
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_update_homework_in_own_school(self):
        self.client.login(username='homework_teacher_a', password='pass12345')
        response = self.client.post(reverse('homework_update', args=[self.homework_a.id]), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_a.id,
            'title': 'Updated Homework A',
            'description': 'Updated content.',
            'due_date': '2026-07-15',
            'is_published': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.homework_a.refresh_from_db()
        self.assertEqual(self.homework_a.title, 'Updated Homework A')
        self.assertEqual(str(self.homework_a.due_date), '2026-07-15')

    def test_teacher_cannot_update_other_school_homework(self):
        self.client.login(username='homework_teacher_a', password='pass12345')
        response = self.client.get(reverse('homework_update', args=[self.homework_b.id]))
        self.assertEqual(response.status_code, 404)

    def test_homework_toggle_publish_requires_post(self):
        self.client.login(username='homework_teacher_a', password='pass12345')

        response = self.client.get(reverse('homework_toggle_publish', args=[self.homework_a.id]))
        self.assertEqual(response.status_code, 405)
        self.homework_a.refresh_from_db()
        self.assertTrue(self.homework_a.is_published)

        response = self.client.post(reverse('homework_toggle_publish', args=[self.homework_a.id]))
        self.assertEqual(response.status_code, 302)
        self.homework_a.refresh_from_db()
        self.assertFalse(self.homework_a.is_published)

    def test_homework_delete_requires_post(self):
        self.client.login(username='homework_teacher_a', password='pass12345')

        response = self.client.get(reverse('homework_delete', args=[self.homework_a.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Homework.objects.filter(pk=self.homework_a.id).exists())

        response = self.client.post(reverse('homework_delete', args=[self.homework_a.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Homework.objects.filter(pk=self.homework_a.id).exists())


class ParentHomeworkViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Parent Homework School')
        self.other_school = School.objects.create(name='Other Homework School')

        self.parent = self.user_model.objects.create_user(
            username='homework_parent',
            password='pass12345',
            role='parent',
            school=self.school,
        )
        self.school_admin = self.user_model.objects.create_user(
            username='homework_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )

        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        school_class = SchoolClass.objects.create(
            school=self.school,
            name='Class 6',
            order=6,
        )
        section_a = Section.objects.create(school_class=school_class, name='A')
        section_b = Section.objects.create(school_class=school_class, name='B')
        subject = Subject.objects.create(
            school=self.school,
            school_class=school_class,
            name='English',
            code='ENG',
        )

        self.student = Student.objects.create(
            school=self.school,
            admission_number='HW-STD-1',
            first_name='Aarav',
            last_name='P',
            school_class=school_class,
            section=section_a,
            academic_session=self.session,
            parent_user=self.parent,
        )

        Homework.objects.create(
            school=self.school,
            academic_session=self.session,
            school_class=school_class,
            section=section_a,
            subject=subject,
            title='Visible Homework',
            description='Visible to parent',
            due_date='2026-08-01',
            is_published=True,
            assigned_by=self.school_admin,
        )
        Homework.objects.create(
            school=self.school,
            academic_session=self.session,
            school_class=school_class,
            section=section_b,
            subject=subject,
            title='Other Section Homework',
            description='Not for this child',
            due_date='2026-08-02',
            is_published=True,
            assigned_by=self.school_admin,
        )

        other_session = AcademicSession.objects.create(
            school=self.other_school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        other_class = SchoolClass.objects.create(
            school=self.other_school,
            name='Class 7',
            order=7,
        )
        other_section = Section.objects.create(
            school_class=other_class,
            name='A',
        )
        other_subject = Subject.objects.create(
            school=self.other_school,
            school_class=other_class,
            name='Physics',
            code='PHY',
        )
        Homework.objects.create(
            school=self.other_school,
            academic_session=other_session,
            school_class=other_class,
            section=other_section,
            subject=other_subject,
            title='Other School Homework',
            description='Not visible',
            due_date='2026-08-03',
            is_published=True,
        )

    def test_parent_sees_only_linked_child_homework(self):
        self.client.login(username='homework_parent', password='pass12345')
        response = self.client.get(reverse('parent_homework_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible Homework')
        self.assertNotContains(response, 'Other Section Homework')
        self.assertNotContains(response, 'Other School Homework')
