from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.exams.models import Exam, ExamSchedule
from apps.academics.staff.models import Staff
from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School


class ExamManagementTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school_a = School.objects.create(name='Exam School A')
        self.school_b = School.objects.create(name='Exam School B')

        self.admin_a = self.user_model.objects.create_user(
            username='exam_admin_a',
            password='pass12345',
            role='schooladmin',
            school=self.school_a,
        )
        self.teacher_user_a = self.user_model.objects.create_user(
            username='exam_teacher_a',
            password='pass12345',
            role='teacher',
            school=self.school_a,
        )

        self.session_a = AcademicSession.objects.create(
            school=self.school_a,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.session_b = AcademicSession.objects.create(
            school=self.school_b,
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

        self.class_a2 = SchoolClass.objects.create(
            school=self.school_a,
            name='Class 6',
            order=6,
        )
        self.section_a2 = Section.objects.create(
            school_class=self.class_a2,
            name='B',
        )
        self.subject_a2 = Subject.objects.create(
            school=self.school_a,
            school_class=self.class_a2,
            name='Science',
            code='SCI',
        )

        self.subject_b = Subject.objects.create(
            school=self.school_b,
            school_class=SchoolClass.objects.create(
                school=self.school_b,
                name='Class 8',
                order=8,
            ),
            name='Physics',
            code='PHY',
        )

        self.invigilator_1 = Staff.objects.create(
            school=self.school_a,
            staff_id='INV-A-1',
            first_name='Anita',
            last_name='Invigilator',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
            user=self.teacher_user_a,
        )
        self.invigilator_2 = Staff.objects.create(
            school=self.school_a,
            staff_id='INV-A-2',
            first_name='Brij',
            last_name='Invigilator',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
        )

    def test_school_admin_can_create_exam(self):
        self.client.login(username='exam_admin_a', password='pass12345')
        response = self.client.post(reverse('exam_manage'), {
            'academic_session': self.session_a.id,
            'name': 'Mid Term',
            'start_date': '2026-09-01',
            'end_date': '2026-09-07',
            'is_published': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Exam.objects.filter(
                school=self.school_a,
                academic_session=self.session_a,
                name='Mid Term'
            ).exists()
        )

    def test_school_admin_cannot_create_exam_for_other_school_session(self):
        self.client.login(username='exam_admin_a', password='pass12345')
        response = self.client.post(reverse('exam_manage'), {
            'academic_session': self.session_b.id,
            'name': 'Wrong Session Exam',
            'start_date': '2026-09-01',
            'end_date': '2026-09-07',
            'is_published': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(
            Exam.objects.filter(school=self.school_a, name='Wrong Session Exam').exists()
        )

    def test_exam_delete_requires_post(self):
        exam = Exam.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            name='Delete Exam',
            start_date='2026-09-01',
            end_date='2026-09-05',
            is_published=True,
        )
        self.client.login(username='exam_admin_a', password='pass12345')

        response = self.client.get(reverse('exam_delete', args=[exam.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Exam.objects.filter(pk=exam.id).exists())

        response = self.client.post(reverse('exam_delete', args=[exam.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Exam.objects.filter(pk=exam.id).exists())

    def test_school_admin_can_create_exam_schedule(self):
        exam = Exam.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            name='Schedule Exam',
            start_date='2026-09-01',
            end_date='2026-09-05',
            is_published=True,
        )
        self.client.login(username='exam_admin_a', password='pass12345')
        response = self.client.post(reverse('exam_schedule_manage', args=[exam.id]), {
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_a.id,
            'date': '2026-09-02',
            'start_time': '09:00',
            'end_time': '10:00',
            'max_marks': '100',
            'pass_marks': '40',
            'room': 'R-01',
            'invigilator': self.invigilator_1.id,
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ExamSchedule.objects.filter(
                school=self.school_a,
                exam=exam,
                school_class=self.class_a,
                section=self.section_a,
                subject=self.subject_a,
            ).exists()
        )

    def test_schedule_delete_requires_post(self):
        exam = Exam.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            name='Schedule Delete Exam',
            start_date='2026-09-01',
            end_date='2026-09-05',
            is_published=True,
        )
        schedule = ExamSchedule.objects.create(
            school=self.school_a,
            exam=exam,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            date='2026-09-02',
            start_time='11:00',
            end_time='12:00',
            max_marks='100',
            pass_marks='40',
            room='R-02',
            invigilator=self.invigilator_1,
            is_active=True,
        )

        self.client.login(username='exam_admin_a', password='pass12345')
        response = self.client.get(reverse('exam_schedule_delete', args=[exam.id, schedule.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(ExamSchedule.objects.filter(pk=schedule.id).exists())

        response = self.client.post(reverse('exam_schedule_delete', args=[exam.id, schedule.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamSchedule.objects.filter(pk=schedule.id).exists())

    def test_cannot_create_overlapping_schedule_for_same_class_section(self):
        exam = Exam.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            name='Overlap Class Exam',
            start_date='2026-09-01',
            end_date='2026-09-05',
            is_published=True,
        )
        ExamSchedule.objects.create(
            school=self.school_a,
            exam=exam,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            date='2026-09-02',
            start_time='09:00',
            end_time='10:00',
            max_marks='100',
            pass_marks='40',
            invigilator=self.invigilator_1,
            is_active=True,
        )

        self.client.login(username='exam_admin_a', password='pass12345')
        response = self.client.post(reverse('exam_schedule_manage', args=[exam.id]), {
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_a.id,
            'date': '2026-09-02',
            'start_time': '09:30',
            'end_time': '10:30',
            'max_marks': '100',
            'pass_marks': '40',
            'room': 'R-03',
            'invigilator': self.invigilator_2.id,
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Time slot overlaps with another exam schedule for this class and section'
        )

    def test_cannot_create_overlapping_schedule_for_same_invigilator(self):
        exam = Exam.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            name='Overlap Invigilator Exam',
            start_date='2026-09-01',
            end_date='2026-09-05',
            is_published=True,
        )
        ExamSchedule.objects.create(
            school=self.school_a,
            exam=exam,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            date='2026-09-03',
            start_time='11:00',
            end_time='12:00',
            max_marks='100',
            pass_marks='40',
            invigilator=self.invigilator_1,
            is_active=True,
        )

        self.client.login(username='exam_admin_a', password='pass12345')
        response = self.client.post(reverse('exam_schedule_manage', args=[exam.id]), {
            'school_class': self.class_a2.id,
            'section': self.section_a2.id,
            'subject': self.subject_a2.id,
            'date': '2026-09-03',
            'start_time': '11:30',
            'end_time': '12:30',
            'max_marks': '100',
            'pass_marks': '40',
            'room': 'R-04',
            'invigilator': self.invigilator_1.id,
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Selected invigilator has another exam assignment in this time slot'
        )

    def test_teacher_cannot_access_exam_manage(self):
        self.client.login(username='exam_teacher_a', password='pass12345')
        response = self.client.get(reverse('exam_manage'))
        self.assertEqual(response.status_code, 403)


class ExamAudienceViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Exam View School')
        self.other_school = School.objects.create(name='Exam Other School')

        self.teacher_user = self.user_model.objects.create_user(
            username='exam_teacher_view',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.parent_user = self.user_model.objects.create_user(
            username='exam_parent_view',
            password='pass12345',
            role='parent',
            school=self.school,
        )
        self.admin_user = self.user_model.objects.create_user(
            username='exam_admin_view',
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
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        school_class = SchoolClass.objects.create(
            school=self.school,
            name='Class 7',
            order=7,
        )
        section_a = Section.objects.create(
            school_class=school_class,
            name='A',
        )
        section_b = Section.objects.create(
            school_class=school_class,
            name='B',
        )
        subject = Subject.objects.create(
            school=self.school,
            school_class=school_class,
            name='Math',
            code='MTH',
        )
        invigilator = Staff.objects.create(
            school=self.school,
            staff_id='EX-VW-INV',
            first_name='Ira',
            last_name='Invigilator',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
            user=self.teacher_user,
        )

        self.student = Student.objects.create(
            school=self.school,
            admission_number='EX-STD-1',
            first_name='Kunal',
            last_name='P',
            school_class=school_class,
            section=section_a,
            academic_session=self.session,
            parent_user=self.parent_user,
        )

        published_exam = Exam.objects.create(
            school=self.school,
            academic_session=self.session,
            name='Published Exam',
            start_date='2026-10-01',
            end_date='2026-10-10',
            is_published=True,
            created_by=self.admin_user,
        )
        unpublished_exam = Exam.objects.create(
            school=self.school,
            academic_session=self.session,
            name='Unpublished Exam',
            start_date='2026-11-01',
            end_date='2026-11-10',
            is_published=False,
            created_by=self.admin_user,
        )

        ExamSchedule.objects.create(
            school=self.school,
            exam=published_exam,
            school_class=school_class,
            section=section_a,
            subject=subject,
            date='2026-10-02',
            start_time='09:00',
            end_time='10:00',
            max_marks='100',
            pass_marks='40',
            room='A1',
            invigilator=invigilator,
            is_active=True,
        )
        ExamSchedule.objects.create(
            school=self.school,
            exam=published_exam,
            school_class=school_class,
            section=section_b,
            subject=subject,
            date='2026-10-03',
            start_time='09:00',
            end_time='10:00',
            max_marks='100',
            pass_marks='40',
            room='B1',
            invigilator=invigilator,
            is_active=True,
        )
        ExamSchedule.objects.create(
            school=self.school,
            exam=unpublished_exam,
            school_class=school_class,
            section=section_a,
            subject=subject,
            date='2026-11-02',
            start_time='09:00',
            end_time='10:00',
            max_marks='100',
            pass_marks='40',
            room='A2',
            invigilator=invigilator,
            is_active=True,
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
            name='Class 8',
            order=8,
        )
        other_section = Section.objects.create(school_class=other_class, name='A')
        other_subject = Subject.objects.create(
            school=self.other_school,
            school_class=other_class,
            name='Science',
            code='SCI',
        )
        other_exam = Exam.objects.create(
            school=self.other_school,
            academic_session=other_session,
            name='Other School Exam',
            start_date='2026-10-01',
            end_date='2026-10-10',
            is_published=True,
        )
        ExamSchedule.objects.create(
            school=self.other_school,
            exam=other_exam,
            school_class=other_class,
            section=other_section,
            subject=other_subject,
            date='2026-10-02',
            start_time='09:00',
            end_time='10:00',
            max_marks='100',
            pass_marks='40',
            room='O1',
            is_active=True,
        )

    def test_teacher_sees_only_published_school_exam_schedules(self):
        self.client.login(username='exam_teacher_view', password='pass12345')
        response = self.client.get(reverse('teacher_exam_schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A1')
        self.assertContains(response, 'B1')
        self.assertNotContains(response, 'A2')
        self.assertNotContains(response, 'O1')

    def test_parent_sees_only_published_linked_child_exam_schedules(self):
        self.client.login(username='exam_parent_view', password='pass12345')
        response = self.client.get(reverse('parent_exam_schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A1')
        self.assertNotContains(response, 'B1')
        self.assertNotContains(response, 'A2')
        self.assertNotContains(response, 'O1')
