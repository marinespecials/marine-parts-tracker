from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q, F
from .models import Customer, InventoryItem
from finance.models import Invoice, MasterPricelistItem

def hub_view(request):
    """Main landing hub connecting all system apps."""
    total_invoices = Invoice.objects.count()
    total_inventory_items = InventoryItem.objects.count()
    low_stock_count = InventoryItem.objects.filter(quantity__lte=F('reorder_level')).count()
    total_pricelist_items = MasterPricelistItem.objects.count()
    total_clients = Customer.objects.count()

    recent_invoices = Invoice.objects.all().order_by('-issue_date')[:5]
    low_stock_items = InventoryItem.objects.filter(quantity__lte=F('reorder_level'))[:5]

    context = {
        'total_invoices': total_invoices,
        'total_inventory_items': total_inventory_items,
        'low_stock_count': low_stock_count,
        'total_pricelist_items': total_pricelist_items,
        'total_clients': total_clients,
        'recent_invoices': recent_invoices,
        'low_stock_items': low_stock_items,
    }
    return render(request, 'tracker/hub.html', context)

# Alias for url compatibility
app_hub = hub_view


def inventory_list(request):
    """Warehouse inventory dashboard and item management."""
    query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip()

    if request.method == 'POST':
        part_name = request.POST.get('part_name', '').strip()
        part_code = request.POST.get('part_code', '').strip()
        category = request.POST.get('category', 'General')
        quantity = int(request.POST.get('quantity', 0))
        reorder_level = int(request.POST.get('reorder_level', 5))
        location = request.POST.get('location', 'Piraeus Warehouse').strip()
        unit_cost = float(request.POST.get('unit_cost', 0.00))
        supplier_id = request.POST.get('supplier_id')

        supplier = Customer.objects.filter(id=supplier_id).first() if supplier_id else None

        InventoryItem.objects.create(
            part_name=part_name,
            part_code=part_code,
            category=category,
            quantity=quantity,
            reorder_level=reorder_level,
            location=location,
            unit_cost=unit_cost,
            supplier=supplier
        )
        return redirect('inventory_list')

    items = InventoryItem.objects.all()

    if query:
        items = items.filter(
            Q(part_name__icontains=query) |
            Q(part_code__icontains=query) |
            Q(location__icontains=query)
        )

    if selected_category:
        items = items.filter(category=selected_category)

    total_items = items.count()
    total_warehouse_value = sum(item.total_stock_value for item in items)
    low_stock_count = items.filter(quantity__lte=F('reorder_level')).count()

    context = {
        'items': items,
        'total_items': total_items,
        'total_warehouse_value': total_warehouse_value,
        'low_stock_count': low_stock_count,
        'query': query,
        'selected_category': selected_category,
        'category_choices': InventoryItem.CATEGORY_CHOICES,
        'customers': Customer.objects.all(),
    }
    return render(request, 'tracker/inventory_list.html', context)


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

    context = {
        'item': item,
        'category_choices': InventoryItem.CATEGORY_CHOICES,
        'customers': Customer.objects.all(),
    }
    return render(request, 'tracker/inventory_edit.html', context)


def delete_inventory_item(request, item_id):
    if request.method == 'POST':
        InventoryItem.objects.filter(id=item_id).delete()
    return redirect('inventory_list')


def client_list(request):
    """Client Ledgers List View."""
    clients = Customer.objects.annotate(invoice_count=Count('invoice')).order_by('name')
    context = {'clients': clients}
    return render(request, 'tracker/client_list.html', context)