import json
import random
from decimal import Decimal
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q, F, Sum, Max, DecimalField, ExpressionWrapper
from django.utils import timezone
from django.urls import reverse
from django.db import transaction
from django.contrib import messages
from django.utils.translation import gettext as _

from core.utils import to_decimal, to_int, redirect_back

from .models import (
    Customer, InventoryItem, OrderItem, Supplier, PurchaseOrder, PurchaseOrderItem,
    PART_CATEGORIES, guess_category,
)
from finance.models import Invoice, PriceRecord, MasterPricelistItem
from tracker.templatetags.ui import STATUS_LABELS

ORDER_STATUSES = ['PENDING', 'PROCESSING', 'DELIVERED']
INVOICE_STATUSES = ['UNPAID', 'OVERDUE', 'PAID']
CATEGORY_CODES = {code for code, _label in PART_CATEGORIES}

STOCK_VALUE = ExpressionWrapper(F('quantity') * F('unit_cost'), output_field=DecimalField(max_digits=14, decimal_places=2))


# ==========================================
# SHARED HELPERS
# ==========================================

def parts_json():
    """Every warehouse part, once, for the part pickers (static/js/app.js fills the <select>s)."""
    return [
        {'id': p['id'], 'name': p['part_name'], 'code': p['part_code'] or '', 'qty': p['quantity'],
         'cost': f"{p['unit_cost']:.2f}"}
        for p in InventoryItem.objects.order_by('part_name').values('id', 'part_name', 'part_code', 'quantity', 'unit_cost')
    ]


def related_document(doc):
    """The order behind an invoice (or the invoice made from an order).
    'Convert to invoice' turns ORD-1234 into INV-1234 for the same client."""
    number = doc.invoice_number or ''
    if number.startswith('ORD-'):
        twin, statuses = 'INV-' + number[4:], INVOICE_STATUSES + ['DRAFT', 'VOID']
    elif number.startswith('INV-'):
        twin, statuses = 'ORD-' + number[4:], ORDER_STATUSES
    else:
        return None
    return Invoice.objects.filter(invoice_number=twin, customer_id=doc.customer_id,
                                  status__in=statuses).exclude(id=doc.id).first()


def _recalc_total(doc):
    doc.total_amount = sum(i.total_price for i in doc.order_items.all())
    doc.save()


def _process_order_item_stock(inventory_id, custom_desc, quantity, unit_price):
    inv_item = None
    desc = ""
    price = Decimal('0.00')

    if inventory_id:
        inv_item = InventoryItem.objects.filter(id=inventory_id).first()

    clean_desc = (custom_desc or '').strip()

    if not inv_item and clean_desc:
        inv_item = InventoryItem.objects.filter(
            Q(part_name__iexact=clean_desc) | Q(part_code__iexact=clean_desc)
        ).first()

    if inv_item:
        desc = clean_desc or (f"{inv_item.part_name} ({inv_item.part_code})" if inv_item.part_code else inv_item.part_name)
        price = to_decimal(unit_price, default=inv_item.unit_cost, minimum=0)
        inv_item.quantity = max(0, inv_item.quantity - quantity)
        inv_item.save()
    elif clean_desc:
        price = to_decimal(unit_price, minimum=0)
        inv_item = InventoryItem.objects.create(
            part_name=clean_desc,
            part_code='',
            category=guess_category(clean_desc),
            quantity=0,
            reorder_level=5,
            location='Piraeus Warehouse',
            unit_cost=price
        )
        desc = clean_desc

    return inv_item, desc, price


@transaction.atomic
def sync_all_historical_orders(request):
    if request.method == 'POST':
        unlinked_items = OrderItem.objects.filter(inventory_item__isnull=True)
        linked = created = 0

        for item in unlinked_items:
            clean_desc = item.description.strip()
            if not clean_desc:
                continue

            match = InventoryItem.objects.filter(
                Q(part_name__iexact=clean_desc) | Q(part_code__iexact=clean_desc)
            ).first()

            if match:
                item.inventory_item = match
                item.save()
                match.quantity = max(0, match.quantity - item.quantity)
                match.save()
                linked += 1
            else:
                new_inv = InventoryItem.objects.create(
                    part_name=clean_desc,
                    part_code='',
                    category=guess_category(clean_desc),
                    quantity=0,
                    reorder_level=5,
                    location='Piraeus Warehouse',
                    unit_cost=item.unit_price or 0
                )
                item.inventory_item = new_inv
                item.save()
                created += 1
        messages.success(request, _("Linked %(linked)s order lines to existing parts and created %(created)s new warehouse parts.") % {'linked': linked, 'created': created})

    return redirect('orders_dashboard')


# ==========================================
# DASHBOARD & OPERATIONS
# ==========================================

def hub_view(request):
    active = Invoice.objects.filter(status__in=['PENDING', 'PROCESSING'])
    unpaid = Invoice.objects.filter(status__in=['UNPAID', 'OVERDUE'])
    low_stock = InventoryItem.objects.filter(quantity__lte=F('reorder_level'))
    month_start = timezone.localdate().replace(day=1)

    context = {
        'total_orders': active.count(),
        'total_deliveries': Invoice.objects.filter(status='DELIVERED').count(),
        'total_inventory_items': InventoryItem.objects.count(),
        'warehouse_value': InventoryItem.objects.aggregate(v=Sum(STOCK_VALUE))['v'] or 0,
        'low_stock_count': low_stock.count(),
        'active_orders': active.select_related('customer').annotate(
            line_count=Count('order_items'), packed_count=Count('order_items', filter=Q(order_items__is_packed=True)),
        ).order_by('-issue_date', '-id')[:6],
        'low_stock_items': low_stock.order_by('quantity')[:6],
        'unpaid_count': unpaid.count(),
        'unpaid_total': unpaid.aggregate(t=Sum('total_amount'))['t'] or 0,
        'overdue_count': Invoice.objects.filter(status='OVERDUE').count(),
        'paid_this_month': Invoice.objects.filter(status='PAID', issue_date__gte=month_start)
                                          .aggregate(t=Sum('total_amount'))['t'] or 0,
        'recent_invoices': Invoice.objects.filter(status__in=INVOICE_STATUSES).select_related('customer')
                                          .order_by('-issue_date', '-id')[:5],
        'open_pos': PurchaseOrder.objects.exclude(status='RECEIVED').select_related('supplier').order_by('-issue_date')[:4],
    }
    return render(request, 'tracker/hub.html', context)

app_hub = hub_view


def active_board(request):
    orders = (
        Invoice.objects.filter(status__in=['PENDING', 'PROCESSING'])
        .select_related('customer')
        .annotate(line_count=Count('order_items'),
                  packed_count=Count('order_items', filter=Q(order_items__is_packed=True)))
        .order_by('issue_date', 'id')
    )
    for order in orders:
        if order.line_count:
            order.progress = int(order.packed_count * 100 / order.line_count)
        else:
            order.progress = 50 if order.status == 'PROCESSING' else 0
        absolute_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
        order.qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=160x160&margin=0&data={absolute_url}"

    return render(request, 'tracker/active_board.html', {'orders': orders})


def orders_dashboard(request):
    status_filter = request.GET.get('status', 'PENDING').upper()
    query = request.GET.get('q', '').strip()

    records = Invoice.objects.exclude(status='DRAFT').select_related('customer').annotate(
        line_count=Count('order_items'),
    ).order_by('-issue_date', '-id')

    if status_filter != 'ALL':
        records = records.filter(status=status_filter)
    if query:
        records = records.filter(Q(invoice_number__icontains=query) | Q(customer__name__icontains=query))

    counts = Invoice.objects.aggregate(
        PENDING=Count('id', filter=Q(status='PENDING')),
        PROCESSING=Count('id', filter=Q(status='PROCESSING')),
        DELIVERED=Count('id', filter=Q(status='DELIVERED')),
        ALL=Count('id', filter=~Q(status='DRAFT')),
    )

    return render(request, 'tracker/orders.html', {
        'records': records,
        'status_filter': status_filter,
        'query': query,
        'counts': counts,
        'order_statuses': ORDER_STATUSES,
    })


@transaction.atomic
def create_order(request):
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        order_number = request.POST.get('order_number', '').strip() or f"ORD-{random.randint(1000, 9999)}"
        raw_issue_date = request.POST.get('issue_date')
        raw_due_date = request.POST.get('due_date')
        status = request.POST.get('status', 'PENDING')
        if status not in ORDER_STATUSES:
            status = 'PENDING'

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
            quantity = to_int(request.POST.get('quantity'), 1, 1)
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
                _recalc_total(order)

            messages.success(request, _("Order %(n)s created.") % {'n': order.invoice_number})
            return redirect('order_detail', order_id=order.id)
        messages.error(request, _("Please enter a client or vessel name."))

    return render(request, 'tracker/order_form.html', {
        'parts': parts_json(),
        'customers': Customer.objects.order_by('name').values_list('name', flat=True),
        'today': timezone.localdate(),
        'preset_client': request.GET.get('client', ''),
    })


def order_detail(request, order_id):
    order = get_object_or_404(Invoice.objects.select_related('customer'), id=order_id)
    items = list(order.order_items.select_related('inventory_item').order_by('id'))
    packed = sum(1 for i in items if i.is_packed)
    return render(request, 'tracker/order_detail.html', {
        'order': order,
        'items': items,
        'packed_count': packed,
        'progress': int(packed * 100 / len(items)) if items else 0,
        'parts': parts_json(),
        'related': related_document(order),
        'order_statuses': ORDER_STATUSES,
    })


@transaction.atomic
def link_order_item_to_inventory(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    if request.method == 'POST':
        inventory_id = request.POST.get('inventory_id')
        if inventory_id:
            inv = get_object_or_404(InventoryItem, id=inventory_id)
            item.inventory_item = inv
            item.save()
            inv.quantity = max(0, inv.quantity - item.quantity)
            inv.save()
            messages.success(request, _("Linked to %(part)s; stock reduced by %(qty)s.") % {'part': inv.part_name, 'qty': item.quantity})

    return redirect_back(request, 'order_detail', order_id=item.order_id)


@transaction.atomic
def add_order_item(request, order_id):
    order = get_object_or_404(Invoice, id=order_id)
    if request.method == 'POST':
        inventory_id = request.POST.get('inventory_id')
        custom_desc = request.POST.get('description', '').strip()
        quantity = to_int(request.POST.get('quantity'), 1, 1)
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
            _recalc_total(order)
        else:
            messages.error(request, _("Pick a warehouse part or type an item name."))

    return redirect('order_detail', order_id=order.id)


@transaction.atomic
def adjust_order_item_qty(request, item_id, action):
    item = get_object_or_404(OrderItem, id=item_id)
    order_id = item.order_id
    if request.method == 'POST':
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

        _recalc_total(order)
        return redirect_back(request, 'order_detail', order_id=order_id)

    return redirect('order_detail', order_id=order_id)


def toggle_item_packed(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    if request.method == 'POST':
        item.is_packed = not item.is_packed
        item.save()

        order = item.order
        if item.is_packed and order.status == 'PENDING':
            order.status = 'PROCESSING'
            order.save()

        return redirect_back(request, 'order_detail', order_id=order.id)

    return redirect('order_detail', order_id=item.order.id)


@transaction.atomic
def delete_order_item(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(OrderItem, id=item_id)
        order = item.order

        if item.inventory_item:
            inv = item.inventory_item
            inv.quantity += item.quantity
            inv.save()

        item.delete()
        _recalc_total(order)
        return redirect('order_detail', order_id=order.id)
    return redirect('orders_dashboard')


def change_order_status(request, order_id, new_status):
    if request.method == 'POST':
        order = get_object_or_404(Invoice, id=order_id)
        new_status = new_status.upper()
        if new_status in {code for code, _label in Invoice.STATUS_CHOICES}:
            order.status = new_status
            order.save()
            messages.success(request, _("%(n)s marked %(status)s.") % {'n': order.invoice_number, 'status': STATUS_LABELS.get(new_status, new_status)})
        else:
            messages.error(request, _("'%(status)s' is not a valid status.") % {'status': new_status})

    return redirect_back(request, 'orders_dashboard')


@transaction.atomic
def convert_order_to_invoice(request, order_id):
    if request.method == 'POST':
        original_order = get_object_or_404(Invoice, id=order_id)

        existing = related_document(original_order)
        if existing and existing.invoice_number.startswith('INV-'):
            messages.info(request, _("This order was already invoiced as %(n)s.") % {'n': existing.invoice_number})
            return redirect('finance:invoice_detail', invoice_id=existing.id)

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

        messages.success(request, _("Invoice %(inv)s created from %(order)s.") % {'inv': inv_num, 'order': original_order.invoice_number})
        return redirect('finance:invoice_detail', invoice_id=new_invoice.id)

    return redirect('order_detail', order_id=order_id)


@transaction.atomic
def delete_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Invoice, id=order_id)
        for item in order.order_items.all():
            if item.inventory_item:
                inv = item.inventory_item
                inv.quantity += item.quantity
                inv.save()
        number = order.invoice_number
        order.delete()
        messages.success(request, _("Order %(n)s deleted and its stock returned to the warehouse.") % {'n': number})
    return redirect('orders_dashboard')


def mobile_packing_list(request, order_id):
    order = get_object_or_404(Invoice.objects.select_related('customer'), id=order_id)
    items = list(order.order_items.select_related('inventory_item').order_by('is_packed', 'id'))
    total_items = len(items)
    packed_items = sum(1 for i in items if i.is_packed)
    progress = int((packed_items / total_items) * 100) if total_items > 0 else 0

    return render(request, 'tracker/mobile_pack.html', {
        'order': order,
        'items': items,
        'total_items': total_items,
        'packed_items': packed_items,
        'progress': progress,
    })


# ==========================================
# WAREHOUSE & PARTS
# ==========================================

def inventory_list(request):
    query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'ALL').upper()
    category_filter = request.GET.get('category', 'ALL')

    if request.method == 'POST' and 'add_item' in request.POST:
        part_name = request.POST.get('part_name', '').strip()
        part_code = request.POST.get('part_code', '').strip()
        quantity = to_int(request.POST.get('quantity'), 1, 0)
        location = request.POST.get('location', '').strip() or 'Piraeus Warehouse'
        unit_cost = to_decimal(request.POST.get('unit_cost'), minimum=0)
        category = request.POST.get('category', 'AUTO')
        if category not in CATEGORY_CODES:
            category = guess_category(part_name, part_code)

        if part_name:
            item = InventoryItem.objects.create(
                part_name=part_name,
                part_code=part_code,
                category=category,
                quantity=quantity,
                reorder_level=to_int(request.POST.get('reorder_level'), 5, 0),
                location=location,
                unit_cost=unit_cost
            )
            messages.success(request, _("%(part)s added to the warehouse (%(category)s).") % {'part': item.part_name, 'category': item.get_category_display()})
        return redirect('inventory_list')

    all_items = InventoryItem.objects.all()
    items = all_items.annotate(stock_value=STOCK_VALUE).order_by('part_name')
    if filter_type == 'LOW_STOCK':
        items = items.filter(quantity__lte=F('reorder_level'))
    if category_filter in CATEGORY_CODES:
        items = items.filter(category=category_filter)
    if query:
        items = items.filter(Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(location__icontains=query))

    counts = all_items.aggregate(
        ALL=Count('id'),
        LOW_STOCK=Count('id', filter=Q(quantity__lte=F('reorder_level'))),
        GENERAL=Count('id', filter=Q(category='General')),
    )
    by_cat = dict(all_items.values_list('category').annotate(n=Count('id')))
    return render(request, 'tracker/inventory_list.html', {
        'items': items,
        'counts': counts,
        'total_items': items.count(),
        'total_warehouse_value': items.aggregate(v=Sum(STOCK_VALUE))['v'] or 0,
        'query': query,
        'filter_type': filter_type,
        'category_filter': category_filter,
        'categories': [(code, label, by_cat.get(code, 0)) for code, label in PART_CATEGORIES],
    })


@transaction.atomic
def auto_categorise(request):
    """Sort parts still marked 'General' into categories using keyword rules. Runs only when asked."""
    if request.method == 'POST':
        changed = 0
        uncategorised = InventoryItem.objects.filter(category='General')
        total = uncategorised.count()
        for item in uncategorised:
            guess = guess_category(item.part_name, item.part_code)
            if guess != 'General':
                item.category = guess
                item.save(update_fields=['category'])
                changed += 1
        messages.success(
            request,
            _("Sorted %(changed)s of %(total)s uncategorised parts. %(rest)s stay in General Hardware — you can change any part from its page.")
            % {'changed': changed, 'total': total, 'rest': total - changed}
        )
    return redirect('inventory_list')


def part_detail(request, item_id):
    """Everything about one part: stock, which orders used it, purchase history, suppliers, prices."""
    item = get_object_or_404(InventoryItem, id=item_id)
    order_lines = (item.orderitem_set.select_related('order', 'order__customer')
                   .order_by('-order__issue_date', '-id'))
    po_lines = (PurchaseOrderItem.objects.filter(inventory_item=item)
                .select_related('purchase_order', 'purchase_order__supplier')
                .order_by('-purchase_order__issue_date'))
    price_q = Q(part_name__iexact=item.part_name)
    if item.part_code:
        price_q |= Q(part_code__iexact=item.part_code)
    price_records = PriceRecord.objects.filter(price_q).order_by('-date_recorded')[:20]
    pricelist_q = Q(part_name__iexact=item.part_name)
    if item.part_code:
        pricelist_q |= Q(part_code__iexact=item.part_code)
    pricelist = MasterPricelistItem.objects.filter(pricelist_q).first()

    suppliers = {}
    for line in po_lines:
        s = line.purchase_order.supplier
        entry = suppliers.setdefault(s.id, {'supplier': s, 'qty': 0, 'last_cost': line.unit_cost, 'last_date': line.purchase_order.issue_date})
        entry['qty'] += line.quantity

    clients = (order_lines.exclude(order__customer__isnull=True)
               .values('order__customer__id', 'order__customer__name')
               .annotate(qty=Sum('quantity'), orders=Count('order', distinct=True))
               .order_by('-qty')[:6])

    return render(request, 'tracker/part_detail.html', {
        'item': item,
        'order_lines': order_lines[:25],
        'units_sold': order_lines.aggregate(q=Sum('quantity'))['q'] or 0,
        'po_lines': po_lines[:15],
        'suppliers': suppliers.values(),
        'clients': clients,
        'price_records': price_records,
        'pricelist': pricelist,
        'categories': PART_CATEGORIES,
    })


def client_pricelist(request):
    query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', 'ALL')

    items = InventoryItem.objects.all().order_by('category', 'part_name')

    if category_filter in CATEGORY_CODES:
        items = items.filter(category=category_filter)

    if query:
        items = items.filter(
            Q(part_name__icontains=query) |
            Q(part_code__icontains=query) |
            Q(category__icontains=query)
        )

    by_cat = dict(InventoryItem.objects.values_list('category').annotate(n=Count('id')))
    return render(request, 'tracker/client_pricelist.html', {
        'items': items,
        'query': query,
        'category_filter': category_filter,
        'categories': [(code, label, by_cat.get(code, 0)) for code, label in PART_CATEGORIES if by_cat.get(code)],
        'today': timezone.localdate(),
    })


@transaction.atomic
def adjust_stock(request, item_id, action):
    if request.method == 'POST':
        item = get_object_or_404(InventoryItem, id=item_id)
        if action == 'increase':
            item.quantity += 1
        elif action == 'decrease' and item.quantity > 0:
            item.quantity -= 1
        item.save()
    return redirect_back(request, 'inventory_list')


@transaction.atomic
def edit_inventory_item(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    if request.method == 'POST':
        item.part_name = request.POST.get('part_name', item.part_name).strip() or item.part_name
        item.part_code = request.POST.get('part_code', item.part_code)
        item.quantity = to_int(request.POST.get('quantity'), item.quantity, 0)
        item.reorder_level = to_int(request.POST.get('reorder_level'), item.reorder_level, 0)
        item.location = request.POST.get('location', item.location)
        item.unit_cost = to_decimal(request.POST.get('unit_cost'), default=item.unit_cost, minimum=0)
        category = request.POST.get('category')
        if category in CATEGORY_CODES:
            item.category = category
        item.save()
        messages.success(request, _("%(part)s saved.") % {'part': item.part_name})
        return redirect('part_detail', item_id=item.id)
    return render(request, 'tracker/inventory_edit.html', {'item': item, 'categories': PART_CATEGORIES})


@transaction.atomic
def delete_inventory_item(request, item_id):
    if request.method == 'POST':
        InventoryItem.objects.filter(id=item_id).delete()
        messages.success(request, _("Part deleted."))
    return redirect('inventory_list')


# ==========================================
# CLIENTS & SEARCH
# ==========================================

def client_list(request):
    query = request.GET.get('q', '').strip()
    clients = Customer.objects.annotate(
        invoice_count=Count('invoice', filter=Q(invoice__status__in=INVOICE_STATUSES)),
        order_count=Count('invoice', filter=Q(invoice__status__in=ORDER_STATUSES)),
        paid_total=Sum('invoice__total_amount', filter=Q(invoice__status='PAID')),
        open_total=Sum('invoice__total_amount', filter=Q(invoice__status__in=['UNPAID', 'OVERDUE'])),
        last_activity=Max('invoice__issue_date'),
    ).order_by('name')
    if query:
        clients = clients.filter(name__icontains=query)
    return render(request, 'tracker/client_list.html', {'clients': clients, 'query': query})


def global_search(request):
    query = request.GET.get('q', '').strip()
    orders = invoices = inventory = clients = suppliers = pos = []

    if query:
        all_docs = Invoice.objects.filter(
            Q(invoice_number__icontains=query) | Q(customer__name__icontains=query)
        ).select_related('customer').order_by('-issue_date')

        orders = all_docs.filter(status__in=ORDER_STATUSES)
        invoices = all_docs.filter(status__in=['UNPAID', 'PAID', 'OVERDUE', 'DRAFT', 'VOID'])

        inventory = InventoryItem.objects.filter(
            Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(location__icontains=query)
        ).order_by('part_name')

        clients = Customer.objects.filter(name__icontains=query).order_by('name')
        suppliers = Supplier.objects.filter(
            Q(name__icontains=query) | Q(contact_person__icontains=query) | Q(email__icontains=query)
        ).order_by('name')
        pos = PurchaseOrder.objects.filter(
            Q(po_number__icontains=query) | Q(supplier__name__icontains=query)
        ).select_related('supplier').order_by('-issue_date')

    results = {
        'orders': list(orders), 'invoices': list(invoices), 'inventory': list(inventory),
        'clients': list(clients), 'suppliers': list(suppliers), 'pos': list(pos),
    }
    return render(request, 'tracker/search_results.html', {
        'query': query,
        'search_query': query,
        'total_hits': sum(len(v) for v in results.values()),
        **results,
    })


def research_hub(request):
    """Analytics: best-selling parts, best clients, stock by category, plus a parts lookup."""
    query = request.GET.get('q', '').strip()

    all_parts = InventoryItem.objects.all().order_by('part_name')
    if query:
        all_parts = all_parts.filter(
            Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(category__icontains=query)
        )

    top_parts_qs = (
        OrderItem.objects.filter(inventory_item__isnull=False)
        .values('inventory_item__part_name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:6]
    )
    top_clients_qs = (
        Customer.objects.annotate(
            total_spent=Sum('invoice__total_amount', filter=~Q(invoice__status='DRAFT'))
        )
        .filter(total_spent__gt=0)
        .order_by('-total_spent')[:6]
    )
    labels = dict(PART_CATEGORIES)
    by_category = [(labels.get(c['category'], c['category']), float(c['value'] or 0))
                   for c in InventoryItem.objects.values('category').annotate(value=Sum(STOCK_VALUE)).order_by('-value')]
    by_category = [c for c in by_category if c[1] > 0]
    if len(by_category) > 6:  # top 5 + "Other" so every slice gets its own colour
        by_category = by_category[:5] + [('Other', sum(v for _l, v in by_category[5:]))]

    context = {
        'query': query,
        'parts': all_parts[:100],
        'parts_total': all_parts.count(),
        'total_catalog_items': InventoryItem.objects.count(),
        'total_clients': Customer.objects.count(),
        'total_orders_logged': Invoice.objects.exclude(status='DRAFT').count(),
        'total_suppliers': Supplier.objects.count(),
        'chart_data': {
            'parts': {'labels': [p['inventory_item__part_name'] for p in top_parts_qs],
                      'values': [p['total_qty'] for p in top_parts_qs]},
            'clients': {'labels': [c.name for c in top_clients_qs],
                        'values': [float(c.total_spent or 0) for c in top_clients_qs]},
            'categories': {'labels': [label for label, _v in by_category],
                           'values': [value for _l, value in by_category]},
        },
    }
    return render(request, 'tracker/research.html', context)


# ==========================================
# PURCHASING & SUPPLIER MODULE
# ==========================================

def supplier_list(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            s = Supplier.objects.create(
                name=name,
                contact_person=request.POST.get('contact_person', '').strip(),
                email=request.POST.get('email', '').strip(),
                phone=request.POST.get('phone', '').strip(),
            )
            messages.success(request, _("Supplier %(name)s added.") % {'name': s.name})
            return redirect('supplier_detail', supplier_id=s.id)
        return redirect('supplier_list')

    suppliers = Supplier.objects.annotate(
        po_count=Count('purchaseorder'),
        po_total=Sum('purchaseorder__total_amount'),
        last_po=Max('purchaseorder__issue_date'),
    ).order_by('name')
    return render(request, 'tracker/supplier_list.html', {'suppliers': suppliers})


def supplier_detail(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    if request.method == 'POST':
        supplier.name = request.POST.get('name', '').strip() or supplier.name
        supplier.contact_person = request.POST.get('contact_person', '').strip()
        supplier.email = request.POST.get('email', '').strip()
        supplier.phone = request.POST.get('phone', '').strip()
        supplier.save()
        messages.success(request, _("Supplier details saved."))
        return redirect('supplier_detail', supplier_id=supplier.id)

    pos = supplier.purchaseorder_set.annotate(line_count=Count('items')).order_by('-issue_date', '-id')
    parts = (PurchaseOrderItem.objects.filter(purchase_order__supplier=supplier, inventory_item__isnull=False)
             .values('inventory_item__id', 'inventory_item__part_name', 'inventory_item__part_code', 'inventory_item__quantity')
             .annotate(qty=Sum('quantity'), last_cost=Max('unit_cost'), last_date=Max('purchase_order__issue_date'))
             .order_by('-last_date'))
    prices = PriceRecord.objects.filter(supplier_or_client_name__iexact=supplier.name).order_by('-date_recorded')[:15]
    return render(request, 'tracker/supplier_detail.html', {
        'supplier': supplier,
        'pos': pos,
        'parts': parts,
        'prices': prices,
        'po_total': pos.aggregate(t=Sum('total_amount'))['t'] or 0,
        'open_count': pos.exclude(status='RECEIVED').count(),
    })


def po_list(request):
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier_id')
        po_number = request.POST.get('po_number', '').strip() or f"PO-{random.randint(1000, 9999)}"
        if supplier_id:
            supplier = get_object_or_404(Supplier, id=supplier_id)
            po = PurchaseOrder.objects.create(po_number=po_number, supplier=supplier, status='DRAFT')
            messages.success(request, _("%(n)s created — add the parts you need.") % {'n': po.po_number})
            return redirect('po_detail', po_id=po.id)
        messages.error(request, _("Choose a supplier first."))
        return redirect('po_list')

    status = request.GET.get('status', 'ALL').upper()
    pos = PurchaseOrder.objects.select_related('supplier').annotate(line_count=Count('items')).order_by('-issue_date', '-id')
    if status == 'OPEN':
        pos = pos.exclude(status='RECEIVED')
    elif status == 'RECEIVED':
        pos = pos.filter(status='RECEIVED')
    counts = PurchaseOrder.objects.aggregate(
        ALL=Count('id'), OPEN=Count('id', filter=~Q(status='RECEIVED')), RECEIVED=Count('id', filter=Q(status='RECEIVED')),
    )
    suppliers = Supplier.objects.all().order_by('name')
    return render(request, 'tracker/po_list.html', {
        'pos': pos, 'suppliers': suppliers, 'status_filter': status, 'counts': counts,
        'preset_supplier': request.GET.get('supplier', ''),
    })


@transaction.atomic
def po_detail(request, po_id):
    po = get_object_or_404(PurchaseOrder.objects.select_related('supplier'), id=po_id)

    if request.method == 'POST':
        if 'add_item' in request.POST and po.status != 'RECEIVED':
            inv_id = request.POST.get('inventory_id')
            qty = to_int(request.POST.get('quantity'), 1, 1)
            cost = to_decimal(request.POST.get('unit_cost'), minimum=0)
            if inv_id:
                inv_item = get_object_or_404(InventoryItem, id=inv_id)
                PurchaseOrderItem.objects.create(
                    purchase_order=po, inventory_item=inv_item, quantity=qty, unit_cost=cost
                )
                po.total_amount = sum(item.total_cost for item in po.items.all())
                po.save()
            else:
                messages.error(request, _("Pick a part to add."))

        elif 'receive_po' in request.POST:
            if po.status != 'RECEIVED':
                for item in po.items.all():
                    if item.inventory_item:
                        # Auto-add quantity to warehouse stock & update cost!
                        item.inventory_item.quantity += item.quantity
                        item.inventory_item.unit_cost = item.unit_cost
                        item.inventory_item.save()
                po.status = 'RECEIVED'
                po.save()
                messages.success(request, _("%(n)s received — warehouse stock updated.") % {'n': po.po_number})
        return redirect('po_detail', po_id=po.id)

    return render(request, 'tracker/po_detail.html', {
        'po': po,
        'items': po.items.select_related('inventory_item').order_by('id'),
        'parts': parts_json(),
    })


@transaction.atomic
def delete_po(request, po_id):
    if request.method == 'POST':
        po = get_object_or_404(PurchaseOrder, id=po_id)
        number = po.po_number
        po.delete()
        messages.success(request, _("%(n)s deleted.") % {'n': number})
    return redirect('po_list')


@transaction.atomic
def delete_po_item(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(PurchaseOrderItem, id=item_id)
        po = item.purchase_order
        item.delete()
        po.total_amount = sum(i.total_cost for i in po.items.all())
        po.save()
        return redirect('po_detail', po_id=po.id)
    return redirect('po_list')
