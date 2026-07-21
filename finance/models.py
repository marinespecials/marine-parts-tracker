from django.db import models
from tracker.models import Customer

class Invoice(models.Model):
    invoice_number = models.CharField(max_length=100, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PAID', 'Paid'),
        ('VOID', 'Void'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    
    # Primary Cloud Document Link
    google_drive_url = models.URLField(
        max_length=500, 
        blank=True, 
        null=True, 
        help_text="Google Drive shareable link for this invoice"
    )

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"

class ClientFinancialProfile(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='financial_profile')
    lifetime_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    RATING_CHOICES = [
        ('A', 'A - Excellent'),
        ('B', 'B - Good'),
        ('C', 'C - Risky'),
    ]
    internal_rating = models.CharField(max_length=5, choices=RATING_CHOICES, default='B')
    payment_terms_days = models.IntegerField(default=30)
    negotiation_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Profile: {self.customer.name}"

class PriceRecord(models.Model):
    date_recorded = models.DateField(auto_now_add=True)
    supplier_or_client_name = models.CharField(max_length=200)
    part_name = models.CharField(max_length=200)
    transaction_type = models.CharField(max_length=50, default='Purchase')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')

    def __str__(self):
        return f"{self.part_name} - {self.unit_price} {self.currency}"