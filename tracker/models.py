import re
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# One category list shared by the warehouse, the client catalog and the master price list.
PART_CATEGORIES = [
    ('General', _('General Hardware')),
    ('Engine Spares', _('Engine Spares')),
    ('Filters', _('Filters & Separators')),
    ('Pumps', _('Pumps & Impellers')),
    ('Valves', _('Valves & Plumbing')),
    ('Hoses & Fittings', _('Hoses & Fittings')),
    ('Seals & Bearings', _('Seals & Bearings')),
    ('Electrical', _('Electrical & Batteries')),
    ('Anodes', _('Anodes & Corrosion')),
    ('Lubricants', _('Oils & Lubricants')),
    ('Safety', _('Safety Equipment')),
]

# Keyword rules used to suggest a category from a part's name/code (English + Greek).
# Order matters: the first matching rule wins ("oil filter" is a Filter, not a Lubricant).
CATEGORY_KEYWORDS = [
    ('Filters', ['filter', 'φίλτρ', 'φιλτρ', 'separator', 'racor', 'strainer']),
    ('Pumps', ['pump', 'impeller', 'αντλ', 'φτερωτ']),
    ('Anodes', ['anode', 'zinc', 'ψευδαργ', 'ανόδι', 'ανοδι']),
    ('Seals & Bearings', ['seal', 'o-ring', 'oring', 'o ring', 'bearing', 'τσιμουχ', 'τσιμούχ', 'ρουλεμ', 'φλάντζ', 'φλαντζ', 'gasket', 'packing']),
    ('Valves', ['valve', 'βαλβ', 'βάνα', 'βανα', 'ball cock', 'seacock', 'check valve']),
    ('Hoses & Fittings', ['hose', 'fitting', 'clamp', 'σωλ', 'coupling', 'elbow', 'nipple', 'adapter', 'connector', 'σφιγκτ']),
    ('Electrical', ['battery', 'μπαταρ', 'cable', 'καλώδ', 'καλωδ', 'fuse', 'relay', 'switch', 'alternator', 'δυναμ',
                    'starter', 'μίζα', 'μιζα', 'charger', 'inverter', 'led', 'lamp', 'bulb', 'λάμπ', 'λαμπ', 'breaker',
                    'wire', 'sensor', 'αισθητ', 'solenoid', 'victron', 'volt', 'amper']),
    ('Engine Spares', ['piston', 'injector', 'μπεκ', 'belt', 'ιμάντ', 'ιμαντ', 'thermostat', 'θερμοστ', 'turbo',
                       'liner', 'cylinder', 'κύλινδ', 'κυλινδ', 'crank', 'camshaft', 'glow plug', 'spark plug',
                       'μπουζ', 'rocker', 'exhaust', 'εξατμ', 'heat exchanger', 'yanmar', 'volvo', 'mtu', 'caterpillar', 'cummins']),
    ('Lubricants', ['oil', 'λάδι', 'λαδι', 'grease', 'γράσ', 'γρασ', 'lubric', 'coolant', 'antifreeze', 'αντιψυκτ']),
    ('Safety', ['life jacket', 'lifejacket', 'σωσίβ', 'σωσιβ', 'flare', 'extinguisher', 'πυροσβεστ', 'epirb', 'buoy',
                'raft', 'σχεδί', 'first aid', 'harness']),
]


def _keyword_pattern(word):
    # Latin keywords must start a word ("led" matches "LED lamp", not "sealed");
    # Greek keywords are stems, so they may appear anywhere.
    return re.compile((r'\b' if word.isascii() else '') + re.escape(word))


_CATEGORY_PATTERNS = [(cat, [_keyword_pattern(w) for w in words]) for cat, words in CATEGORY_KEYWORDS]


def guess_category(*texts):
    """Suggest a category from part name / code. Returns 'General' when nothing matches."""
    haystack = ' '.join(t for t in texts if t).lower()
    for category, patterns in _CATEGORY_PATTERNS:
        if any(p.search(haystack) for p in patterns):
            return category
    return 'General'


class Customer(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    CATEGORY_CHOICES = PART_CATEGORIES
    part_name = models.CharField(max_length=255)
    part_code = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='General')
    quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=5)
    location = models.CharField(max_length=100, default='Piraeus Warehouse')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    supplier = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def total_stock_value(self):
        return self.quantity * Decimal(str(self.unit_cost))

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level

    def __str__(self):
        return f"{self.part_name} ({self.location})"


class OrderItem(models.Model):
    """Line items attached to an Order, pulling from Master Inventory."""
    order = models.ForeignKey('finance.Invoice', on_delete=models.CASCADE, related_name='order_items')
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255, help_text="Part name if not from inventory")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_packed = models.BooleanField(default=False)

    @property
    def total_price(self):
        return self.quantity * Decimal(str(self.unit_price))

    def __str__(self):
        return f"{self.quantity}x {self.description} for {self.order.invoice_number}"
from django.utils import timezone

class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.name

class PurchaseOrder(models.Model):
    po_number = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    issue_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, default='DRAFT')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return self.po_number

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, related_name='items', on_delete=models.CASCADE)
    inventory_item = models.ForeignKey('InventoryItem', on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total_cost(self):
        return self.quantity * Decimal(str(self.unit_cost))