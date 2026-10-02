from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.utils import to_decimal, to_int
from finance.models import Invoice
from tracker.models import Customer, InventoryItem, OrderItem


class ParsingHelperTests(TestCase):
    def test_decimal_handles_bad_and_greek_input(self):
        self.assertEqual(to_decimal('12,50'), Decimal('12.50'))
        self.assertEqual(to_decimal('1,234.50'), Decimal('1234.50'))
        self.assertEqual(to_decimal('abc'), Decimal('0.00'))
        self.assertEqual(to_decimal(None, default='3'), Decimal('3.00'))
        self.assertEqual(to_decimal('-5', minimum=0), Decimal('0.00'))
        self.assertEqual(to_decimal('NaN'), Decimal('0.00'))

    def test_int_handles_bad_input(self):
        self.assertEqual(to_int('x', 1, 1), 1)
        self.assertEqual(to_int('-4', 1, 1), 1)
        self.assertEqual(to_int('7'), 7)


class AuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('tester', password='correct-horse-battery')

    def test_pages_require_login(self):
        for name in ('app_hub', 'orders_dashboard', 'inventory_list', 'finance:export_finances'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn('/login/', response['Location'], name)

    def test_login_works_and_hub_loads(self):
        self.assertTrue(self.client.login(username='tester', password='correct-horse-battery'))
        self.assertEqual(self.client.get(reverse('app_hub')).status_code, 200)

    def test_login_locks_out_after_five_failures(self):
        for _ in range(5):
            self.client.post(reverse('login'), {'username': 'tester', 'password': 'wrong'})
        response = self.client.post(reverse('login'), {'username': 'tester', 'password': 'correct-horse-battery'})
        self.assertEqual(response.status_code, 429)


class OrderBehaviourTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user('tester', password='pw-for-tests-123')
        self.client.login(username='tester', password='pw-for-tests-123')
        self.customer = Customer.objects.create(name='M/V Test')
        self.order = Invoice.objects.create(invoice_number='ORD-1', customer=self.customer, status='PENDING')

    def test_valid_status_change(self):
        self.client.post(reverse('change_order_status', args=[self.order.id, 'delivered']))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'DELIVERED')

    def test_invalid_status_is_rejected(self):
        self.client.post(reverse('change_order_status', args=[self.order.id, 'hacked']))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'PENDING')

    def test_status_change_does_not_redirect_offsite(self):
        response = self.client.post(
            reverse('change_order_status', args=[self.order.id, 'processing']),
            HTTP_REFERER='https://evil.example.com/steal',
        )
        self.assertNotIn('evil.example.com', response['Location'])

    def test_money_is_exact_decimal(self):
        item = OrderItem.objects.create(order=self.order, description='Gasket', quantity=3, unit_price=Decimal('0.10'))
        self.assertEqual(item.total_price, Decimal('0.30'))

    def test_stock_never_goes_negative(self):
        part = InventoryItem.objects.create(part_name='Filter', quantity=0)
        self.client.post(reverse('adjust_stock', args=[part.id, 'decrease']))
        part.refresh_from_db()
        self.assertEqual(part.quantity, 0)

    def test_csv_export_downloads(self):
        response = self.client.get(reverse('finance:export_finances'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('ORD-1', response.content.decode('utf-8'))
