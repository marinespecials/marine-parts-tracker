import random
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Sum, Count, Avg, F, Value
from django.utils import timezone

from .models import Invoice, PriceRecord, MasterPricelistItem, ClientFinancialProfile
from tracker.models import Customer, InventoryItem, OrderItem


def finance_dashboard(request):
    """Main Financial Intelligence Dashboard."""
    invoices = Invoice.objects.exclude(status='DRAFT').order_by('-issue_date')
    
    unpaid_invoices = invoices.filter(status='UNPAID')
    paid_invoices = invoices.filter(status='PAID')
    overdue_invoices = invoices.filter(status='OVERDUE')

    total_unpaid = sum(inv.total_amount for inv in unpaid_invoices)
    total_paid = sum(inv.total_amount for inv in paid_invoices)

    context = {
        'invoices': invoices[:10],
        'total_unpaid': total_unpaid,
        'total_paid': total_paid,
        'unpaid_count': unpaid_invoices.count(),
        'overdue_count': overdue_invoices.count(),
    }
    return render(request, 'finance/dashboard.html', context)


def client_ledger(request, client_id):
    """Enterprise Client Ledger view with full metrics aggregation."""
    client = get_object_or_404(Customer, id=client_id)
    profile, _ = ClientFinancialProfile.objects.get_or_create(customer=client)

    # Handle Settings Form Submission
    if request.method == 'POST' and 'update_profile' in request.POST:
        profile.internal_rating = request.POST.get('internal_rating', profile.internal_rating)
        profile.payment_terms_days = int(request.POST.get('payment_terms_days') or 30)
        profile.negotiation_notes = request.POST.get('negotiation_notes', '')
        profile.save()
        return redirect('finance:client_ledger', client_id=client.id)

    invoices = Invoice.objects.filter(customer=client).order_by('-issue_date')

    # Lifetime Revenue Calculation
    lifetime_revenue = sum(inv.total_amount for inv in invoices.filter(status='PAID'))
    profile.lifetime_revenue = lifetime_revenue

    # Yearly Summary Aggregation
    yearly_data = (
        invoices.values('issue_date__year')
        .annotate(count=Count('id'), total=Sum('total_amount'))
        .order_by('-issue_date__year')
    )

    # Top Purchased Parts
    top_parts = (
        OrderItem.objects.filter(order__customer=client)
        .values('description')
        .annotate(
            part_name=F('description'),
            purchase_count=Count('id'),
            avg_price=Avg('unit_price'),
            currency=Value('€')
        )
        .order_by('-purchase_count')[:5]
    )

    # Price History
    price_history = PriceRecord.objects.filter(
        supplier_or_client_name__icontains=client.name
    ).order_by('-date_recorded')

    return render(request, 'finance/client_ledger.html', {
        'client': client,
        'profile': profile,
        'invoices': invoices,
        'yearly_data': yearly_data,
        'top_parts': top_parts,
        'price_history': price_history,
    })


def create_invoice(request):
    """Create a new formal Financial Invoice with optional initial line items."""
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        invoice_number = request.POST.get('invoice_number', '').strip() or f"INV-{random.randint(1000, 9999)}"
        raw_issue_date = request.POST.get('issue_date')
        raw_due_date = request.POST.get('due_date')
        status = request.POST.get('status', 'UNPAID')
        google_drive_url = request.POST.get('google_drive_url', '').strip()

        try:
            issue_date = date.fromisoformat(raw_issue_date) if raw_issue_date else timezone.now().date()
        except ValueError:
            issue_date = timezone.now().date()

        try:
            due_date = date.fromisoformat(raw_due_date) if raw_due_date else issue_date + timedelta(days=30)
        except ValueError:
            due_date = issue_date + timedelta(days=30)

        if customer_name:
            customer, _ = Customer.objects.get_or_create(name=customer_name)
            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                customer=customer,
                total_amount=0.00,
                issue_date=issue_date,
                due_date=due_date,
                status=status,
                google_drive_url=google_drive_url
            )

            inventory_id = request.POST.get('inventory_id')
            custom_desc = request.POST.get('custom_description', '').strip()
            quantity = int(request.POST.get('quantity') or 1)
            unit_price = request.POST.get('unit_price')

            if inventory_id or custom_desc:
                if inventory_id:
                    inv_item = InventoryItem.objects.filter(id=inventory_id).first()
                    desc = custom_desc or (f"{inv_item.part_name} ({inv_item.part_code})" if inv_item and inv_item.part_code else (inv_item.part_name if inv_item else 'Item'))
                    price = float(unit_price) if unit_price else float(inv_item.unit_cost if inv_item else 0.0)
                else:
                    inv_item = None
                    desc = custom_desc
                    price = float(unit_price or 0.0)

                OrderItem.objects.create(
                    order=invoice,
                    inventory_item=inv_item,
                    description=desc,
                    quantity=quantity,
                    unit_price=price
                )
                invoice.total_amount = sum(item.total_price for item in invoice.order_items.all())
                invoice.save()

            return redirect('finance:invoice_detail', invoice_id=invoice.id)

    master_items = InventoryItem.objects.all().order_by('part_name')
    customers = Customer.objects.all().order_by('name')
    return render(request, 'finance/invoice_form.html', {
        'master_items': master_items,
        'customers': customers,
    })


def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    master_items = InventoryItem.objects.all().order_by('part_name')
    return render(request, 'finance/invoice_detail.html', {
        'invoice': invoice,
        'master_items': master_items,
    })


def add_invoice_item(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        inventory_id = request.POST.get('inventory_id')
        quantity = int(request.POST.get('quantity') or 1)
        custom_price = request.POST.get('unit_price')
        custom_desc = request.POST.get('description', '').strip()

        if inventory_id:
            inv_item = InventoryItem.objects.filter(id=inventory_id).first()
            desc = custom_desc or (f"{inv_item.part_name} ({inv_item.part_code})" if inv_item and inv_item.part_code else (inv_item.part_name if inv_item else 'Item'))
            unit_price = float(custom_price) if custom_price else float(inv_item.unit_cost if inv_item else 0.0)
        else:
            inv_item = None
            desc = custom_desc or 'Billed Item / Service'
            unit_price = float(custom_price or 0.00)

        OrderItem.objects.create(
            order=invoice,
            inventory_item=inv_item,
            description=desc,
            quantity=quantity,
            unit_price=unit_price
        )
        invoice.total_amount = sum(item.total_price for item in invoice.order_items.all())
        invoice.save()

    return redirect('finance:invoice_detail', invoice_id=invoice.id)


def delete_invoice_item(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(OrderItem, id=item_id)
        invoice = item.order
        item.delete()
        invoice.total_amount = sum(i.total_price for i in invoice.order_items.all())
        invoice.save()
        return redirect('finance:invoice_detail', invoice_id=invoice.id)


def delete_invoice(request, invoice_id):
    """Delete an invoice and return to the client ledger."""
    if request.method == 'POST':
        invoice = get_object_or_404(Invoice, id=invoice_id)
        client_id = invoice.customer.id if invoice.customer else None
        invoice.delete()
        if client_id:
            return redirect('finance:client_ledger', client_id=client_id)
    return redirect('finance:dashboard')


def update_invoice_details(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        invoice.status = request.POST.get('status', invoice.status)
        invoice.google_drive_url = request.POST.get('google_drive_url', invoice.google_drive_url).strip()
        raw_due_date = request.POST.get('due_date')
        if raw_due_date:
            try:
                invoice.due_date = date.fromisoformat(raw_due_date)
            except ValueError:
                pass
        invoice.save()
    return redirect('finance:invoice_detail', invoice_id=invoice.id)


def edit_invoice(request, invoice_id):
    return redirect('finance:invoice_detail', invoice_id=invoice_id)


def bulk_import(request):
    return render(request, 'finance/bulk_import.html')


def pricelist_dashboard(request):
    items = MasterPricelistItem.objects.all()
    return render(request, 'finance/pricelist.html', {'items': items})


def price_history(request):
    records = PriceRecord.objects.all().order_by('-date_recorded')
    return render(request, 'finance/price_history.html', {'records': records})


def export_finances(request):
    return redirect('finance:dashboard')