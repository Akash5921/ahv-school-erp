from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, SchoolClass, Section, Subject
from apps.core.hr.models import Designation, Staff, TeacherSubjectAssignment
from apps.core.schools.models import School
from apps.core.students.models import Student, StudentSessionRecord, StudentSubject

from .models import Exam, ExamSubject, ExamType, StudentMark
from .services import generate_exam_results, upsert_student_mark


class ExamsBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()
        self.school = School.objects.create(name='Exam School', code='exam_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.today - timedelta(days=90),
            end_date=self.today + timedelta(days=90),
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='9th',
            code='IX',
            display_order=9,
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A')

        self.math = Subject.objects.create(school=self.school, name='Math', code='MTH')
        self.science = Subject.objects.create(school=self.school, name='Science', code='SCI')
        self.computer = Subject.objects.create(school=self.school, name='Computer', code='CSP')
        ClassSubject.objects.create(school_class=self.school_class, subject=self.math)
        ClassSubject.objects.create(school_class=self.school_class, subject=self.science)

        self.admin = user_model.objects.create_user(
            username='exam_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher_user_1 = user_model.objects.create_user(
            username='exam_teacher_1',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.teacher_user_2 = user_model.objects.create_user(
            username='exam_teacher_2',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

        designation = Designation.objects.create(school=self.school, name='Teacher')
        self.teacher_1 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_1,
            employee_id='EX-T1',
            joining_date=self.today - timedelta(days=300),
            designation=designation,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )
        self.teacher_2 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_2,
            employee_id='EX-T2',
            joining_date=self.today - timedelta(days=300),
            designation=designation,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )

        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_1,
            school_class=self.school_class,
            subject=self.math,
            is_active=True,
        )

        self.student_1 = self._create_student('EX-S1', '1')
        self.student_2 = self._create_student('EX-S2', '2')
        self.student_3 = self._create_student('EX-S3', '3')

        self.exam_type = ExamType.objects.create(
            school=self.school,
            session=self.session,
            name='Mid Term',
            is_active=True,
        )

    def _create_student(self, admission_no, roll_no):
        student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number=admission_no,
            first_name=admission_no,
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number=roll_no,
        )
        StudentSessionRecord.objects.create(
            student=student,
            school=self.school,
            session=self.session,
            school_class=self.school_class,
            section=self.section,
            roll_number=roll_no,
            is_current=True,
        )
        StudentSubject.objects.create(
            student=student,
            subject=self.math,
            school_class=self.school_class,
            session=self.session,
            is_active=True,
        )
        StudentSubject.objects.create(
            student=student,
            subject=self.science,
            school_class=self.school_class,
            session=self.session,
            is_active=True,
        )
        return student

    def _create_exam(self):
        exam = Exam.objects.create(
            school=self.school,
            session=self.session,
            exam_type=self.exam_type,
            school_class=self.school_class,
            section=self.section,
            start_date=self.today - timedelta(days=5),
            end_date=self.today - timedelta(days=1),
            total_marks=Decimal('100'),
            created_by=self.admin,
        )
        ExamSubject.objects.create(exam=exam, subject=self.math, max_marks=100, pass_marks=33, is_active=True)
        return exam


class ExamModelRuleTests(ExamsBaseTestCase):
    def test_exam_subject_requires_class_subject_mapping(self):
        exam = self._create_exam()
        exam_subject = ExamSubject(
            exam=exam,
            subject=self.computer,
            max_marks=Decimal('100'),
            pass_marks=Decimal('33'),
        )
        with self.assertRaises(ValidationError):
            exam_subject.full_clean()


class ExamServiceTests(ExamsBaseTestCase):
    def test_marks_entry_blocks_after_exam_lock(self):
        exam = self._create_exam()
        exam.is_locked = True
        exam.save(update_fields=['is_locked'])

        with self.assertRaises(ValidationError):
            upsert_student_mark(
                exam=exam,
                student=self.student_1,
                subject_id=self.math.id,
                marks_obtained=Decimal('78'),
                entered_by=self.admin,
            )

    def test_result_generation_requires_all_marks(self):
        exam = self._create_exam()
        ExamSubject.objects.create(exam=exam, subject=self.science, max_marks=100, pass_marks=33, is_active=True)

        upsert_student_mark(
            exam=exam,
            student=self.student_1,
            subject_id=self.math.id,
            marks_obtained=Decimal('80'),
            entered_by=self.admin,
        )

        with self.assertRaises(ValidationError):
            generate_exam_results(exam=exam)

    def test_rank_calculation_handles_ties(self):
        exam = self._create_exam()

        upsert_student_mark(
            exam=exam,
            student=self.student_1,
            subject_id=self.math.id,
            marks_obtained=Decimal('90'),
            entered_by=self.admin,
        )
        upsert_student_mark(
            exam=exam,
            student=self.student_2,
            subject_id=self.math.id,
            marks_obtained=Decimal('90'),
            entered_by=self.admin,
        )
        upsert_student_mark(
            exam=exam,
            student=self.student_3,
            subject_id=self.math.id,
            marks_obtained=Decimal('70'),
            entered_by=self.admin,
        )

        summaries = generate_exam_results(exam=exam)
        self.assertEqual(len(summaries), 3)
        rank_map = {
            row.student_id: row.rank
            for row in exam.result_summaries.all()
        }
        self.assertEqual(rank_map[self.student_1.id], 1)
        self.assertEqual(rank_map[self.student_2.id], 1)
        self.assertEqual(rank_map[self.student_3.id], 3)


class ExamViewTests(ExamsBaseTestCase):
    def test_schooladmin_can_create_exam_type(self):
        self.client.login(username='exam_admin', password='pass12345')
        response = self.client.post(reverse('exam_type_create'), {
            'session': self.session.id,
            'name': 'Unit Test',
            'weightage': '10',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExamType.objects.filter(school=self.school, name='Unit Test').exists())

    def test_teacher_with_assignment_can_enter_marks(self):
        exam = self._create_exam()
        self.client.login(username='exam_teacher_1', password='pass12345')
        response = self.client.post(reverse('marks_entry_core'), {
            'exam': exam.id,
            'subject': self.math.id,
            'action': 'save',
            f'marks_{self.student_1.id}': '84',
            f'remarks_{self.student_1.id}': 'Good',
            f'marks_{self.student_2.id}': '72',
            f'remarks_{self.student_2.id}': '',
            f'marks_{self.student_3.id}': '69',
            f'remarks_{self.student_3.id}': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            StudentMark.objects.filter(exam=exam, subject=self.math, school=self.school).count(),
            3,
        )

    def test_teacher_without_assignment_cannot_enter_marks(self):
        exam = self._create_exam()
        self.client.login(username='exam_teacher_2', password='pass12345')
        response = self.client.post(reverse('marks_entry_core'), {
            'exam': exam.id,
            'subject': self.math.id,
            'action': 'save',
            f'marks_{self.student_1.id}': '84',
            f'remarks_{self.student_1.id}': '',
            f'marks_{self.student_2.id}': '72',
            f'remarks_{self.student_2.id}': '',
            f'marks_{self.student_3.id}': '69',
            f'remarks_{self.student_3.id}': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudentMark.objects.filter(exam=exam, subject=self.math).count(), 0)

    def test_report_card_download_returns_pdf(self):
        exam = self._create_exam()
        upsert_student_mark(
            exam=exam,
            student=self.student_1,
            subject_id=self.math.id,
            marks_obtained=Decimal('88'),
            entered_by=self.admin,
        )
        upsert_student_mark(
            exam=exam,
            student=self.student_2,
            subject_id=self.math.id,
            marks_obtained=Decimal('77'),
            entered_by=self.admin,
        )
        upsert_student_mark(
            exam=exam,
            student=self.student_3,
            subject_id=self.math.id,
            marks_obtained=Decimal('66'),
            entered_by=self.admin,
        )
        generate_exam_results(exam=exam)

        self.client.login(username='exam_admin', password='pass12345')
        response = self.client.get(reverse('report_card_download', args=[exam.id, self.student_1.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])
