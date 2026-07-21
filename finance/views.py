import random
import qrcode
import pdfplumber
from io import BytesIO
from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from django.core.management import call_command
from django.http import HttpResponse

from tracker.models import Customer
from .models import Invoice, ClientFinancialProfile, PriceRecord

def finance_dashboard(request):
    invoices = Invoice.objects.all().order_by('-issue_date')
    recent_prices = PriceRecord.objects.all().order_by('-date_recorded')[:10]
    
    # 1. Calculate KPI Metrics
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


def upload_ocr(request):
    if request.method == 'POST' and request.FILES.get('invoice_file'):
        uploaded_file = request.FILES['invoice_file']
        
        # ==========================================
        # ⚙️ UPGRADED ENGINE: PDFPLUMBER
        # ==========================================
        extracted_text = ""
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    extracted_text += page.extract_text() + "\n"
        except Exception as e:
            extracted_text = "OCR Failed or Image-Only PDF"

        # Fallback dummy data if extraction fails
        extracted_invoice_number = f"INV-{random.randint(1000, 9999)}"
        extracted_total = 0.00
        
        # NATIVE CLIENT DATABASE MATCHING
        matched_customer = None
        all_customers = Customer.objects.all()
        for client in all_customers:
            if client.name.lower() in extracted_text.lower():
                matched_customer = client
                break
        
        if not matched_customer:
            matched_customer, _ = Customer.objects.get_or_create(name="Unknown OCR Client")

        # CREATE THE DRAFT INVOICE
        draft_due_date = timezone.now().date() + timedelta(days=30)
        
        new_invoice = Invoice.objects.create(
            invoice_number=extracted_invoice_number,
            customer=matched_customer,
            total_amount=extracted_total,
            status='DRAFT',
            due_date=draft_due_date,
            ocr_document=uploaded_file
        )

        # GENERATE QR CODE
        tracking_url = f"https://marine-specials-tracker.onrender.com/admin/finance/invoice/{new_invoice.id}/change/"
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(tracking_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0A2540", back_color="white")
        
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        new_invoice.qr_code.save(f"QR_{new_invoice.invoice_number}.png", ContentFile(buffer.getvalue()), save=True)

        # REDIRECT TO THE REVIEW SCREEN INSTEAD OF DASHBOARD
        return redirect('finance:ocr_review', invoice_id=new_invoice.id)
        
    return render(request, 'finance/upload_ocr.html')


# ==========================================
# 🔍 HUMAN-IN-THE-LOOP REVIEW SCREEN
# ==========================================
def ocr_review(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    customers = Customer.objects.all()
    
    if request.method == 'POST':
        # Get the corrected data from the user
        invoice.invoice_number = request.POST.get('invoice_number')
        customer_id = request.POST.get('customer_id')
        invoice.customer = get_object_or_404(Customer, id=customer_id)
        invoice.total_amount = request.POST.get('total_amount')
        invoice.status = request.POST.get('status')
        
        # Save the finalized invoice
        invoice.save()
        return redirect('finance:dashboard')

    context = {
        'invoice': invoice,
        'customers': customers,
    }
    return render(request, 'finance/ocr_review.html', context)


# --- TEMPORARY DATABASE UPDATER ---
def update_cloud_db(request):
    try:
        call_command('migrate')
        return HttpResponse("✅ Cloud Database Successfully Updated! You can now upload OCR PDFs.")
    except Exception as e:
        return HttpResponse(f"❌ Error updating database: {e}")