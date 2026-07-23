import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q, F
from django.utils import timezone

from .models import Customer, InventoryItem
from finance.models import Invoice

def hub_view(request):
    """Main clean landing hub."""
    total_orders = Invoice.objects.filter(status='ORDER').count()
    total_deliveries = Invoice.objects.filter(status='DELIVERY').count()
    total_inventory_items = InventoryItem.objects.count()
    low_stock_count = InventoryItem.objects.filter(quantity__lte=F('reorder_level')).count()

    active_orders = Invoice.objects.filter(status='ORDER').order_by('-issue_date')[:5]

    context = {
        'total_orders': total_orders,
        'total_deliveries': total_deliveries,
        'total_inventory_items': total_inventory_items,
        'low_stock_count': low_stock_count,
        'active_orders': active_orders,
    }
    return render(request, 'tracker/hub.html', context)

# Alias for url compatibility
app_hub = hub_view


def orders_dashboard(request):
    """Ultra-clean Order & Delivery Note Manager."""
    status_filter = request.GET.get('status', 'ORDER').upper()
    query = request.GET.get('q', '').strip()

    # Fast Manual Order Creation
    if request.method == 'POST' and 'create_order' in request.POST:
        customer_name = request.POST.get('customer_name', '').strip()
        order_number = request.POST.get('order_number', '').strip() or f"ORD-{random.randint(1000, 9999)}"
        total_amount = float(request.POST.get('total_amount') or 0.00)
        issue_date = request.POST.get('issue_date') or timezone.now().date()
        status = request.POST.get('status', 'ORDER')

        if customer_name:
            customer, _ = Customer.objects.get_or_create(name=customer_name)
            Invoice.objects.create(
                invoice_number=order_number,
                customer=customer,
                total_amount=total_amount,
                issue_date=issue_date,
                due_date=issue_date + timedelta(days=30),
                status=status,
                google_drive_url=''
            )
        return redirect(f"{request.path}?status={status}")

    records = Invoice.objects.filter(status__in=['ORDER', 'DELIVERY']).order_by('-issue_date')

    if status_filter != 'ALL':
        records = records.filter(status=status_filter)

    if query:
        records = records.filter(
            Q(invoice_number__icontains=query) |
            Q(customer__name__icontains=query)
        )

    counts = {
        'ORDER': Invoice.objects.filter(status='ORDER').count(),
        'DELIVERY': Invoice.objects.filter(status='DELIVERY').count(),
        'ALL': Invoice.objects.filter(status__in=['ORDER', 'DELIVERY']).count(),
    }

    context = {
        'records': records,
        'status_filter': status_filter,
        'query': query,
        'counts': counts,
        'customers': Customer.objects.all(),
    }
    return render(request, 'tracker/orders.html', context)


def convert_order_status(request, order_id):
    """1-Click status progression: ORDER -> DELIVERY"""
    if request.method == 'POST':
        order = get_object_or_404(Invoice, id=order_id)
        if order.status == 'ORDER':
            order.status = 'DELIVERY'
            order.save()
    return redirect('orders_dashboard')


def delete_order(request, order_id):
    if request.method == 'POST':
        Invoice.objects.filter(id=order_id).delete()
    return redirect('orders_dashboard')


def inventory_list(request):
    """Classic, simple warehouse stock manager."""
    query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'ALL').upper()

    # Fast Inline Quick Add (No Categories)
    if request.method == 'POST' and 'add_item' in request.POST:
        part_name = request.POST.get('part_name', '').strip()
        part_code = request.POST.get('part_code', '').strip()
        quantity = int(request.POST.get('quantity', 1))
        location = request.POST.get('location', 'Piraeus Warehouse').strip()
        unit_cost = float(request.POST.get('unit_cost', 0.00))

        if part_name:
            InventoryItem.objects.create(
                part_name=part_name,
                part_code=part_code,
                category='General', # Defaults quietly in the background
                quantity=quantity,
                reorder_level=5,
                location=location,
                unit_cost=unit_cost
            )
        return redirect('inventory_list')

    items = InventoryItem.objects.all().order_by('-id')

    if filter_type == 'LOW_STOCK':
        items = items.filter(quantity__lte=F('reorder_level'))

    if query:
        items = items.filter(
            Q(part_name__icontains=query) |
            Q(part_code__icontains=query) |
            Q(location__icontains=query)
        )

    counts = {
        'ALL': InventoryItem.objects.count(),
        'LOW_STOCK': InventoryItem.objects.filter(quantity__lte=F('reorder_level')).count(),
    }

    context = {
        'items': items,
        'counts': counts,
        'total_items': items.count(),
        'total_warehouse_value': sum(item.total_stock_value for item in items),
        'query': query,
        'filter_type': filter_type,
    }
    return render(request, 'tracker/inventory_list.html', context)


def adjust_stock(request, item_id, action):
    """In-row 1-click quantity stepper ([+] or [-])."""
    if request.method == 'POST':
        item = get_object_or_404(InventoryItem, id=item_id)
        if action == 'increase':
            item.quantity += 1
        elif action == 'decrease' and item.quantity > 0:
            item.quantity -= 1
        item.save()
    return redirect('inventory_list')


def edit_inventory_item(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    if request.method == 'POST':
        item.part_name = request.POST.get('part_name', item.part_name)
        item.part_code = request.POST.get('part_code', item.part_code)
        item.category = request.POST.get('category', item.category)
        item.quantity = int(request.POST.get('quantity', item.quantity))
        item.reorder_level = int(request.POST.get('reorder_level', item.reorder_level))
        item.location = request.POST.get('location', item.location)
        item.unit_cost = float(request.POST.get('unit_cost', item.unit_cost))
        
        supplier_id = request.POST.get('supplier_id')
        item.supplier = Customer.objects.filter(id=supplier_id).first() if supplier_id else None
        
        item.save()
        return redirect('inventory_list')

    return render(request, 'tracker/inventory_edit.html', {
        'item': item,
        'category_choices': InventoryItem.CATEGORY_CHOICES,
        'customers': Customer.objects.all(),
    })


def delete_inventory_item(request, item_id):
    if request.method == 'POST':
        InventoryItem.objects.filter(id=item_id).delete()
    return redirect('inventory_list')


def client_list(request):
    """Client Ledgers list."""
    clients = Customer.objects.annotate(invoice_count=Count('invoice')).order_by('name')
    return render(request, 'tracker/client_list.html', {'clients': clients})