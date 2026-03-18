from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.fees.models import LedgerEntry
from apps.core.hr.models import Designation, Staff
from apps.core.schools.models import School
from apps.core.students.models import Student

from .models import Book, StockItem, Vendor
from .services import issue_book, record_purchase, return_book


class InventoryBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.today = timezone.localdate()

        self.school = School.objects.create(name='Inventory School', code='inventory_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date=self.today - timedelta(days=90),
            end_date=self.today + timedelta(days=270),
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.admin = user_model.objects.create_user(
            username='inventory_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.accountant = user_model.objects.create_user(
            username='inventory_accountant',
            password='pass12345',
            role='accountant',
            school=self.school,
        )

        designation = Designation.objects.create(school=self.school, name='Librarian')
        self.staff_user = user_model.objects.create_user(
            username='inventory_staff',
            password='pass12345',
            role='staff',
            school=self.school,
        )
        self.staff = Staff.objects.create(
            school=self.school,
            user=self.staff_user,
            employee_id='INV-STF-01',
            joining_date=self.today - timedelta(days=120),
            designation=designation,
            status=Staff.STATUS_ACTIVE,
            is_active=True,
        )

        self.student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='INV-S1',
            first_name='Nia',
            admission_type=Student.ADMISSION_FRESH,
        )

        self.vendor = Vendor.objects.create(
            school=self.school,
            vendor_name='Stationers Hub',
            phone='9000000002',
            is_active=True,
        )
        self.stock_item = StockItem.objects.create(
            school=self.school,
            item_name='Notebook',
            item_code='NB-01',
            category='Stationery',
            quantity_available=10,
            minimum_threshold=5,
            unit_price=Decimal('25.00'),
            is_active=True,
        )
        self.book = Book.objects.create(
            school=self.school,
            title='Physics Basics',
            author='A. Writer',
            isbn='ISBN-001',
            category='Science',
            total_copies=5,
            available_copies=5,
            is_active=True,
        )


class InventoryServiceTests(InventoryBaseTestCase):
    def test_purchase_updates_stock_and_creates_ledger_entry(self):
        purchase, _ = record_purchase(
            school=self.school,
            session=self.session,
            vendor=self.vendor,
            purchase_date=self.today,
            invoice_number='INV-100',
            items=[{
                'stock_item': self.stock_item,
                'quantity': 4,
                'unit_price': Decimal('30.00'),
            }],
            created_by=self.admin,
        )

        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.quantity_available, 14)
        self.assertEqual(purchase.total_amount, Decimal('120.00'))
        self.assertTrue(
            LedgerEntry.objects.filter(
                school=self.school,
                transaction_type=LedgerEntry.TYPE_EXPENSE,
                reference_model='Purchase',
                reference_id=str(purchase.id),
            ).exists()
        )

    def test_book_issue_and_return_updates_copies_and_fine(self):
        issue = issue_book(
            school=self.school,
            session=self.session,
            book=self.book,
            issued_student=self.student,
            issue_date=self.today - timedelta(days=5),
            due_date=self.today - timedelta(days=2),
            issued_by=self.admin,
        )
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 4)

        issue, _ = return_book(
            issue=issue,
            return_date=self.today,
            fine_per_day=Decimal('10.00'),
            returned_by=self.admin,
        )
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 5)
        self.assertEqual(issue.fine_amount, Decimal('20.00'))

    def test_issue_book_blocks_when_no_copy_available(self):
        self.book.available_copies = 0
        self.book.save(update_fields=['available_copies'])
        with self.assertRaises(ValidationError):
            issue_book(
                school=self.school,
                session=self.session,
                book=self.book,
                issued_staff=self.staff,
                issue_date=self.today,
                due_date=self.today + timedelta(days=7),
                issued_by=self.admin,
            )


class InventoryViewTests(InventoryBaseTestCase):
    def test_schooladmin_can_open_purchase_page(self):
        self.client.login(username='inventory_admin', password='pass12345')
        response = self.client.get(reverse('inventory_purchase_list_core'))
        self.assertEqual(response.status_code, 200)

    def test_accountant_can_open_purchase_report_page(self):
        self.client.login(username='inventory_accountant', password='pass12345')
        response = self.client.get(reverse('inventory_report_purchases_core'))
        self.assertEqual(response.status_code, 200)
