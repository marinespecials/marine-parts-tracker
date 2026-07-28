import random
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q, F
from django.utils import timezone
from django.urls import reverse

from .models import Customer, InventoryItem, OrderItem
from finance.models import Invoice


def _process_order_item_stock(inventory_id, custom_desc, quantity, unit_price):
    inv_item = None
    desc = ""
    price = 0.0

    if inventory_id:
        inv_item = InventoryItem.objects.filter(id=inventory_id).first()

    clean_desc = (custom_desc or '').strip()

    if not inv_item and clean_desc:
        inv_item = InventoryItem.objects.filter(
            Q(part_name__iexact=clean_desc) | Q(part_code__iexact=clean_desc)
        ).first()

    if inv_item:
        desc = clean_desc or (f"{inv_item.part_name} ({inv_item.part_code})" if inv_item.part_code else inv_item.part_name)
        price = float(unit_price) if unit_price is not None and str(unit_price).strip() != '' else float(inv_item.unit_cost)
        inv_item.quantity = max(0, inv_item.quantity - quantity)
        inv_item.save()
    elif clean_desc:
        price = float(unit_price or 0.0)
        inv_item = InventoryItem.objects.create(
            part_name=clean_desc,
            part_code='',
            category='General',
            quantity=0,
            reorder_level=5,
            location='Piraeus Warehouse',
            unit_cost=price
        )
        desc = clean_desc

    return inv_item, desc, price


def sync_all_historical_orders(request):
    """
    Scans ALL past order items in the database:
    1. Links unlinked items to matching Master Warehouse parts (or creates new ones).
    2. Syncs stock counts across all orders.
    """
    if request.method == 'POST':
        unlinked_items = OrderItem.objects.filter(inventory_item__isnull=True)
        
        for item in unlinked_items:
            clean_desc = item.description.strip()
            if not clean_desc:
                continue

            # Check if part already exists in warehouse
            match = InventoryItem.objects.filter(
                Q(part_name__iexact=clean_desc) | Q(part_code__iexact=clean_desc)
            ).first()

            if match:
                item.inventory_item = match
                item.save()
                match.quantity = max(0, match.quantity - item.quantity)
                match.save()
            else:
                # Auto-create new warehouse part for old item
                new_inv = InventoryItem.objects.create(
                    part_name=clean_desc,
                    part_code='',
                    category='General',
                    quantity=0,
                    reorder_level=5,
                    location='Piraeus Warehouse',
                    unit_cost=float(item.unit_price or 0.0)
                )
                item.inventory_item = new_inv
                item.save()

    return redirect('orders_dashboard')


def hub_view(request):
    total_orders = Invoice.objects.filter(status__in=['PENDING', 'PROCESSING']).count()
    total_deliveries = Invoice.objects.filter(status='DELIVERED').count()
    context = {
        'total_orders': total_orders,
        'total_deliveries': total_deliveries,
        'total_inventory_items': InventoryItem.objects.count(),
        'low_stock_count': InventoryItem.objects.filter(quantity__lte=F('reorder_level')).count(),
        'active_orders': Invoice.objects.filter(status__in=['PENDING', 'PROCESSING']).order_by('-issue_date')[:5],
    }
    return render(request, 'tracker/hub.html', context)

app_hub = hub_view


def active_board(request):
    orders = Invoice.objects.filter(status__in=['PENDING', 'PROCESSING']).order_by('issue_date')
    for order in orders:
        items = order.order_items.all()
        total_items = items.count()
        packed_items = items.filter(is_packed=True).count()
        
        if total_items > 0:
            order.progress = int((packed_items / total_items) * 100)
        else:
            order.progress = 50 if order.status == 'PROCESSING' else 0

        absolute_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
        order.qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=120x120&data={absolute_url}"

    return render(request, 'tracker/active_board.html', {'orders': orders})


def orders_dashboard(request):
    status_filter = request.GET.get('status', 'PENDING').upper()
    query = request.GET.get('q', '').strip()

    records = Invoice.objects.exclude(status='DRAFT').order_by('-issue_date')

    if status_filter != 'ALL':
        records = records.filter(status=status_filter)
    if query:
        records = records.filter(Q(invoice_number__icontains=query) | Q(customer__name__icontains=query))

    counts = {
        'PENDING': Invoice.objects.filter(status='PENDING').count(),
        'PROCESSING': Invoice.objects.filter(status='PROCESSING').count(),
        'DELIVERED': Invoice.objects.filter(status='DELIVERED').count(),
        'ALL': Invoice.objects.exclude(status='DRAFT').count(),
    }

    return render(request, 'tracker/orders.html', {
        'records': records,
        'status_filter': status_filter,
        'query': query,
        'counts': counts,
    })


def create_order(request):
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        order_number = request.POST.get('order_number', '').strip() or f"ORD-{random.randint(1000, 9999)}"
        raw_issue_date = request.POST.get('issue_date')
        raw_due_date = request.POST.get('due_date')
        status = request.POST.get('status', 'PENDING')

        try:
            issue_date = date.fromisoformat(raw_issue_date) if raw_issue_date else timezone.now().date()
        except ValueError:
            issue_date = timezone.now().date()

        try:
            due_date = date.fromisoformat(raw_due_date) if raw_due_date else issue_date + timedelta(days=14)
        except ValueError:
            due_date = issue_date + timedelta(days=14)

        if customer_name:
            customer, _ = Customer.objects.get_or_create(name=customer_name)
            order = Invoice.objects.create(
                invoice_number=order_number,
                customer=customer,
                total_amount=0.00,
                issue_date=issue_date,
                due_date=due_date,
                status=status,
                google_drive_url=''
            )

            inventory_id = request.POST.get('inventory_id')
            custom_desc = request.POST.get('custom_description', '').strip()
            quantity = int(request.POST.get('quantity') or 1)
            unit_price = request.POST.get('unit_price')

            if inventory_id or custom_desc:
                inv_item, desc, price = _process_order_item_stock(inventory_id, custom_desc, quantity, unit_price)
                OrderItem.objects.create(
                    order=order,
                    inventory_item=inv_item,
                    description=desc,
                    quantity=quantity,
                    unit_price=price
                )
                order.total_amount = sum(item.total_price for item in order.order_items.all())
                order.save()

            return redirect('order_detail', order_id=order.id)

    master_items = InventoryItem.objects.all().order_by('part_name')
    customers = Customer.objects.all().order_by('name')
    return render(request, 'tracker/order_form.html', {
        'master_items': master_items,
        'customers': customers,
    })


def order_detail(request, order_id):
    order = get_object_or_404(Invoice, id=order_id)
    master_items = InventoryItem.objects.all().order_by('part_name')
    return render(request, 'tracker/order_detail.html', {'order': order, 'master_items': master_items})


def link_order_item_to_inventory(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(OrderItem, id=item_id)
        inventory_id = request.POST.get('inventory_id')
        if inventory_id:
            inv = get_object_or_404(InventoryItem, id=inventory_id)
            item.inventory_item = inv
            item.save()
            inv.quantity = max(0, inv.quantity - item.quantity)
            inv.save()

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)

    return redirect('order_detail', order_id=item.order.id)


def add_order_item(request, order_id):
    order = get_object_or_404(Invoice, id=order_id)
    if request.method == 'POST':
        inventory_id = request.POST.get('inventory_id')
        custom_desc = request.POST.get('description', '').strip()
        quantity = int(request.POST.get('quantity') or 1)
        unit_price = request.POST.get('unit_price')

        if inventory_id or custom_desc:
            inv_item, desc, price = _process_order_item_stock(inventory_id, custom_desc, quantity, unit_price)
            OrderItem.objects.create(
                order=order,
                inventory_item=inv_item,
                description=desc,
                quantity=quantity,
                unit_price=price
            )
            order.total_amount = sum(item.total_price for item in order.order_items.all())
            order.save()
        
    return redirect('order_detail', order_id=order.id)


def adjust_order_item_qty(request, item_id, action):
    if request.method == 'POST':
        item = get_object_or_404(OrderItem, id=item_id)
        order = item.order

        if action == 'increase':
            item.quantity += 1
            item.save()
            if item.inventory_item:
                inv = item.inventory_item
                inv.quantity = max(0, inv.quantity - 1)
                inv.save()
        elif action == 'decrease':
            if item.quantity > 1:
                item.quantity -= 1
                item.save()
                if item.inventory_item:
                    inv = item.inventory_item
                    inv.quantity += 1
                    inv.save()
            else:
                if item.inventory_item:
                    inv = item.inventory_item
                    inv.quantity += 1
                    inv.save()
                item.delete()

        order.total_amount = sum(i.total_price for i in order.order_items.all())
        order.save()

        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)

    return redirect('order_detail', order_id=item.order.id)


def toggle_item_packed(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(OrderItem, id=item_id)
        item.is_packed = not item.is_packed
        item.save()
        
        order = item.order
        total = order.order_items.count()
        packed = order.order_items.filter(is_packed=True).count()
        
        if packed == total and total > 0:
            order.status = 'PROCESSING'
        elif packed > 0:
            order.status = 'PROCESSING'
        
        order.save()
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
            
    return redirect('order_detail', order_id=item.order.id)


def delete_order_item(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(OrderItem, id=item_id)
        order = item.order
        
        if item.inventory_item:
            inv = item.inventory_item
            inv.quantity += item.quantity
            inv.save()

        item.delete()
        order.total_amount = sum(i.total_price for i in order.order_items.all())
        order.save()
        return redirect('order_detail', order_id=order.id)


def change_order_status(request, order_id, new_status):
    if request.method == 'POST':
        order = get_object_or_404(Invoice, id=order_id)
        order.status = new_status.upper()
        order.save()
    return redirect('orders_dashboard')


def convert_order_to_invoice(request, order_id):
    if request.method == 'POST':
        original_order = get_object_or_404(Invoice, id=order_id)
        
        raw_num = original_order.invoice_number.replace('ORD-', '')
        inv_num = f"INV-{raw_num}"
        if Invoice.objects.filter(invoice_number=inv_num).exists():
            inv_num = f"INV-{random.randint(1000, 9999)}"

        issue_date = timezone.now().date()
        due_date = issue_date + timedelta(days=30)

        new_invoice = Invoice.objects.create(
            invoice_number=inv_num,
            customer=original_order.customer,
            total_amount=original_order.total_amount,
            issue_date=issue_date,
            due_date=due_date,
            status='UNPAID',
            google_drive_url=original_order.google_drive_url
        )

        for item in original_order.order_items.all():
            OrderItem.objects.create(
                order=new_invoice,
                inventory_item=item.inventory_item,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                is_packed=True
            )

        return redirect('finance:invoice_detail', invoice_id=new_invoice.id)
    
    return redirect('order_detail', order_id=order_id)


def delete_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Invoice, id=order_id)
        for item in order.order_items.all():
            if item.inventory_item:
                inv = item.inventory_item
                inv.quantity += item.quantity
                inv.save()
        order.delete()
    return redirect('orders_dashboard')


def inventory_list(request):
    query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'ALL').upper()

    if request.method == 'POST' and 'add_item' in request.POST:
        part_name = request.POST.get('part_name', '').strip()
        part_code = request.POST.get('part_code', '').strip()
        quantity = int(request.POST.get('quantity') or 1)
        location = request.POST.get('location', 'Piraeus Warehouse').strip()
        unit_cost = float(request.POST.get('unit_cost') or 0.00)

        if part_name:
            InventoryItem.objects.create(
                part_name=part_name,
                part_code=part_code,
                category='General',
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
        items = items.filter(Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(location__icontains=query))

    counts = {
        'ALL': InventoryItem.objects.count(),
        'LOW_STOCK': InventoryItem.objects.filter(quantity__lte=F('reorder_level')).count()
    }
    return render(request, 'tracker/inventory_list.html', {
        'items': items,
        'counts': counts,
        'total_items': items.count(),
        'total_warehouse_value': sum(item.total_stock_value for item in items),
        'query': query,
        'filter_type': filter_type,
    })


def client_pricelist(request):
    query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', 'ALL')

    items = InventoryItem.objects.all().order_by('part_name')

    if category_filter != 'ALL':
        items = items.filter(category=category_filter)

    if query:
        items = items.filter(
            Q(part_name__icontains=query) |
            Q(part_code__icontains=query) |
            Q(category__icontains=query)
        )

    categories = InventoryItem.objects.values_list('category', flat=True).distinct()

    return render(request, 'tracker/client_pricelist.html', {
        'items': items,
        'query': query,
        'category_filter': category_filter,
        'categories': categories,
    })


def adjust_stock(request, item_id, action):
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
        item.quantity = int(request.POST.get('quantity') or item.quantity)
        item.location = request.POST.get('location', item.location)
        item.unit_cost = float(request.POST.get('unit_cost') or item.unit_cost)
        item.save()
        return redirect('inventory_list')
    return render(request, 'tracker/inventory_edit.html', {'item': item})


def delete_inventory_item(request, item_id):
    if request.method == 'POST':
        InventoryItem.objects.filter(id=item_id).delete()
    return redirect('inventory_list')


def client_list(request):
    clients = Customer.objects.annotate(invoice_count=Count('invoice')).order_by('name')
    return render(request, 'tracker/client_list.html', {'clients': clients})


def global_search(request):
    query = request.GET.get('q', '').strip()
    orders = []
    invoices = []
    inventory = []
    clients = []

    if query:
        all_docs = Invoice.objects.filter(
            Q(invoice_number__icontains=query) | Q(customer__name__icontains=query)
        ).order_by('-issue_date')
        
        orders = all_docs.filter(status__in=['PENDING', 'PROCESSING', 'DELIVERED'])
        invoices = all_docs.filter(status__in=['UNPAID', 'PAID', 'OVERDUE', 'DRAFT'])
        
        inventory = InventoryItem.objects.filter(
            Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(location__icontains=query)
        )

        clients = Customer.objects.filter(name__icontains=query)

    return render(request, 'tracker/search_results.html', {
        'query': query,
        'orders': orders,
        'invoices': invoices,
        'inventory': inventory,
        'clients': clients,
    })


def mobile_packing_list(request, order_id):
    order = get_object_or_404(Invoice, id=order_id)
    items = order.order_items.all()
    total_items = items.count()
    packed_items = items.filter(is_packed=True).count()
    progress = int((packed_items / total_items) * 100) if total_items > 0 else 0

    return render(request, 'tracker/mobile_pack.html', {
        'order': order,
        'items': items,
        'total_items': total_items,
        'packed_items': packed_items,
        'progress': progress,
    })