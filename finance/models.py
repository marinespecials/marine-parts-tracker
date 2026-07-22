from django.db import models
from django.utils import timezone
from tracker.models import Customer

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'DRAFT / INVOICE'),
        ('ORDER', 'ORDER (Παραγγελία)'),
        ('DELIVERY', 'DELIVERY NOTE (Δελτίο Αποστολής)'),
        ('PAID', 'PAID'),
        ('VOID', 'VOID'),
    ]
    invoice_number = models.CharField(max_length=100)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    google_drive_url = models.URLField(max_length=500, blank=True, null=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"

class ClientFinancialProfile(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)
    lifetime_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    negotiation_notes = models.TextField(blank=True, null=True)
    payment_terms_days = models.IntegerField(default=30)
    internal_rating = models.CharField(max_length=5, default='B')

    def __str__(self):
        return f"Profile: {self.customer.name}"

class PriceRecord(models.Model):
    part_name = models.CharField(max_length=255)
    part_code = models.CharField(max_length=100, blank=True, null=True)
    supplier_or_client_name = models.CharField(max_length=255)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')
    date_recorded = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date_recorded']

    def __str__(self):
        return f"{self.part_name} - {self.unit_price} {self.currency} ({self.supplier_or_client_name})"