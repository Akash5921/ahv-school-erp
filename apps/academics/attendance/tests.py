from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.attendance.models import StaffAttendance
from apps.academics.staff.models import Staff
from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School


class StaffAttendanceTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Attendance School')
        self.admin = self.user_model.objects.create_user(
            username='attendance_admin',
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

        self.staff = Staff.objects.create(
            school=self.school,
            staff_id='STAFF-AT-1',
            first_name='Anil',
            last_name='Singh',
            staff_type='teacher',
            joining_date='2025-01-01',
            is_active=True,
        )

    def test_school_admin_can_mark_staff_attendance(self):
        self.client.login(username='attendance_admin', password='pass12345')
        response = self.client.post(reverse('mark_staff_attendance'), {
            f'status_{self.staff.id}': 'present'
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            StaffAttendance.objects.filter(
                school=self.school,
                academic_session=self.session,
                staff=self.staff,
                status='present'
            ).exists()
        )
