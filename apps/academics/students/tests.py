from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.exams.models import Exam, ExamSchedule
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

    def test_student_create_rejects_section_not_in_selected_class(self):
        other_class = SchoolClass.objects.create(
            school=self.school,
            name='Class 7'
        )
        other_section = Section.objects.create(
            school_class=other_class,
            name='B'
        )

        self.client.login(username='student_admin', password='pass12345')
        response = self.client.post(reverse('student_create'), {
            'admission_number': 'ENR-1002',
            'first_name': 'Nina',
            'last_name': 'Das',
            'date_of_birth': '2014-02-10',
            'gender': 'female',
            'academic_session': self.session.id,
            'school_class': self.school_class.id,
            'section': other_section.id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selected section does not belong to the selected class')
        self.assertFalse(Student.objects.filter(admission_number='ENR-1002').exists())


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


class StudentActionMethodTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Student Action School')
        self.admin = self.user_model.objects.create_user(
            username='student_action_admin',
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
            name='Class 8'
        )
        self.section = Section.objects.create(
            school_class=self.school_class,
            name='A'
        )
        self.student = Student.objects.create(
            school=self.school,
            admission_number='ACT-1001',
            first_name='Isha',
            last_name='N',
            academic_session=self.session,
            school_class=self.school_class,
            section=self.section,
        )
        self.enrollment = StudentEnrollment.objects.create(
            student=self.student,
            academic_session=self.session,
            school_class=self.school_class,
            section=self.section,
            status='active',
        )
        self.grade_scale = GradeScale.objects.create(
            school=self.school,
            grade_name='A',
            min_percentage=80,
            max_percentage=100,
            remarks='Excellent',
        )

    def test_grade_scale_delete_requires_post(self):
        self.client.login(username='student_action_admin', password='pass12345')

        response = self.client.get(reverse('grade_scale_delete', args=[self.grade_scale.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(GradeScale.objects.filter(pk=self.grade_scale.id).exists())

        response = self.client.post(reverse('grade_scale_delete', args=[self.grade_scale.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GradeScale.objects.filter(pk=self.grade_scale.id).exists())

    def test_enrollment_status_update_requires_post(self):
        self.client.login(username='student_action_admin', password='pass12345')

        response = self.client.get(reverse('enrollment_status_update', args=[self.enrollment.id]), {
            'status': 'passed'
        })
        self.assertEqual(response.status_code, 405)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, 'active')

        response = self.client.post(reverse('enrollment_status_update', args=[self.enrollment.id]), {
            'status': 'passed'
        })
        self.assertEqual(response.status_code, 302)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, 'passed')


class AddMarksScheduleIntegrationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Marks School')
        self.teacher = self.user_model.objects.create_user(
            username='marks_teacher',
            password='pass12345',
            role='teacher',
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
            name='Class 9'
        )
        self.section = Section.objects.create(
            school_class=self.school_class,
            name='A'
        )
        self.student = Student.objects.create(
            school=self.school,
            admission_number='MARK-1001',
            first_name='Reema',
            last_name='S',
            academic_session=self.session,
            school_class=self.school_class,
            section=self.section,
        )

        self.exam = Exam.objects.create(
            school=self.school,
            academic_session=self.session,
            name='Mid Term',
            start_date='2026-09-01',
            end_date='2026-09-15',
            is_published=True,
        )
        self.subject = self.school.subjects.create(
            school_class=self.school_class,
            name='Science',
            code='SCI',
        )
        self.exam_schedule = ExamSchedule.objects.create(
            school=self.school,
            exam=self.exam,
            school_class=self.school_class,
            section=self.section,
            subject=self.subject,
            date='2026-09-10',
            start_time='10:00',
            end_time='11:00',
            max_marks='80',
            pass_marks='30',
            is_active=True,
        )

    def test_teacher_add_marks_uses_exam_schedule_subject_exam_and_total(self):
        self.client.login(username='marks_teacher', password='pass12345')
        response = self.client.post(reverse('add_marks'), {
            'student': self.student.id,
            'exam_schedule': self.exam_schedule.id,
            'marks': '72',
        })

        self.assertEqual(response.status_code, 302)
        mark = StudentMark.objects.get(student=self.student)
        self.assertEqual(mark.exam_schedule_id, self.exam_schedule.id)
        self.assertEqual(mark.subject, 'Science')
        self.assertEqual(mark.exam_type, 'Mid Term')
        self.assertEqual(mark.total_marks, 80)
        self.assertEqual(mark.marks_obtained, 72)

    def test_teacher_cannot_add_marks_for_schedule_of_different_section(self):
        other_section = Section.objects.create(
            school_class=self.school_class,
            name='B'
        )
        other_schedule = ExamSchedule.objects.create(
            school=self.school,
            exam=self.exam,
            school_class=self.school_class,
            section=other_section,
            subject=self.subject,
            date='2026-09-12',
            start_time='12:00',
            end_time='13:00',
            max_marks='80',
            pass_marks='30',
            is_active=True,
        )

        self.client.login(username='marks_teacher', password='pass12345')
        response = self.client.post(reverse('add_marks'), {
            'student': self.student.id,
            'exam_schedule': other_schedule.id,
            'marks': '60',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not assigned to the selected student')
        self.assertFalse(StudentMark.objects.filter(student=self.student).exists())
