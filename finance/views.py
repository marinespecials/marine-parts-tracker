import random
import qrcode
import csv
import re
from io import BytesIO
from datetime import timedelta, datetime

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


def create_invoice(request):
    customers = Customer.objects.all()
    if request.method == 'POST':
        invoice_number = request.POST.get('invoice_number', f"INV-{random.randint(1000, 9999)}")
        customer_id = request.POST.get('customer_id')
        total_amount = request.POST.get('total_amount', '0.00')
        due_date = request.POST.get('due_date') or (timezone.now().date() + timedelta(days=30))
        status = request.POST.get('status', 'DRAFT')
        google_drive_url = request.POST.get('google_drive_url', '').strip()
        
        customer = get_object_or_404(Customer, id=customer_id)
        
        new_invoice = Invoice.objects.create(
            invoice_number=invoice_number,
            customer=customer,
            total_amount=total_amount,
            due_date=due_date,
            status=status,
            google_drive_url=google_drive_url
        )
        
        tracking_url = f"https://marine-specials-tracker.onrender.com/admin/finance/invoice/{new_invoice.id}/change/"
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(tracking_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0A2540", back_color="white")
        
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        new_invoice.qr_code.save(f"QR_{new_invoice.invoice_number}.png", ContentFile(buffer.getvalue()), save=True)
        
        return redirect('finance:dashboard')
        
    context = {
        'customers': customers,
        'action_title': 'Add New Invoice & Link Drive'
    }
    return render(request, 'finance/invoice_form.html', context)


def bulk_import_links(request):
    customers = Customer.objects.all()
    message = None
    
    if request.method == 'POST':
        raw_data = request.POST.get('raw_data', '')
        imported_count = 0
        lines = raw_data.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 1. Extract Google Drive URL using regex
            url_match = re.search(r'https?://[^\s]+', line)
            drive_url = url_match.group(0) if url_match else ''
            
            # Remove URL from the line to analyze the filename/metadata text
            text_content = line.replace(drive_url, '').strip()
            
            # 2. Extract Invoice Number
            inv_match = re.search(r'(INV[-_\s]?\d+|\b[A-Z0-9]{4,10}\b)', text_content, re.IGNORECASE)
            inv_num = inv_match.group(0).replace(' ', '-').upper() if inv_match else f"INV-{random.randint(1000, 9999)}"
            
            # 3. Extract Date
            date_match = re.search(r'\b(20\d{2}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]20\d{2})\b', text_content)
            issue_date = timezone.now().date()
            if date_match:
                date_str = date_match.group(0).replace('/', '-')
                try:
                    if date_str.startswith('20'):
                        issue_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    else:
                        issue_date = datetime.strptime(date_str, '%d-%m-%Y').date()
                except ValueError:
                    pass
            
            # 4. Extract Amount
            amount_match = re.search(r'\b\d+[\.,]\d{2}\b', text_content)
            total_amount = 0.00
            if amount_match:
                try:
                    clean_amt = amount_match.group(0).replace(',', '.')
                    total_amount = float(clean_amt)
                except ValueError:
                    pass
            
            # 5. Extract Client Name
            cleaned_name = text_content
            if inv_match:
                cleaned_name = cleaned_name.replace(inv_match.group(0), '')
            if date_match:
                cleaned_name = cleaned_name.replace(date_match.group(0), '')
            if amount_match:
                cleaned_name = cleaned_name.replace(amount_match.group(0), '')
            
            cleaned_name = re.sub(r'[\._-]+', ' ', cleaned_name)
            cleaned_name = re.sub(r'\b(pdf|jpg|png|invoice|inv)\b', '', cleaned_name, flags=re.IGNORECASE)
            client_name = cleaned_name.strip()
            
            if not client_name or len(client_name) < 2:
                client_name = "General Marine Client"
            else:
                client_name = client_name.title()
            
            customer, _ = Customer.objects.get_or_create(name=client_name)
            
            invoice, created = Invoice.objects.get_or_create(
                invoice_number=inv_num,
                defaults={
                    'customer': customer,
                    'total_amount': total_amount,
                    'issue_date': issue_date,
                    'due_date': issue_date + timedelta(days=30),
                    'status': 'DRAFT',
                    'google_drive_url': drive_url
                }
            )
            if not created:
                invoice.customer = customer
                invoice.total_amount = total_amount
                invoice.issue_date = issue_date
                invoice.google_drive_url = drive_url
                invoice.save()
                
            imported_count += 1
                
        message = f"Successfully auto-extracted and imported {imported_count} invoices with smart file text parsing!"

    context = {
        'customers': customers,
        'message': message
    }
    return render(request, 'finance/bulk_import.html', context)


def edit_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    customers = Customer.objects.all()
    
    if request.method == 'POST':
        if 'delete_invoice' in request.POST:
            return redirect('finance:delete_invoice', invoice_id=invoice.id)
        
        invoice.invoice_number = request.POST.get('invoice_number')
        customer_id = request.POST.get('customer_id')
        invoice.customer = get_object_or_404(Customer, id=customer_id)
        invoice.total_amount = request.POST.get('total_amount')
        invoice.due_date = request.POST.get('due_date')
        invoice.status = request.POST.get('status')
        invoice.google_drive_url = request.POST.get('google_drive_url', '').strip()
        invoice.save()
        
        return redirect('finance:dashboard')
        
    context = {
        'invoice': invoice,
        'customers': customers,
        'action_title': 'Edit Invoice & Drive Link'
    }
    return render(request, 'finance/invoice_form.html', context)


def delete_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        if invoice.qr_code:
            invoice.qr_code.delete(save=False)
        invoice.delete()
    
    return redirect(request.META.get('HTTP_REFERER', 'finance:dashboard'))


def client_ledger(request, client_id):
    client = get_object_or_404(Customer, id=client_id)
    profile, created = ClientFinancialProfile.objects.get_or_create(customer=client)
    
    if request.method == 'POST' and 'update_profile' in request.POST:
        profile.negotiation_notes = request.POST.get('negotiation_notes', '')
        profile.payment_terms_days = request.POST.get('payment_terms_days', 30)
        profile.internal_rating = request.POST.get('internal_rating', 'B')
        profile.save()
        return redirect('finance:client_ledger', client_id=client.id)

    client_invoices = Invoice.objects.filter(customer=client).order_by('-issue_date')
    total_revenue = sum(inv.total_amount for inv in client_invoices if inv.status != 'VOID')
    
    if profile.lifetime_revenue != total_revenue:
        profile.lifetime_revenue = total_revenue
        profile.save()

    yearly_data = client_invoices.values('issue_date__year').annotate(
        total=Sum('total_amount'),
        count=Count('id')
    ).order_by('-issue_date__year')

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


def export_finances_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="marine_finance_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Invoice Number', 'Client Name', 'Issue Date', 'Due Date', 'Status', 'Total Amount (EUR)', 'Google Drive URL'])
    
    invoices = Invoice.objects.all().order_by('-issue_date')
    for inv in invoices:
        writer.writerow([
            inv.invoice_number,
            inv.customer.name,
            inv.issue_date,
            inv.due_date,
            inv.status,
            inv.total_amount,
            inv.google_drive_url or ''
        ])
        
    return response


def update_cloud_db(request):
    try:
        call_command('migrate')
        return HttpResponse("✅ Cloud Database Successfully Updated!")
    except Exception as e:
        return HttpResponse(f"❌ Error updating database: {e}")