import random
import qrcode
import pdfplumber
from io import BytesIO
from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Sum, Avg
from django.core.management import call_command
from django.http import HttpResponse

from tracker.models import Customer
from .models import Invoice, ClientFinancialProfile, PriceRecord

def finance_dashboard(request):
    invoices = Invoice.objects.all().order_by('-issue_date')
    recent_prices = PriceRecord.objects.all().order_by('-date_recorded')[:10]
    
    total_invoices = invoices.count()
    
    top_suppliers = Invoice.objects.values('customer__name').annotate(count=Count('id')).order_by('-count')[:5]
    top_supplier_name = top_suppliers[0]['customer__name'] if top_suppliers else "N/A"
    
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
        
        # 1. SAVE THE FILE TO THE DATABASE FIRST
        matched_customer, _ = Customer.objects.get_or_create(name="Unknown OCR Client")
        draft_due_date = timezone.now().date() + timedelta(days=30)
        
        new_invoice = Invoice.objects.create(
            invoice_number=f"INV-{random.randint(1000, 9999)}",
            customer=matched_customer,
            total_amount=0.00,
            status='DRAFT',
            due_date=draft_due_date,
            ocr_document=uploaded_file # File is safely written to disk here
        )
        
        # 2. READ THE PHYSICAL FILE FROM THE DISK
        extracted_text = ""
        try:
            with pdfplumber.open(new_invoice.ocr_document.path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += page_text + "\n"
        except Exception as e:
            extracted_text = "OCR Failed or Image-Only PDF"

        request.session['last_ocr_text'] = extracted_text
        
        # 3. UPDATE MATCHED CLIENT BASED ON TEXT
        all_customers = Customer.objects.all()
        for client in all_customers:
            if client.name.lower() in extracted_text.lower():
                new_invoice.customer = client
                new_invoice.save()
                break

        # 4. GENERATE QR CODE
        tracking_url = f"https://marine-specials-tracker.onrender.com/admin/finance/invoice/{new_invoice.id}/change/"
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(tracking_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0A2540", back_color="white")
        
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        new_invoice.qr_code.save(f"QR_{new_invoice.invoice_number}.png", ContentFile(buffer.getvalue()), save=True)

        return redirect('finance:ocr_review', invoice_id=new_invoice.id)
        
    return render(request, 'finance/upload_ocr.html')


def ocr_review(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    customers = Customer.objects.all()
    
    if request.method == 'POST':
        # Handled by the global delete function now
        if 'delete_invoice' in request.POST:
            return redirect('finance:delete_invoice', invoice_id=invoice.id)
        
        invoice.invoice_number = request.POST.get('invoice_number')
        customer_id = request.POST.get('customer_id')
        invoice.customer = get_object_or_404(Customer, id=customer_id)
        invoice.total_amount = request.POST.get('total_amount')
        invoice.status = request.POST.get('status')
        invoice.save()
        
        if 'last_ocr_text' in request.session:
            del request.session['last_ocr_text']
            
        return redirect('finance:dashboard')

    extracted_text = request.session.get('last_ocr_text', 'No text extracted. The engine might need an image-based OCR fallback.')
    
    context = {
        'invoice': invoice,
        'customers': customers,
        'extracted_text': extracted_text
    }
    return render(request, 'finance/ocr_review.html', context)


# ==========================================
# 🗑️ GLOBAL DELETE ROUTE
# ==========================================
def delete_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        if invoice.ocr_document:
            invoice.ocr_document.delete(save=False) # Delete physical PDF
        if invoice.qr_code:
            invoice.qr_code.delete(save=False)      # Delete physical QR
        invoice.delete()                            # Delete from DB
    
    # Send user back to wherever they clicked the delete button from
    return redirect(request.META.get('HTTP_REFERER', 'finance:dashboard'))


# ==========================================
# 📊 SAP-STYLE CLIENT LEDGER (UPGRADED)
# ==========================================
def client_ledger(request, client_id):
    client = get_object_or_404(Customer, id=client_id)
    profile, created = ClientFinancialProfile.objects.get_or_create(customer=client)
    
    client_invoices = Invoice.objects.filter(customer=client).order_by('-issue_date')
    total_revenue = sum(inv.total_amount for inv in client_invoices if inv.status != 'VOID')
    
    if profile.lifetime_revenue != total_revenue:
        profile.lifetime_revenue = total_revenue
        profile.save()

    # 1. New: Yearly Statistics
    yearly_data = client_invoices.values('issue_date__year').annotate(
        total=Sum('total_amount'),
        count=Count('id')
    ).order_by('-issue_date__year')

    # 2. Existing: Most Bought Parts
    price_history = PriceRecord.objects.filter(supplier_or_client_name__icontains=client.name).order_by('-date_recorded')
    top_parts = price_history.values('part_name', 'currency').annotate(
        purchase_count=Count('id'),
        avg_price=Avg('unit_price')
    ).order_by('-purchase_count')[:10]

    context = {
        'client': client,
        'profile': profile,
        'invoices': client_invoices,
        'price_history': price_history,
        'top_parts': top_parts,
        'yearly_data': yearly_data,
    }
    return render(request, 'finance/client_ledger.html', context)


def update_cloud_db(request):
    try:
        call_command('migrate')
        return HttpResponse("✅ Cloud Database Successfully Updated!")
    except Exception as e:
        return HttpResponse(f"❌ Error updating database: {e}")

import csv
from django.http import HttpResponse

# ==========================================
# 📥 MONTH-END FINANCIAL EXPORT
# ==========================================
def export_finances_csv(request):
    # Create the HTTP response with the correct CSV headers
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="marine_finance_export.csv"'
    
    writer = csv.writer(response)
    
    # Write the spreadsheet header row
    writer.writerow(['Invoice Number', 'Client Name', 'Issue Date', 'Due Date', 'Status', 'Total Amount (EUR)'])
    
    # Write data rows
    invoices = Invoice.objects.all().order_by('-issue_date')
    for inv in invoices:
        writer.writerow([
            inv.invoice_number,
            inv.customer.name,
            inv.issue_date,
            inv.due_date,
            inv.status,
            inv.total_amount
        ])
        
    return response
# ==========================================
# 🏢 SAP ENTERPRISE LEDGER HOME
# ==========================================
def sap_overview(request):
    profiles = ClientFinancialProfile.objects.select_related('customer').all()
    total_enterprise_revenue = sum(p.lifetime_revenue for p in profiles)
    
    context = {
        'profiles': profiles,
        'total_enterprise_revenue': total_enterprise_revenue,
    }
    return render(request, 'finance/sap_overview.html', context)