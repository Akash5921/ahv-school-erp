from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, Period, SchoolClass, Section, Subject
from apps.core.hr.models import Designation, Staff, Substitution, TeacherSubjectAssignment
from apps.core.schools.models import School

from .models import TimetableEntry
from .services import build_class_timetable_grid


class TimetableBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.school = School.objects.create(name='Timetable School', code='timetable_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.class_9 = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='9th',
            code='IX',
            display_order=9,
        )
        self.section_a = Section.objects.create(school_class=self.class_9, name='A')

        self.class_10 = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='10th',
            code='X',
            display_order=10,
        )
        self.section_b = Section.objects.create(school_class=self.class_10, name='B')

        self.subject_math = Subject.objects.create(school=self.school, name='Math', code='MTH')
        self.subject_science = Subject.objects.create(school=self.school, name='Science', code='SCI')

        ClassSubject.objects.create(school_class=self.class_9, subject=self.subject_math)
        ClassSubject.objects.create(school_class=self.class_10, subject=self.subject_math)

        self.period_1 = Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=1,
            start_time='09:00',
            end_time='09:40',
            is_active=True,
        )
        self.period_2 = Period.objects.create(
            school=self.school,
            session=self.session,
            period_number=2,
            start_time='09:40',
            end_time='10:20',
            is_active=True,
        )

        self.admin_user = user_model.objects.create_user(
            username='tt_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher_user_1 = user_model.objects.create_user(
            username='tt_teacher_1',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.teacher_user_2 = user_model.objects.create_user(
            username='tt_teacher_2',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

        designation = Designation.objects.create(school=self.school, name='Teacher')
        self.teacher_1 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_1,
            employee_id='T001',
            joining_date='2026-04-05',
            designation=designation,
            status='active',
            is_active=True,
        )
        self.teacher_2 = Staff.objects.create(
            school=self.school,
            user=self.teacher_user_2,
            employee_id='T002',
            joining_date='2026-04-05',
            designation=designation,
            status='active',
            is_active=True,
        )

        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_1,
            school_class=self.class_9,
            subject=self.subject_math,
            is_active=True,
        )
        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_2,
            school_class=self.class_9,
            subject=self.subject_math,
            is_active=True,
        )
        TeacherSubjectAssignment.objects.create(
            school=self.school,
            session=self.session,
            teacher=self.teacher_1,
            school_class=self.class_10,
            subject=self.subject_math,
            is_active=True,
        )


class TimetableModelRuleTests(TimetableBaseTestCase):
    def test_teacher_conflict_blocks_double_booking(self):
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        entry = TimetableEntry(
            school=self.school,
            session=self.session,
            school_class=self.class_10,
            section=self.section_b,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_subject_must_be_mapped_to_class(self):
        entry = TimetableEntry(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='tuesday',
            period=self.period_1,
            subject=self.subject_science,
            teacher=self.teacher_1,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_teacher_must_be_assigned_for_class_subject(self):
        ClassSubject.objects.create(school_class=self.class_9, subject=self.subject_science)

        entry = TimetableEntry(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='wednesday',
            period=self.period_1,
            subject=self.subject_science,
            teacher=self.teacher_1,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_same_slot_in_class_section_is_unique(self):
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='thursday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        entry = TimetableEntry(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='thursday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_2,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()


class TimetableSubstitutionTests(TimetableBaseTestCase):
    def test_grid_overlays_substitute_teacher(self):
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        Substitution.objects.create(
            school=self.school,
            session=self.session,
            date=date(2026, 4, 20),
            period=self.period_1,
            school_class=self.class_9,
            section=self.section_a,
            subject=self.subject_math,
            original_teacher=self.teacher_1,
            substitute_teacher=self.teacher_2,
            is_active=True,
        )

        periods = Period.objects.filter(school=self.school, session=self.session, is_active=True).order_by('period_number')
        rows = build_class_timetable_grid(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            periods=periods,
            view_date=date(2026, 4, 20),
        )

        monday_row = next(row for row in rows if row['day_key'] == 'monday')
        first_cell = next(cell for cell in monday_row['cells'] if cell['period'].id == self.period_1.id)

        self.assertIsNotNone(first_cell['entry'])
        self.assertIsNotNone(first_cell['substitution'])
        self.assertEqual(first_cell['effective_teacher'], self.teacher_2)

    def test_substitution_shifts_slot_responsibility(self):
        entry = TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        Substitution.objects.create(
            school=self.school,
            session=self.session,
            date=date(2026, 4, 20),
            period=self.period_1,
            school_class=self.class_9,
            section=self.section_a,
            subject=self.subject_math,
            original_teacher=self.teacher_1,
            substitute_teacher=self.teacher_2,
            is_active=True,
        )

        from .services import teacher_can_handle_slot

        self.assertFalse(
            teacher_can_handle_slot(entry=entry, teacher=self.teacher_1, target_date=date(2026, 4, 20))
        )
        self.assertTrue(
            teacher_can_handle_slot(entry=entry, teacher=self.teacher_2, target_date=date(2026, 4, 20))
        )


class TimetableViewTests(TimetableBaseTestCase):
    def test_schooladmin_can_create_timetable_cell(self):
        self.client.login(username='tt_admin', password='pass12345')

        response = self.client.post(
            reverse('timetable_cell_edit', args=[self.class_9.id, self.section_a.id, 'monday', self.period_1.id]) + f'?session={self.session.id}',
            {
                'session': self.session.id,
                'school_class': self.class_9.id,
                'section': self.section_a.id,
                'day_of_week': 'monday',
                'period': self.period_1.id,
                'subject': self.subject_math.id,
                'teacher': self.teacher_1.id,
                'is_active': 'on',
                'view_date': '2026-04-20',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TimetableEntry.objects.filter(
                school=self.school,
                session=self.session,
                school_class=self.class_9,
                section=self.section_a,
                day_of_week='monday',
                period=self.period_1,
                teacher=self.teacher_1,
                is_active=True,
            ).exists()
        )

    def test_teacher_cannot_access_admin_grid(self):
        self.client.login(username='tt_teacher_1', password='pass12345')
        response = self.client.get(reverse('timetable_class_grid'))
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_view_own_timetable(self):
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        self.client.login(username='tt_teacher_1', password='pass12345')
        response = self.client.get(reverse('timetable_teacher_view'), {'session': self.session.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teacher Timetable')
        self.assertContains(response, 'MTH')

    def test_class_timetable_pdf_export(self):
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        self.client.login(username='tt_admin', password='pass12345')
        response = self.client.get(
            reverse('timetable_class_pdf', args=[self.class_9.id, self.section_a.id]),
            {'session': self.session.id, 'view_date': '2026-04-20'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])

    def test_teacher_timetable_pdf_export(self):
        TimetableEntry.objects.create(
            school=self.school,
            session=self.session,
            school_class=self.class_9,
            section=self.section_a,
            day_of_week='monday',
            period=self.period_1,
            subject=self.subject_math,
            teacher=self.teacher_1,
            is_active=True,
        )

        self.client.login(username='tt_teacher_1', password='pass12345')
        response = self.client.get(reverse('timetable_teacher_pdf'), {'session': self.session.id})

        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])
