from django.shortcuts import render
from .models import Invoice, ClientFinancialProfile, PriceRecord

from django.shortcuts import render, redirect
from django.db.models import Count
from .models import Invoice, ClientFinancialProfile, PriceRecord

def finance_dashboard(request):
    invoices = Invoice.objects.all().order_by('-issue_date')
    recent_prices = PriceRecord.objects.all().order_by('-date_recorded')[:10]
    
    # 1. Calculate KPI Metrics (Replicating your Tkinter logic)
    total_invoices = invoices.count()
    
    # 2. Get the Top 5 Suppliers by Volume
    top_suppliers = Invoice.objects.values('customer__name').annotate(count=Count('id')).order_by('-count')[:5]
    top_supplier_name = top_suppliers[0]['customer__name'] if top_suppliers else "N/A"
    
    # 3. Prepare data for the JavaScript pie chart
    chart_labels = [supplier['customer__name'] for supplier in top_suppliers]
    chart_data = [supplier['count'] for supplier in top_suppliers]
    
    context = {
        'invoices': invoices,
        'recent_prices': recent_prices,
        'total_invoices': total_invoices,
        'top_supplier': top_supplier_name,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
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

import random
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect
from tracker.models import Customer
from .models import Invoice, ClientFinancialProfile, PriceRecord

def upload_ocr(request):
    if request.method == 'POST' and request.FILES.get('invoice_file'):
        uploaded_file = request.FILES['invoice_file']
        
        # ==========================================
        # 1. YOUR OCR TEXT EXTRACTION
        # (Where your PyTesseract logic will go)
        # ==========================================
        extracted_text = "INVOICE #9982\nTotal: 1250.00\nClient: D.B.S. S.r.l." 
        extracted_invoice_number = f"INV-{random.randint(1000, 9999)}"
        extracted_total = 1250.00
        
        # ==========================================
        # 2. NATIVE CLIENT DATABASE MATCHING
        # ==========================================
        matched_customer = None
        all_customers = Customer.objects.all()
        
        # Loop through your live database and see if the name appears in the OCR text
        for client in all_customers:
            if client.name.lower() in extracted_text.lower():
                matched_customer = client
                break
        
        # Fallback if no match is found
        if not matched_customer:
            matched_customer, _ = Customer.objects.get_or_create(name="Unknown OCR Client")

        # ==========================================
        # 3. CREATE THE INVOICE
        # ==========================================
        draft_due_date = timezone.now().date() + timedelta(days=30)
        
        new_invoice = Invoice.objects.create(
            invoice_number=extracted_invoice_number,
            customer=matched_customer,
            total_amount=extracted_total,
            status='DRAFT',
            due_date=draft_due_date,
            ocr_document=uploaded_file
        )

        # ==========================================
        # 4. NATIVE QR CODE GENERATION
        # ==========================================
        # Creates a URL linking to your live Hub
        tracking_url = f"https://marine-specials-tracker.onrender.com/admin/finance/invoice/{new_invoice.id}/change/"
        
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(tracking_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0A2540", back_color="white")
        
        # Save the QR code directly to the Django database in memory (no external files needed)
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        file_name = f"QR_{new_invoice.invoice_number}.png"
        new_invoice.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=True)

        return redirect('finance:dashboard')
        
    return render(request, 'finance/upload_ocr.html')