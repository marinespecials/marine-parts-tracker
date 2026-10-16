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


class CategoryGuessTests(TestCase):
    def test_keywords_pick_the_right_category(self):
        from tracker.models import guess_category
        self.assertEqual(guess_category('Racor oil filter 2010PM'), 'Filters')  # filter beats oil
        self.assertEqual(guess_category('Raw water pump impeller'), 'Pumps')
        self.assertEqual(guess_category('Μπαταρια AGM 100Ah'), 'Electrical')
        self.assertEqual(guess_category('LED deck lamp'), 'Electrical')
        self.assertEqual(guess_category('Assembled bracket'), 'General')  # "led" inside a word must not match
        self.assertEqual(guess_category('Shaft zinc anode'), 'Anodes')
        self.assertEqual(guess_category('Something odd'), 'General')


class PagesAndLinksTests(TestCase):
    """Every page renders with real-looking data, and the new connected pages work."""

    def setUp(self):
        cache.clear()
        from finance.models import PriceRecord, MasterPricelistItem
        from tracker.models import Supplier, PurchaseOrder, PurchaseOrderItem
        User.objects.create_user('tester', password='pw-for-tests-123')
        self.client.login(username='tester', password='pw-for-tests-123')
        self.customer = Customer.objects.create(name='M/V Aegean Star')
        self.part = InventoryItem.objects.create(part_name='Oil filter', part_code='OF-1', category='General',
                                                 quantity=2, reorder_level=5, unit_cost=Decimal('12.50'))
        self.order = Invoice.objects.create(invoice_number='ORD-1001', customer=self.customer, status='PENDING')
        OrderItem.objects.create(order=self.order, inventory_item=self.part, description='Oil filter', quantity=1, unit_price=Decimal('20'))
        self.invoice = Invoice.objects.create(invoice_number='INV-1001', customer=self.customer, status='UNPAID', total_amount=Decimal('20'))
        self.supplier = Supplier.objects.create(name='Jabsco Hellas', email='orders@example.com')
        self.po = PurchaseOrder.objects.create(po_number='PO-1', supplier=self.supplier)
        PurchaseOrderItem.objects.create(purchase_order=self.po, inventory_item=self.part, quantity=10, unit_cost=Decimal('9'))
        PriceRecord.objects.create(part_name='Oil filter', supplier_or_client_name='Jabsco Hellas', unit_price=Decimal('9'))
        MasterPricelistItem.objects.create(part_name='Oil filter', part_code='OF-1', cost_price=Decimal('10'))

    def test_every_page_renders(self):
        pages = [
            reverse('hub'), reverse('active_board'), reverse('orders_dashboard') + '?status=ALL', reverse('create_order'),
            reverse('order_detail', args=[self.order.id]), reverse('mobile_packing_list', args=[self.order.id]),
            reverse('inventory_list'), reverse('inventory_list') + '?filter=LOW_STOCK&category=Filters',
            reverse('part_detail', args=[self.part.id]), reverse('edit_inventory_item', args=[self.part.id]),
            reverse('client_pricelist'), reverse('client_list'), reverse('research_hub'),
            reverse('global_search') + '?q=oil', reverse('supplier_list'), reverse('supplier_detail', args=[self.supplier.id]),
            reverse('po_list'), reverse('po_detail', args=[self.po.id]),
            reverse('finance:dashboard'), reverse('finance:create_invoice'),
            reverse('finance:invoice_detail', args=[self.invoice.id]), reverse('finance:client_ledger', args=[self.customer.id]),
            reverse('finance:bulk_import'), reverse('finance:pricelist_dashboard'), reverse('finance:price_history'),
        ]
        for url in pages:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_order_and_invoice_link_to_each_other(self):
        self.assertContains(self.client.get(reverse('order_detail', args=[self.order.id])), 'INV-1001')
        self.assertContains(self.client.get(reverse('finance:invoice_detail', args=[self.invoice.id])), 'ORD-1001')

    def test_part_page_connects_orders_suppliers_and_prices(self):
        response = self.client.get(reverse('part_detail', args=[self.part.id]))
        for text in ('ORD-1001', 'M/V Aegean Star', 'Jabsco Hellas', 'PO-1'):
            self.assertContains(response, text)

    def test_auto_categorise_only_runs_on_post(self):
        self.client.get(reverse('auto_categorise'))
        self.part.refresh_from_db()
        self.assertEqual(self.part.category, 'General')
        self.client.post(reverse('auto_categorise'))
        self.part.refresh_from_db()
        self.assertEqual(self.part.category, 'Filters')

    def test_price_history_form_saves(self):
        from finance.models import PriceRecord
        self.client.post(reverse('finance:price_history'), {
            'part_name': 'Impeller', 'supplier_name': 'M/V Aegean Star', 'unit_price': '45,50', 'date_recorded': '2026-10-01',
        })
        record = PriceRecord.objects.get(part_name='Impeller')
        self.assertEqual(record.unit_price, Decimal('45.50'))
        self.assertEqual(record.customer, self.customer)

    def test_drive_links_attach_to_matching_invoice(self):
        self.client.post(reverse('finance:bulk_import'), {'raw_data': 'INV-1001 https://drive.google.com/file/d/abc/view\nnothing here'})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.google_drive_url, 'https://drive.google.com/file/d/abc/view')

    def test_healthz_is_public_and_skips_login(self):
        self.client.logout()
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')


class LanguageTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user('tester', password='pw-for-tests-123')
        self.client.login(username='tester', password='pw-for-tests-123')

    def test_greek_is_default_and_english_switch_works(self):
        self.assertContains(self.client.get(reverse('hub')), 'Πίνακας ελέγχου')
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        self.assertContains(self.client.get(reverse('hub')), 'Dashboard')

    def test_greek_money_format(self):
        from tracker.templatetags.ui import money
        from django.utils import translation
        with translation.override('el'):
            self.assertEqual(money(Decimal('1234.5')), '1.234,50 €')
        with translation.override('en'):
            self.assertEqual(money(Decimal('1234.5')), '1,234.50 €')


class StockHistoryRolesAndToolsTests(TestCase):
    def setUp(self):
        cache.clear()
        from django.contrib.auth.models import Group
        self.admin = User.objects.create_superuser('boss', password='pw-for-tests-123')
        self.client.login(username='boss', password='pw-for-tests-123')
        self.part = InventoryItem.objects.create(part_name='Impeller', part_code='IMP-1', quantity=10, location='Bin A1')

    def test_creating_order_invoice_and_client_settings_work(self):
        from finance.models import Invoice
        r = self.client.post(reverse('create_order'), {'customer_name': 'M/V Test', 'inventory_id': self.part.id, 'quantity': 2})
        self.assertEqual(r.status_code, 302)
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity, 8)
        move = self.part.movements.first()
        self.assertEqual((move.change, move.reason, move.user), (-2, 'SALE', self.admin))
        r = self.client.post(reverse('finance:create_invoice'), {'customer_name': 'M/V Test'})
        self.assertEqual(r.status_code, 302)
        client = Customer.objects.get(name='M/V Test')
        r = self.client.post(reverse('finance:client_ledger', args=[client.id]), {'update_profile': '1', 'internal_rating': 'A', 'payment_terms_days': '45'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Invoice.objects.filter(customer=client).count() == 2)

    def test_manual_adjust_and_scan_count_are_logged(self):
        self.client.post(reverse('adjust_stock', args=[self.part.id, 'increase']))
        self.client.post(reverse('scan_part', args=[self.part.id]), {'action': 'count', 'counted': '7'})
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity, 7)
        reasons = list(self.part.movements.values_list('reason', 'change'))
        self.assertEqual(reasons, [('COUNT', -4), ('ADJUST', 1)])

    def test_shelf_count_records_differences(self):
        other = InventoryItem.objects.create(part_name='Anode', quantity=3, location='Bin A1')
        self.client.post(reverse('stock_count'), {'location': 'Bin A1', f'count_{self.part.id}': '10', f'count_{other.id}': '5'})
        other.refresh_from_db()
        self.assertEqual(other.quantity, 5)
        self.assertEqual(self.part.movements.get().change, 0)  # counted, no difference, still logged

    def test_purchase_order_receive_is_logged(self):
        from tracker.models import Supplier, PurchaseOrder, PurchaseOrderItem
        po = PurchaseOrder.objects.create(po_number='PO-9', supplier=Supplier.objects.create(name='S'))
        PurchaseOrderItem.objects.create(purchase_order=po, inventory_item=self.part, quantity=5, unit_cost=Decimal('3'))
        self.client.post(reverse('po_detail', args=[po.id]), {'receive_po': '1'})
        self.assertEqual(self.part.movements.first().reason, 'PURCHASE')
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity, 15)

    def test_tool_pages_render(self):
        for url in [reverse('print_labels'), reverse('print_labels') + '?kind=shelves', reverse('stock_count') + '?location=Bin+A1',
                    reverse('dead_stock'), reverse('scan_part', args=[self.part.id]), reverse('team'), reverse('activity'),
                    reverse('activity') + '?tab=stock', reverse('password_change'), reverse('part_detail', args=[self.part.id])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(reverse('print_labels')), '<svg')

    def test_team_page_creates_member_with_role(self):
        from tracker.roles import user_role
        self.client.post(reverse('team'), {'action': 'create', 'username': 'nikos', 'first_name': 'Nikos', 'role': 'Technician',
                                           'password': 'Sea-Battery-4471', 'password2': 'Sea-Battery-4471'})
        self.assertEqual(user_role(User.objects.get(username='nikos')), 'Technician')

    def test_technician_cannot_open_money_pages(self):
        from tracker.roles import set_role
        tech = User.objects.create_user('tech', password='pw-for-tests-123')
        set_role(tech, 'Technician')
        self.client.logout()
        self.client.login(username='tech', password='pw-for-tests-123')
        for url in ('/finance/', '/clients/', '/purchasing/', '/team/', '/activity/'):
            self.assertRedirects(self.client.get(url), reverse('app_hub'), fetch_redirect_response=False, msg_prefix=url)
        self.assertEqual(self.client.get(reverse('inventory_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('scan_part', args=[self.part.id])).status_code, 200)

    def test_office_cannot_open_team_page(self):
        User.objects.create_user('office', password='pw-for-tests-123')
        self.client.logout()
        self.client.login(username='office', password='pw-for-tests-123')
        self.assertEqual(self.client.get('/team/').status_code, 302)
        self.assertEqual(self.client.get('/finance/').status_code, 200)
