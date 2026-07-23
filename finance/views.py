import random
import csv
import re
from datetime import timedelta, datetime

from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Sum, Avg, Q
from django.http import HttpResponse

from tracker.models import Customer
from .models import Invoice, ClientFinancialProfile, PriceRecord, MasterPricelistItem

def finance_dashboard(request):
    status_filter = request.GET.get('status', 'ALL').upper()
    query = request.GET.get('q', '').strip()

    # Fast Order / Invoice Creator
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        invoice_number = request.POST.get('invoice_number', '').strip() or f"ORD-{random.randint(1000, 9999)}"
        total_amount = float(request.POST.get('total_amount') or 0.00)
        issue_date = request.POST.get('issue_date') or timezone.now().date()
        status = request.POST.get('status', 'ORDER')
        google_drive_url = request.POST.get('google_drive_url', '').strip()

        if customer_name:
            customer, _ = Customer.objects.get_or_create(name=customer_name)
            Invoice.objects.create(
                invoice_number=invoice_number,
                customer=customer,
                total_amount=total_amount,
                issue_date=issue_date,
                due_date=issue_date,
                status=status,
                google_drive_url=google_drive_url
            )
        return redirect(f"{request.path}?status={status}")

    invoices = Invoice.objects.all().order_by('-issue_date')

    # Tab Filter
    if status_filter != 'ALL':
        invoices = invoices.filter(status=status_filter)

    # Search Filter
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query) |
            Q(customer__name__icontains=query)
        )

    # Tab Counts
    counts = {
        'ALL': Invoice.objects.count(),
        'ORDER': Invoice.objects.filter(status='ORDER').count(),
        'DRAFT': Invoice.objects.filter(status='DRAFT').count(),
        'DELIVERY': Invoice.objects.filter(status='DELIVERY').count(),
        'PAID': Invoice.objects.filter(status='PAID').count(),
    }

    context = {
        'invoices': invoices,
        'status_filter': status_filter,
        'query': query,
        'counts': counts,
        'customers': Customer.objects.all(),
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
        
        Invoice.objects.create(
            invoice_number=invoice_number,
            customer=customer,
            total_amount=total_amount,
            issue_date=timezone.now().date(),
            due_date=due_date,
            status=status,
            google_drive_url=google_drive_url
        )
        return redirect('finance:dashboard')
        
    context = {
        'customers': customers,
        'action_title': 'Add New Document'
    }
    return render(request, 'finance/invoice_form.html', context)


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
        'action_title': 'Edit Document'
    }
    return render(request, 'finance/invoice_form.html', context)


def delete_invoice(request, invoice_id):
    if request.method == 'POST':
        Invoice.objects.filter(id=invoice_id).delete()
    return redirect('finance:dashboard')


def bulk_import_links(request):
    customers = Customer.objects.all()
    message = None
    if request.method == 'POST':
        raw_data = request.POST.get('raw_data', '')
        imported_count = 0
        urls = re.findall(r'https?://[^\s,\"\']+', raw_data)
        
        for drive_url in urls:
            drive_url = drive_url.rstrip(',.')
            if not drive_url:
                continue
            
            customer, _ = Customer.objects.get_or_create(name="General Marine Client")
            Invoice.objects.create(
                invoice_number=f"ORD-{random.randint(1000, 9999)}",
                customer=customer,
                total_amount=0.00,
                issue_date=timezone.now().date(),
                due_date=timezone.now().date() + timedelta(days=30),
                status='ORDER',
                google_drive_url=drive_url
            )
            imported_count += 1
                
        message = f"Successfully imported {imported_count} files!"

    context = {'customers': customers, 'message': message}
    return render(request, 'finance/bulk_import.html', context)


def price_history_dashboard(request):
    query = request.GET.get('q', '').strip()
    if request.method == 'POST':
        part_name = request.POST.get('part_name', '').strip()
        part_code = request.POST.get('part_code', '').strip()
        supplier_name = request.POST.get('supplier_name', '').strip()
        unit_price = request.POST.get('unit_price', '0.00')
        currency = request.POST.get('currency', 'EUR')
        date_recorded = request.POST.get('date_recorded') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()

        customer, _ = Customer.objects.get_or_create(name=supplier_name) if supplier_name else (None, False)

        PriceRecord.objects.create(
            part_name=part_name,
            part_code=part_code,
            supplier_or_client_name=supplier_name,
            customer=customer,
            unit_price=unit_price,
            currency=currency,
            date_recorded=date_recorded,
            notes=notes
        )
        return redirect('finance:price_history')

    records = PriceRecord.objects.all().order_by('-date_recorded')
    if query:
        records = records.filter(
            Q(part_name__icontains=query) |
            Q(part_code__icontains=query) |
            Q(supplier_or_client_name__icontains=query)
        )

    return render(request, 'finance/price_history.html', {
        'records': records,
        'unique_parts_count': PriceRecord.objects.values('part_name').distinct().count(),
        'total_records': records.count(),
        'query': query,
    })


def delete_price_record(request, record_id):
    if request.method == 'POST':
        PriceRecord.objects.filter(id=record_id).delete()
    return redirect('finance:price_history')


def pricelist_dashboard(request):
    query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip()

    if request.method == 'POST':
        part_name = request.POST.get('part_name', '').strip()
        part_code = request.POST.get('part_code', '').strip()
        category = request.POST.get('category', 'General')
        brand = request.POST.get('brand', '').strip()
        cost_price = float(request.POST.get('cost_price') or 0.00)
        markup_percent = float(request.POST.get('markup_percent') or 30.00)
        availability = request.POST.get('availability', 'In Stock')

        MasterPricelistItem.objects.create(
            part_name=part_name,
            part_code=part_code,
            category=category,
            brand=brand,
            cost_price=cost_price,
            markup_percent=markup_percent,
            availability=availability
        )
        return redirect('finance:pricelist_dashboard')

    items = MasterPricelistItem.objects.all()
    if query:
        items = items.filter(Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(brand__icontains=query))
    if selected_category:
        items = items.filter(category=selected_category)

    return render(request, 'finance/pricelist_dashboard.html', {
        'items': items,
        'total_items': items.count(),
        'avg_markup': round(items.aggregate(Avg('markup_percent'))['markup_percent__avg'] or 30.0, 1),
        'query': query,
        'selected_category': selected_category,
        'category_choices': MasterPricelistItem.CATEGORY_CHOICES,
        'availability_choices': MasterPricelistItem.AVAILABILITY_CHOICES,
    })


def export_pricelist_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="Marine_Specials_Pricelist.csv"'
    writer = csv.writer(response)
    writer.writerow(['Part / OEM Code', 'Description', 'Brand', 'Category', 'Client Price (EUR)', 'Availability'])
    for item in MasterPricelistItem.objects.all():
        writer.writerow([item.part_code or 'N/A', item.part_name, item.brand or 'Generic', item.get_category_display(), f'{item.client_price:.2f} €', item.get_availability_display()])
    return response


def delete_pricelist_item(request, item_id):
    if request.method == 'POST':
        MasterPricelistItem.objects.filter(id=item_id).delete()
    return redirect('finance:pricelist_dashboard')


def client_ledger(request, client_id):
    client = get_object_or_404(Customer, id=client_id)
    profile, _ = ClientFinancialProfile.objects.get_or_create(customer=client)
    client_invoices = Invoice.objects.filter(customer=client).order_by('-issue_date')
    return render(request, 'finance/client_ledger.html', {
        'client': client,
        'profile': profile,
        'invoices': client_invoices,
    })


def export_finances_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="marine_finance_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['Invoice Number', 'Client Name', 'Issue Date', 'Status', 'Total Amount (EUR)'])
    for inv in Invoice.objects.all().order_by('-issue_date'):
        writer.writerow([inv.invoice_number, inv.customer.name, inv.issue_date, inv.status, inv.total_amount])
    return response