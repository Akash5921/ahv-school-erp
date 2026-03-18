from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.fees.models import FeeType, StudentFee
from apps.core.schools.models import School
from apps.core.students.models import Student

from .models import Driver, Route, RouteStop, Vehicle
from .services import assign_student_transport, deactivate_student_transport


class TransportBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()

        self.school = School.objects.create(name='Transport School', code='transport_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.today - timedelta(days=90),
            end_date=self.today + timedelta(days=270),
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='7th',
            code='VII',
            display_order=7,
            is_active=True,
        )
        self.section = Section.objects.create(
            school_class=self.school_class,
            name='A',
            is_active=True,
        )
        self.student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='TR-001',
            first_name='Rohan',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number='1',
        )

        self.admin = user_model.objects.create_user(
            username='transport_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.accountant = user_model.objects.create_user(
            username='transport_accountant',
            password='pass12345',
            role='accountant',
            school=self.school,
        )

        self.driver = Driver.objects.create(
            school=self.school,
            name='Driver One',
            license_number='LIC-1001',
            phone='9000000001',
            joining_date=self.today - timedelta(days=120),
            is_active=True,
        )
        self.vehicle = Vehicle.objects.create(
            school=self.school,
            vehicle_number='BUS-01',
            vehicle_type=Vehicle.TYPE_BUS,
            capacity=40,
            assigned_driver=self.driver,
            is_active=True,
        )
        self.route = Route.objects.create(
            school=self.school,
            route_name='North Route',
            start_point='Gate 1',
            end_point='North Colony',
            vehicle=self.vehicle,
            default_fee=Decimal('1200.00'),
            is_active=True,
        )
        RouteStop.objects.create(route=self.route, stop_name='Stop A', stop_order=1)


class TransportServiceTests(TransportBaseTestCase):
    def test_student_transport_assignment_creates_transport_fee(self):
        allocation = assign_student_transport(
            school=self.school,
            session=self.session,
            student=self.student,
            route=self.route,
            stop_name='Stop A',
            transport_fee=Decimal('1500.00'),
        )

        self.assertTrue(allocation.is_active)
        self.student.refresh_from_db()
        self.assertTrue(self.student.transport_assigned)

        transport_fee_type = FeeType.objects.get(school=self.school, category=FeeType.CATEGORY_TRANSPORT)
        fee_row = StudentFee.objects.get(
            school=self.school,
            session=self.session,
            student=self.student,
            fee_type=transport_fee_type,
            is_carry_forward=False,
        )
        self.assertEqual(fee_row.total_amount, Decimal('1500.00'))
        self.assertTrue(fee_row.is_active)

    def test_deactivate_transport_allocation_deactivates_student_fee(self):
        allocation = assign_student_transport(
            school=self.school,
            session=self.session,
            student=self.student,
            route=self.route,
            stop_name='Stop A',
            transport_fee=Decimal('1100.00'),
        )

        deactivate_student_transport(allocation=allocation)

        self.student.refresh_from_db()
        self.assertFalse(self.student.transport_assigned)

        fee_row = StudentFee.objects.filter(
            school=self.school,
            session=self.session,
            student=self.student,
            fee_type__category=FeeType.CATEGORY_TRANSPORT,
            is_carry_forward=False,
        ).first()
        self.assertIsNotNone(fee_row)
        self.assertFalse(fee_row.is_active)

    def test_vehicle_blocks_inactive_driver_assignment(self):
        self.driver.is_active = False
        self.driver.save(update_fields=['is_active'])
        self.vehicle.assigned_driver = self.driver
        with self.assertRaises(ValidationError):
            self.vehicle.full_clean()


class TransportViewTests(TransportBaseTestCase):
    def test_schooladmin_can_open_transport_allocation_page(self):
        self.client.login(username='transport_admin', password='pass12345')
        response = self.client.get(reverse('transport_student_allocation_list_core'))
        self.assertEqual(response.status_code, 200)

    def test_accountant_can_open_transport_fee_pending_report(self):
        self.client.login(username='transport_accountant', password='pass12345')
        response = self.client.get(reverse('transport_report_fee_pending_core'))
        self.assertEqual(response.status_code, 200)
