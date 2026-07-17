from django.shortcuts import render
from .models import Invoice, ClientFinancialProfile, PriceRecord

def finance_dashboard(request):
    # Fetch all data to display on the dashboard
    invoices = Invoice.objects.all().order_by('-issue_date')
    profiles = ClientFinancialProfile.objects.all()
    # Get the 10 most recent price records
    recent_prices = PriceRecord.objects.all().order_by('-date_recorded')[:10]
    
    context = {
        'invoices': invoices,
        'profiles': profiles,
        'recent_prices': recent_prices,
    }
    return render(request, 'finance/finance_dashboard.html', context)

import random
from django.shortcuts import render, redirect
from tracker.models import Customer
from .models import Invoice, ClientFinancialProfile, PriceRecord

# ... (Keep your existing finance_dashboard function at the top) ...

import random
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect
from tracker.models import Customer
from .models import Invoice, ClientFinancialProfile, PriceRecord

# ... (Keep your existing finance_dashboard function at the top) ...

def upload_ocr(request):
    if request.method == 'POST' and request.FILES.get('invoice_file'):
        uploaded_file = request.FILES['invoice_file']
        
        # ==========================================
        # ⚙️ YOUR OCR ENGINE GOES HERE
        # ==========================================
        extracted_invoice_number = f"INV-{random.randint(1000, 9999)}"
        extracted_client_name = "Automated OCR Client"
        extracted_total = 1250.00
        
        # Calculate a due date (30 days from today)
        draft_due_date = timezone.now().date() + timedelta(days=30)
        
        # 1. Find or create the customer based on extracted text
        customer, created = Customer.objects.get_or_create(name=extracted_client_name)
        
        # 2. Automatically generate the Draft Invoice in the database
        Invoice.objects.create(
            invoice_number=extracted_invoice_number,
            customer=customer,
            total_amount=extracted_total,
            status='DRAFT',
            due_date=draft_due_date  # <-- THIS FIXES THE CRASH!
        )
        
        # Send them back to the dashboard to see the new invoice
        return redirect('finance:dashboard')
        
    return render(request, 'finance/upload_ocr.html')