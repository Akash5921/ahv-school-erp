from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.staff.models import Staff
from apps.academics.students.models import Student
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.schools.models import School
from apps.operations.transport.models import Bus, Route, StudentTransport


class TransportWorkflowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Transport School')
        self.admin = self.user_model.objects.create_user(
            username='transport_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher = self.user_model.objects.create_user(
            username='transport_teacher',
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

        school_class = SchoolClass.objects.create(school=self.school, name='Class 5')
        section = Section.objects.create(school_class=school_class, name='A')
        self.student_1 = Student.objects.create(
            school=self.school,
            admission_number='TR-1001',
            first_name='Piya',
            last_name='Nair',
            academic_session=self.session,
            school_class=school_class,
            section=section,
        )
        self.student_2 = Student.objects.create(
            school=self.school,
            admission_number='TR-1002',
            first_name='Arjun',
            last_name='Das',
            academic_session=self.session,
            school_class=school_class,
            section=section,
        )

        self.driver = Staff.objects.create(
            school=self.school,
            staff_id='DRV-1001',
            first_name='Ravi',
            last_name='Kumar',
            staff_type='driver',
            joining_date='2025-01-01',
            is_active=True,
        )

        self.bus = Bus.objects.create(
            school=self.school,
            bus_number='BUS-01',
            capacity=1,
            driver=self.driver,
        )
        self.route = Route.objects.create(
            school=self.school,
            name='Route A',
            start_point='Main Gate',
            end_point='City Center',
        )

    def test_school_admin_can_assign_student_transport(self):
        self.client.login(username='transport_admin', password='pass12345')
        response = self.client.post(reverse('transport_student_manage'), {
            'student': self.student_1.id,
            'bus': self.bus.id,
            'route': self.route.id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            StudentTransport.objects.filter(
                student=self.student_1,
                academic_session=self.session,
                bus=self.bus,
                route=self.route,
            ).exists()
        )

    def test_bus_capacity_prevents_extra_assignment(self):
        self.client.login(username='transport_admin', password='pass12345')
        self.client.post(reverse('transport_student_manage'), {
            'student': self.student_1.id,
            'bus': self.bus.id,
            'route': self.route.id,
        })
        response = self.client.post(reverse('transport_student_manage'), {
            'student': self.student_2.id,
            'bus': self.bus.id,
            'route': self.route.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is full')
        self.assertFalse(
            StudentTransport.objects.filter(
                student=self.student_2,
                academic_session=self.session,
            ).exists()
        )

    def test_teacher_cannot_access_transport_management(self):
        self.client.login(username='transport_teacher', password='pass12345')
        response = self.client.get(reverse('transport_student_manage'))
        self.assertEqual(response.status_code, 403)
