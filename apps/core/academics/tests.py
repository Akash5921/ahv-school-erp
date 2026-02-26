from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import AcademicConfig, ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.schools.models import School


class AcademicMasterWorkflowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Phase1 School', code='phase1_school')
        self.admin = self.user_model.objects.create_user(
            username='phase1_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher = self.user_model.objects.create_user(
            username='phase1_teacher',
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
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

    def test_school_admin_can_configure_full_academic_master_for_session(self):
        self.client.login(username='phase1_admin', password='pass12345')

        class_response = self.client.post(reverse('class_create'), {
            'session': self.session.id,
            'name': '10th',
            'code': 'X',
            'display_order': 10,
            'is_active': 'on',
        })
        self.assertEqual(class_response.status_code, 302)
        school_class = SchoolClass.objects.get(school=self.school, session=self.session, name='10th')

        section_response = self.client.post(reverse('section_create'), {
            'school_class': school_class.id,
            'name': 'A',
            'capacity': 45,
            'class_teacher': self.teacher.id,
            'is_active': 'on',
        })
        self.assertEqual(section_response.status_code, 302)
        self.assertTrue(
            Section.objects.filter(
                school_class=school_class,
                name='A',
                class_teacher=self.teacher,
            ).exists()
        )

        subject_response = self.client.post(reverse('subject_create'), {
            'name': 'Mathematics',
            'code': 'MTH',
            'subject_type': 'theory',
            'is_optional': False,
            'is_active': True,
        })
        self.assertEqual(subject_response.status_code, 302)
        subject = Subject.objects.get(school=self.school, code='MTH')

        mapping_response = self.client.post(reverse('class_subject_create'), {
            'school_class': school_class.id,
            'subject': subject.id,
            'is_compulsory': True,
            'max_marks': '100',
            'pass_marks': '33',
        })
        self.assertEqual(mapping_response.status_code, 302)
        self.assertTrue(
            ClassSubject.objects.filter(school_class=school_class, subject=subject).exists()
        )

        period_response = self.client.post(reverse('period_create'), {
            'session': self.session.id,
            'period_number': 1,
            'start_time': '09:00',
            'end_time': '09:45',
            'is_active': 'on',
        })
        self.assertEqual(period_response.status_code, 302)
        self.assertTrue(
            Period.objects.filter(
                school=self.school,
                session=self.session,
                period_number=1,
            ).exists()
        )

        config_response = self.client.post(reverse('academic_config_create'), {
            'session': self.session.id,
            'total_periods_per_day': 8,
            'working_days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
            'grading_enabled': True,
            'attendance_type': 'daily',
            'marks_decimal_allowed': False,
        })
        self.assertEqual(config_response.status_code, 302)
        self.assertTrue(
            AcademicConfig.objects.filter(school=self.school, session=self.session).exists()
        )

    def test_teacher_cannot_access_academic_master_pages(self):
        self.client.login(username='phase1_teacher', password='pass12345')
        response = self.client.get(reverse('class_list'))
        self.assertEqual(response.status_code, 403)


class ClassAndSectionRulesTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school_a = School.objects.create(name='School A', code='school_a')
        self.school_b = School.objects.create(name='School B', code='school_b')
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

    def test_class_unique_per_school_and_session(self):
        SchoolClass.objects.create(
            school=self.school_a,
            session=self.session_a,
            name='1st',
            code='I',
        )
        with self.assertRaises(IntegrityError):
            SchoolClass.objects.create(
                school=self.school_a,
                session=self.session_a,
                name='1st',
                code='I-B',
            )

    def test_class_must_belong_to_its_session_school(self):
        school_class = SchoolClass(
            school=self.school_a,
            session=self.session_b,
            name='2nd',
            code='II',
        )
        with self.assertRaises(ValidationError):
            school_class.full_clean()

    def test_class_delete_soft_deactivates_when_no_sections(self):
        school_class = SchoolClass.objects.create(
            school=self.school_a,
            session=self.session_a,
            name='3rd',
            code='III',
        )
        school_class.delete()
        school_class.refresh_from_db()
        self.assertFalse(school_class.is_active)

    def test_class_delete_fails_if_sections_exist(self):
        school_class = SchoolClass.objects.create(
            school=self.school_a,
            session=self.session_a,
            name='4th',
            code='IV',
        )
        Section.objects.create(
            school_class=school_class,
            name='A',
        )
        with self.assertRaises(ValidationError):
            school_class.delete()
        school_class.refresh_from_db()
        self.assertTrue(school_class.is_active)

    def test_section_unique_per_class(self):
        school_class = SchoolClass.objects.create(
            school=self.school_a,
            session=self.session_a,
            name='5th',
            code='V',
        )
        Section.objects.create(school_class=school_class, name='A')
        with self.assertRaises(IntegrityError):
            Section.objects.create(school_class=school_class, name='A')


class SubjectAndMappingRulesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Subject School', code='subject_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='10th',
            code='X',
        )

    def test_subject_unique_code_per_school(self):
        Subject.objects.create(
            school=self.school,
            name='Mathematics',
            code='MTH',
        )
        with self.assertRaises(IntegrityError):
            Subject.objects.create(
                school=self.school,
                name='Math Advanced',
                code='MTH',
            )

    def test_only_active_subject_can_be_mapped(self):
        subject = Subject.objects.create(
            school=self.school,
            name='Physics',
            code='PHY',
            is_active=False,
        )
        mapping = ClassSubject(
            school_class=self.school_class,
            subject=subject,
            max_marks='100',
            pass_marks='33',
        )
        with self.assertRaises(ValidationError):
            mapping.full_clean()

    def test_pass_marks_cannot_exceed_max_marks(self):
        subject = Subject.objects.create(
            school=self.school,
            name='Chemistry',
            code='CHE',
        )
        mapping = ClassSubject(
            school_class=self.school_class,
            subject=subject,
            max_marks='50',
            pass_marks='60',
        )
        with self.assertRaises(ValidationError):
            mapping.full_clean()

    def test_class_subject_unique_mapping(self):
        subject = Subject.objects.create(
            school=self.school,
            name='English',
            code='ENG',
        )
        ClassSubject.objects.create(
            school_class=self.school_class,
            subject=subject,
            max_marks='100',
            pass_marks='33',
        )
        with self.assertRaises(IntegrityError):
            ClassSubject.objects.create(
                school_class=self.school_class,
                subject=subject,
                max_marks='100',
                pass_marks='33',
            )


class PeriodAndConfigRulesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Period School', code='period_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )

    def test_period_cannot_overlap(self):
        Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            is_active=True,
        )
        period = Period(
            school=self.school,
            session=self.session,
            period_number=2,
            start_time='09:30',
            end_time='10:15',
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            period.full_clean()

    def test_period_duration_must_be_consistent(self):
        Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            is_active=True,
        )
        period = Period(
            school=self.school,
            session=self.session,
            period_number=2,
            start_time='10:00',
            end_time='11:00',
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            period.full_clean()

    def test_period_unique_period_number_per_session(self):
        Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            is_active=True,
        )
        with self.assertRaises(IntegrityError):
            Period.objects.create(
                school=self.school,
                session=self.session,
                period_number=1,
                start_time='10:00',
                end_time='10:45',
                is_active=True,
            )

    def test_academic_config_unique_per_school_session(self):
        AcademicConfig.objects.create(
            school=self.school,
            session=self.session,
            total_periods_per_day=8,
            working_days=['monday', 'tuesday'],
            grading_enabled=True,
            attendance_type='daily',
            marks_decimal_allowed=False,
        )
        with self.assertRaises(IntegrityError):
            AcademicConfig.objects.create(
                school=self.school,
                session=self.session,
                total_periods_per_day=7,
                working_days=['monday', 'tuesday'],
                grading_enabled=False,
                attendance_type='period-wise',
                marks_decimal_allowed=True,
            )

    def test_academic_config_requires_valid_working_days(self):
        config = AcademicConfig(
            school=self.school,
            session=self.session,
            total_periods_per_day=8,
            working_days=['monday', 'funday'],
            grading_enabled=True,
            attendance_type='daily',
            marks_decimal_allowed=False,
        )
        with self.assertRaises(ValidationError):
            config.full_clean()
