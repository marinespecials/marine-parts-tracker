from django.db import models
# Import your existing models from the tracker app
from tracker.models import Customer, Offer, Item

class ClientFinancialProfile(models.Model):
    """
    Extends your existing Customer model with private economic data.
    """
    RATING_CHOICES = [
        ('A', 'Excellent (Prompt Payer)'),
        ('B', 'Good (Standard Terms)'),
        ('C', 'Risky (Late Payer)'),
    ]
    
    # OneToOneField means every Customer gets exactly one Financial Profile
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='finance_profile')
    payment_terms_days = models.IntegerField(default=30, help_text="e.g., Net 30")
    internal_rating = models.CharField(max_length=1, choices=RATING_CHOICES, default='B')
    lifetime_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    negotiation_notes = models.TextField(blank=True, help_text="Private notes for the sales manager")

    def __str__(self):
        return f"{self.customer.name} - Financial Profile"


class Invoice(models.Model):
    """
    Connects a financial bill to a specific physical Order/Offer.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('VOID', 'Voided'),
    ]
    qr_code = models.ImageField(upload_to='invoice_qrs/', null=True, blank=True)

    invoice_number = models.CharField(max_length=50, unique=True)
    # Link the invoice to the customer AND the specific order manifest
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    offer = models.OneToOneField(Offer, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')
    
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    
    # Financials
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # For when you integrate your desktop OCR app later
    ocr_document = models.FileField(upload_to='invoices_pdfs/', null=True, blank=True)

    def __str__(self):
        return f"INV-{self.invoice_number} | {self.customer.name}"


class PriceRecord(models.Model):
    """
    A historical ledger of part prices to build your economic database.
    """
    TRANSACTION_TYPES = [
        ('COST', 'Purchase Cost (From Supplier)'),
        ('SALE', 'Sale Price (To Client)'),
    ]

    # We track by name so you can search "Cylinder Liner" and see all past prices
    part_name = models.CharField(max_length=255)
    
    # Optional links back to the specific item or invoice
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items', null=True, blank=True)
    
    transaction_type = models.CharField(max_length=4, choices=TRANSACTION_TYPES)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    
    supplier_or_client_name = models.CharField(max_length=255)
    date_recorded = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.part_name} - {self.unit_price} {self.currency} ({self.transaction_type})"