from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.staff.models import Staff
from apps.academics.students.models import Student
from apps.academics.timetable.models import TimetableEntry
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School


class TimetableManagementTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school_a = School.objects.create(name='Timetable School A')
        self.school_b = School.objects.create(name='Timetable School B')

        self.admin_a = self.user_model.objects.create_user(
            username='tt_admin_a',
            password='pass12345',
            role='schooladmin',
            school=self.school_a,
        )
        self.teacher_user_a = self.user_model.objects.create_user(
            username='tt_teacher_a',
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
        self.teacher_staff_a = Staff.objects.create(
            school=self.school_a,
            staff_id='TT-STF-A',
            first_name='Asha',
            last_name='Teacher',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
            user=self.teacher_user_a,
        )
        self.teacher_staff_a2 = Staff.objects.create(
            school=self.school_a,
            staff_id='TT-STF-A2',
            first_name='Ritu',
            last_name='Teacher',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
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
        self.teacher_staff_b = Staff.objects.create(
            school=self.school_b,
            staff_id='TT-STF-B',
            first_name='Bina',
            last_name='Teacher',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
        )

    def test_school_admin_can_create_timetable_entry(self):
        self.client.login(username='tt_admin_a', password='pass12345')
        response = self.client.post(reverse('timetable_manage'), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_a.id,
            'teacher': self.teacher_staff_a.id,
            'day_of_week': 'monday',
            'period_number': 1,
            'start_time': '09:00',
            'end_time': '09:45',
            'room': 'R-01',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TimetableEntry.objects.filter(
                school=self.school_a,
                school_class=self.class_a,
                section=self.section_a,
                subject=self.subject_a,
                day_of_week='monday',
                period_number=1,
            ).exists()
        )

    def test_school_admin_cannot_create_entry_with_other_school_subject(self):
        self.client.login(username='tt_admin_a', password='pass12345')
        response = self.client.post(reverse('timetable_manage'), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_b.id,
            'teacher': self.teacher_staff_a.id,
            'day_of_week': 'tuesday',
            'period_number': 2,
            'start_time': '10:00',
            'end_time': '10:45',
            'room': 'R-02',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(
            TimetableEntry.objects.filter(
                school=self.school_a,
                day_of_week='tuesday',
                period_number=2,
            ).exists()
        )

    def test_timetable_delete_requires_post(self):
        entry = TimetableEntry.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            teacher=self.teacher_staff_a,
            day_of_week='wednesday',
            period_number=3,
            start_time='11:00',
            end_time='11:45',
            room='R-03',
            is_active=True,
        )

        self.client.login(username='tt_admin_a', password='pass12345')
        response = self.client.get(reverse('timetable_delete', args=[entry.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(TimetableEntry.objects.filter(pk=entry.id).exists())

        response = self.client.post(reverse('timetable_delete', args=[entry.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TimetableEntry.objects.filter(pk=entry.id).exists())

    def test_teacher_cannot_access_timetable_manage(self):
        self.client.login(username='tt_teacher_a', password='pass12345')
        response = self.client.get(reverse('timetable_manage'))
        self.assertEqual(response.status_code, 403)

    def test_school_admin_cannot_create_overlapping_entry_for_same_class_section(self):
        TimetableEntry.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            teacher=self.teacher_staff_a,
            day_of_week='thursday',
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            room='R-01',
            is_active=True,
        )

        self.client.login(username='tt_admin_a', password='pass12345')
        response = self.client.post(reverse('timetable_manage'), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a.id,
            'section': self.section_a.id,
            'subject': self.subject_a.id,
            'teacher': self.teacher_staff_a2.id,
            'day_of_week': 'thursday',
            'period_number': 2,
            'start_time': '09:30',
            'end_time': '10:15',
            'room': 'R-02',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Time slot overlaps with another timetable entry for this class and section'
        )
        self.assertEqual(
            TimetableEntry.objects.filter(
                school=self.school_a,
                school_class=self.class_a,
                section=self.section_a,
                day_of_week='thursday'
            ).count(),
            1
        )

    def test_school_admin_cannot_create_overlapping_entry_for_same_teacher(self):
        TimetableEntry.objects.create(
            school=self.school_a,
            academic_session=self.session_a,
            school_class=self.class_a,
            section=self.section_a,
            subject=self.subject_a,
            teacher=self.teacher_staff_a,
            day_of_week='friday',
            period_number=1,
            start_time='10:00',
            end_time='10:45',
            room='R-01',
            is_active=True,
        )

        self.client.login(username='tt_admin_a', password='pass12345')
        response = self.client.post(reverse('timetable_manage'), {
            'academic_session': self.session_a.id,
            'school_class': self.class_a2.id,
            'section': self.section_a2.id,
            'subject': self.subject_a2.id,
            'teacher': self.teacher_staff_a.id,
            'day_of_week': 'friday',
            'period_number': 2,
            'start_time': '10:15',
            'end_time': '11:00',
            'room': 'R-03',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Selected teacher has another timetable entry in this time slot'
        )
        self.assertFalse(
            TimetableEntry.objects.filter(
                school=self.school_a,
                school_class=self.class_a2,
                section=self.section_a2,
                day_of_week='friday'
            ).exists()
        )


class TeacherAndParentTimetableViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Timetable View School')
        self.other_school = School.objects.create(name='Timetable Other School')

        self.teacher_user = self.user_model.objects.create_user(
            username='tt_teacher_view',
            password='pass12345',
            role='teacher',
            school=self.school,
        )
        self.parent_user = self.user_model.objects.create_user(
            username='tt_parent_view',
            password='pass12345',
            role='parent',
            school=self.school,
        )
        self.admin_user = self.user_model.objects.create_user(
            username='tt_admin_view',
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
            name='Class 6',
            order=6,
        )
        section_a = Section.objects.create(school_class=school_class, name='A')
        section_b = Section.objects.create(school_class=school_class, name='B')
        subject_math = Subject.objects.create(
            school=self.school,
            school_class=school_class,
            name='Math',
            code='MTH',
        )
        subject_eng = Subject.objects.create(
            school=self.school,
            school_class=school_class,
            name='English',
            code='ENG',
        )

        self.teacher_staff = Staff.objects.create(
            school=self.school,
            staff_id='TT-VIEW-T1',
            first_name='Kiran',
            last_name='Teacher',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
            user=self.teacher_user,
        )
        other_teacher = Staff.objects.create(
            school=self.school,
            staff_id='TT-VIEW-T2',
            first_name='Nita',
            last_name='Teacher',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
        )

        self.student = Student.objects.create(
            school=self.school,
            admission_number='TT-STD-1',
            first_name='Rohan',
            last_name='M',
            school_class=school_class,
            section=section_a,
            academic_session=self.session,
            parent_user=self.parent_user,
        )

        TimetableEntry.objects.create(
            school=self.school,
            academic_session=self.session,
            school_class=school_class,
            section=section_a,
            subject=subject_math,
            teacher=self.teacher_staff,
            day_of_week='monday',
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            room='A1',
            is_active=True,
        )
        TimetableEntry.objects.create(
            school=self.school,
            academic_session=self.session,
            school_class=school_class,
            section=section_a,
            subject=subject_eng,
            teacher=other_teacher,
            day_of_week='monday',
            period_number=2,
            start_time='10:00',
            end_time='10:45',
            room='A2',
            is_active=True,
        )
        TimetableEntry.objects.create(
            school=self.school,
            academic_session=self.session,
            school_class=school_class,
            section=section_b,
            subject=subject_math,
            teacher=self.teacher_staff,
            day_of_week='tuesday',
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            room='B1',
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
            name='Class 7',
            order=7,
        )
        other_section = Section.objects.create(school_class=other_class, name='A')
        other_subject = Subject.objects.create(
            school=self.other_school,
            school_class=other_class,
            name='Science',
            code='SCI',
        )
        TimetableEntry.objects.create(
            school=self.other_school,
            academic_session=other_session,
            school_class=other_class,
            section=other_section,
            subject=other_subject,
            day_of_week='wednesday',
            period_number=1,
            start_time='09:00',
            end_time='09:45',
            room='O1',
            is_active=True,
        )

    def test_teacher_sees_only_own_assigned_entries(self):
        self.client.login(username='tt_teacher_view', password='pass12345')
        response = self.client.get(reverse('teacher_timetable'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A1')
        self.assertContains(response, 'B1')
        self.assertNotContains(response, 'A2')
        self.assertNotContains(response, 'O1')

    def test_parent_sees_only_child_section_entries(self):
        self.client.login(username='tt_parent_view', password='pass12345')
        response = self.client.get(reverse('parent_timetable'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A1')
        self.assertContains(response, 'A2')
        self.assertNotContains(response, 'B1')
        self.assertNotContains(response, 'O1')
