from django.db import models
from django.utils import timezone

class Customer(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    CATEGORY_CHOICES = [
        ('General', 'General'),
        ('Electrical', 'Electrical'),
        ('Filters', 'Filters'),
        ('Pumps', 'Pumps'),
        ('Valves', 'Valves'),
    ]
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
        return self.quantity * float(self.unit_cost)

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
        return self.quantity * float(self.unit_price)

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
        return float(self.quantity) * float(self.unit_cost)