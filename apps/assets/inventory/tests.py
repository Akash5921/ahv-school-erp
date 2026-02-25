from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.assets.inventory.models import InventoryCategory, InventoryItem, InventoryPurchase
from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School
from apps.finance.accounts.models import Ledger


class InventoryWorkflowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.school = School.objects.create(name='Inventory School')
        self.admin = self.user_model.objects.create_user(
            username='inventory_admin',
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

        self.category = InventoryCategory.objects.create(name='Science Lab')
        self.item = InventoryItem.objects.create(
            school=self.school,
            category=self.category,
            name='Microscope',
            location='Lab 1',
            quantity=5,
        )

    def test_inventory_purchase_updates_stock_and_creates_ledger_entry(self):
        self.client.login(username='inventory_admin', password='pass12345')
        response = self.client.post(reverse('inventory_purchase'), {
            'item': self.item.id,
            'quantity_purchased': 3,
            'total_cost': '1500.00',
        })

        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)

        purchase = InventoryPurchase.objects.get(item=self.item, academic_session=self.session)
        self.assertEqual(purchase.total_cost, Decimal('1500.00'))

        self.assertTrue(
            Ledger.objects.filter(
                school=self.school,
                academic_session=self.session,
                entry_type='expense',
                description=f'Inventory purchase: {self.item.name}',
                amount=Decimal('1500.00'),
                transaction_date=purchase.purchase_date,
            ).exists()
        )
