import random
import qrcode
import csv
import re
import requests
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
        
        urls = re.findall(r'https?://[^\s,\"\']+', raw_data)
        
        GENERIC_KEYWORDS = [
            'invoice', 'invoices', 'τιμολογιο', 'τιμολογια',
            'παραγγελια', 'παραγγελιες', 'order', 'orders', 'po',
            'δελτιο', 'δελτια', 'αποστολης', 'delivery', 'packing',
            'pdf', 'doc', 'docx', 'jpg', 'png'
        ]
        
        for drive_url in urls:
            drive_url = drive_url.rstrip(',.')
            if not drive_url:
                continue
            
            text_content = ""
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(drive_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    title_match = re.search(r'<title>(.*?)</title>', resp.text, re.IGNORECASE)
                    if title_match:
                        page_title = title_match.group(1)
                        # Strip ALL Google Drive suffixes
                        page_title = re.sub(r'\s*-\s*Google.*$', '', page_title, flags=re.IGNORECASE).strip()
                        text_content = page_title
            except Exception as e:
                print(f"Could not auto-fetch drive title for {drive_url}: {e}")
            
            if not text_content:
                text_content = f"General-Marine-Client_INV-{random.randint(1000, 9999)}_{timezone.now().strftime('%Y-%m-%d')}.pdf"
            
            base_name = re.sub(r'\.[a-zA-Z0-9]+$', '', text_content).strip()
            
            # 1. Extract Date (Matches 29-01-2026, 7-4-2026, 28-01-2026, etc.)
            date_match = re.search(r'(\b\d{1,4}[-_\/]\d{1,2}[-_\/]\d{2,4}\b)', base_name)
            issue_date = timezone.now().date()
            
            if date_match:
                date_str = date_match.group(1)
                clean_date = date_str.replace('_', '-').replace('/', '-')
                d_parts = clean_date.split('-')
                
                if len(d_parts) == 3:
                    try:
                        p1, p2, p3 = int(d_parts[0]), int(d_parts[1]), int(d_parts[2])
                        if p1 > 1000:  # YYYY-MM-DD
                            year, month, day = p1, p2, p3
                        elif p3 > 1000:  # DD-MM-YYYY
                            day, month, year = p1, p2, p3
                        else:  # DD-MM-YY
                            day, month, year = p1, p2, 2000 + p3
                        
                        issue_date = datetime(year, month, day).date()
                    except (ValueError, TypeError):
                        pass
                
                base_name = base_name.replace(date_str, '').strip(' _-')

            # 2. Extract Document Category / Status
            doc_status = 'DRAFT'
            if re.search(r'\b(παραγγελια|order|po)\b', text_content, re.IGNORECASE):
                doc_status = 'ORDER'
            elif re.search(r'\b(δελτιο|delivery|packing)\b', text_content, re.IGNORECASE):
                doc_status = 'DELIVERY'
            
            # 3. Separate Supplier & Invoice Number
            words = [w.strip(' _-#') for w in re.split(r'[\s_]+', base_name) if w.strip(' _-#')]
            
            supplier_words = []
            inv_words = []
            
            for w in words:
                if w.lower() in GENERIC_KEYWORDS:
                    continue
                if any(c.isdigit() for c in w) or re.match(r'^(#|inv|τδα|δα|ρο)', w, re.IGNORECASE):
                    inv_words.append(w)
                else:
                    supplier_words.append(w)
            
            supplier = " ".join(supplier_words).title() if supplier_words else "General Marine Client"
            inv_num = "-".join(inv_words) if inv_words else (base_name if base_name else f"INV-{random.randint(1000, 9999)}")

            customer, _ = Customer.objects.get_or_create(name=supplier)
            
            invoice, created = Invoice.objects.get_or_create(
                invoice_number=inv_num,
                defaults={
                    'customer': customer,
                    'total_amount': 0.00,
                    'issue_date': issue_date,
                    'due_date': issue_date + timedelta(days=30),
                    'status': doc_status,
                    'google_drive_url': drive_url
                }
            )
            
            # Force update issue_date and customer directly in database table
            invoice.customer = customer
            invoice.status = doc_status
            invoice.google_drive_url = drive_url
            invoice.due_date = issue_date + timedelta(days=30)
            invoice.save()
            Invoice.objects.filter(id=invoice.id).update(issue_date=issue_date)
                
            imported_count += 1
                
        message = f"Successfully imported {imported_count} files with exact extracted dates and clean supplier names!"

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