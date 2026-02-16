from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.students.models import GradeScale, Student, StudentEnrollment, StudentMark
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.schools.models import School


class StudentEnrollmentLifecycleTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Enrollment School')
        self.admin = self.user_model.objects.create_user(
            username='student_admin',
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
        self.school_class = SchoolClass.objects.create(
            school=self.school,
            name='Class 6'
        )
        self.section = Section.objects.create(
            school_class=self.school_class,
            name='A'
        )

    def test_student_create_auto_creates_enrollment(self):
        self.client.login(username='student_admin', password='pass12345')
        response = self.client.post(reverse('student_create'), {
            'admission_number': 'ENR-1001',
            'first_name': 'Asha',
            'last_name': 'Khan',
            'date_of_birth': '2014-01-10',
            'gender': 'female',
            'academic_session': self.session.id,
            'school_class': self.school_class.id,
            'section': self.section.id,
        })

        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(admission_number='ENR-1001')
        self.assertTrue(
            StudentEnrollment.objects.filter(
                student=student,
                academic_session=self.session,
                school_class=self.school_class,
                section=self.section,
                status='active',
            ).exists()
        )


class ReportCardAndParentAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Report School')

        self.teacher = self.user_model.objects.create_user(
            username='report_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.parent = self.user_model.objects.create_user(
            username='report_parent',
            password='pass12345',
            role='parent',
            school=self.school,
        )
        self.other_parent = self.user_model.objects.create_user(
            username='other_parent',
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

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            name='Class 7'
        )
        self.section = Section.objects.create(
            school_class=self.school_class,
            name='A'
        )

        self.student = Student.objects.create(
            school=self.school,
            admission_number='RC-1001',
            first_name='Meera',
            last_name='Patel',
            academic_session=self.session,
            school_class=self.school_class,
            section=self.section,
            parent_user=self.parent,
        )

        GradeScale.objects.create(
            school=self.school,
            grade_name='A',
            min_percentage=80,
            max_percentage=100,
            remarks='Excellent',
        )
        GradeScale.objects.create(
            school=self.school,
            grade_name='B',
            min_percentage=60,
            max_percentage=79.99,
            remarks='Good',
        )
        GradeScale.objects.create(
            school=self.school,
            grade_name='C',
            min_percentage=40,
            max_percentage=59.99,
            remarks='Average',
        )
        GradeScale.objects.create(
            school=self.school,
            grade_name='F',
            min_percentage=0,
            max_percentage=39.99,
            remarks='Fail',
        )

        StudentMark.objects.create(
            school=self.school,
            student=self.student,
            subject='Mathematics',
            marks_obtained=45,
            total_marks=50,
            exam_type='Midterm',
        )

    def test_report_card_shows_overall_grade(self):
        self.client.login(username='report_teacher', password='pass12345')
        response = self.client.get(reverse('exam_report_card', args=[self.student.id]), {
            'exam': 'Midterm'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['overall_grade'], 'A')
        self.assertEqual(response.context['status'], 'PASS')

    def test_parent_can_view_own_child_report_card(self):
        self.client.login(username='report_parent', password='pass12345')
        response = self.client.get(reverse('exam_report_card', args=[self.student.id]))
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_view_other_child_report_card(self):
        self.client.login(username='other_parent', password='pass12345')
        response = self.client.get(reverse('exam_report_card', args=[self.student.id]))
        self.assertEqual(response.status_code, 404)
