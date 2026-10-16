import random
import re
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from django.contrib import messages
from django.utils.translation import gettext as _
from django.db import transaction
from core.utils import to_decimal, to_int, redirect_back
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Sum, Count, Avg, Max
from django.utils import timezone

from .models import Invoice, PriceRecord, MasterPricelistItem, ClientFinancialProfile
from tracker.models import Customer, InventoryItem, OrderItem, PART_CATEGORIES, guess_category
from tracker.views import parts_json, related_document, ORDER_STATUSES, INVOICE_STATUSES
from tracker.stock import log_activity
from django.urls import reverse

STATUS_CODES = {code for code, _label in Invoice.STATUS_CHOICES}


def finance_dashboard(request):
    """Invoices workspace: totals plus a filterable, searchable invoice list."""
    status_filter = request.GET.get('status', 'ALL').upper()
    query = request.GET.get('q', '').strip()
    today = timezone.localdate()

    invoices = Invoice.objects.filter(status__in=INVOICE_STATUSES + ['VOID']).select_related('customer')
    totals = invoices.aggregate(
        paid=Sum('total_amount', filter=Q(status='PAID')),
        unpaid=Sum('total_amount', filter=Q(status='UNPAID')),
        overdue=Sum('total_amount', filter=Q(status='OVERDUE')),
        n_all=Count('id', filter=Q(status__in=INVOICE_STATUSES)),
        n_unpaid=Count('id', filter=Q(status='UNPAID')),
        n_overdue=Count('id', filter=Q(status='OVERDUE')),
        n_paid=Count('id', filter=Q(status='PAID')),
        n_past_due=Count('id', filter=Q(status='UNPAID', due_date__lt=today)),
    )

    listing = invoices.order_by('-issue_date', '-id')
    if status_filter in INVOICE_STATUSES:
        listing = listing.filter(status=status_filter)
    else:
        status_filter = 'ALL'
        listing = listing.filter(status__in=INVOICE_STATUSES)
    if query:
        listing = listing.filter(Q(invoice_number__icontains=query) | Q(customer__name__icontains=query))

    return render(request, 'finance/dashboard.html', {
        'invoices': listing[:100],
        'shown_total': listing.aggregate(t=Sum('total_amount'))['t'] or 0,
        'listing_count': listing.count(),
        'totals': totals,
        'status_filter': status_filter,
        'query': query,
        'today': today,
    })


def client_ledger(request, client_id):
    """One client: money, orders, invoices, what they buy, prices and account settings."""
    client = get_object_or_404(Customer, id=client_id)
    profile, _created = ClientFinancialProfile.objects.get_or_create(customer=client)

    if request.method == 'POST' and 'update_profile' in request.POST:
        rating = request.POST.get('internal_rating', profile.internal_rating)
        if rating in ClientFinancialProfile.RATING_LABELS:
            profile.internal_rating = rating
        profile.payment_terms_days = to_int(request.POST.get('payment_terms_days'), 30, 0)
        profile.negotiation_notes = request.POST.get('negotiation_notes', '')
        profile.save()
        messages.success(request, _("Client settings saved."))
        return redirect('finance:client_ledger', client_id=client.id)

    docs = Invoice.objects.filter(customer=client).order_by('-issue_date', '-id')
    invoices = docs.filter(status__in=INVOICE_STATUSES + ['DRAFT', 'VOID'])
    orders = docs.filter(status__in=ORDER_STATUSES)

    money = docs.aggregate(
        paid=Sum('total_amount', filter=Q(status='PAID')),
        outstanding=Sum('total_amount', filter=Q(status__in=['UNPAID', 'OVERDUE'])),
        overdue=Sum('total_amount', filter=Q(status='OVERDUE')),
        last=Max('issue_date'),
    )
    profile.lifetime_revenue = money['paid'] or 0
    profile.save(update_fields=['lifetime_revenue'])

    yearly_data = (
        invoices.values('issue_date__year')
        .annotate(count=Count('id'), total=Sum('total_amount'), paid=Sum('total_amount', filter=Q(status='PAID')))
        .order_by('-issue_date__year')
    )

    top_parts = (
        OrderItem.objects.filter(order__customer=client)
        .values('inventory_item_id', 'description')
        .annotate(qty=Sum('quantity'), lines=Count('id'), avg_price=Avg('unit_price'))
        .order_by('-qty')[:8]
    )

    price_history = PriceRecord.objects.filter(
        Q(customer=client) | Q(supplier_or_client_name__iexact=client.name)
    ).order_by('-date_recorded')[:10]

    return render(request, 'finance/client_ledger.html', {
        'client': client,
        'profile': profile,
        'rating_label': ClientFinancialProfile.RATING_LABELS.get(profile.internal_rating, profile.internal_rating),
        'rating_choices': ClientFinancialProfile.RATING_LABELS.items(),
        'invoices': invoices,
        'orders': orders,
        'money': money,
        'doc_count': docs.count(),
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
        if status not in INVOICE_STATUSES:
            status = 'UNPAID'
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
            customer, _created = Customer.objects.get_or_create(name=customer_name)
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
            quantity = to_int(request.POST.get('quantity'), 1, 1)
            unit_price = request.POST.get('unit_price')

            if inventory_id or custom_desc:
                if inventory_id:
                    inv_item = InventoryItem.objects.filter(id=inventory_id).first()
                    desc = custom_desc or (f"{inv_item.part_name} ({inv_item.part_code})" if inv_item and inv_item.part_code else (inv_item.part_name if inv_item else 'Item'))
                    price = to_decimal(unit_price, default=(inv_item.unit_cost if inv_item else 0), minimum=0)
                else:
                    inv_item = None
                    desc = custom_desc
                    price = to_decimal(unit_price, minimum=0)

                OrderItem.objects.create(
                    order=invoice,
                    inventory_item=inv_item,
                    description=desc,
                    quantity=quantity,
                    unit_price=price
                )
                invoice.total_amount = sum(item.total_price for item in invoice.order_items.all())
                invoice.save()

            log_activity(request, 'invoice_created', invoice.invoice_number, reverse('finance:invoice_detail', args=[invoice.id]))
            messages.success(request, _("Invoice %(n)s created.") % {'n': invoice.invoice_number})
            return redirect('finance:invoice_detail', invoice_id=invoice.id)
        messages.error(request, _("Please enter a client or vessel name."))

    today = timezone.localdate()
    return render(request, 'finance/invoice_form.html', {
        'parts': parts_json(),
        'customers': Customer.objects.order_by('name').values_list('name', flat=True),
        'today': today,
        'default_due': today + timedelta(days=30),
        'preset_client': request.GET.get('client', ''),
    })


def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(Invoice.objects.select_related('customer', 'supplier'), id=invoice_id)
    return render(request, 'finance/invoice_detail.html', {
        'invoice': invoice,
        'items': invoice.order_items.select_related('inventory_item').order_by('id'),
        'parts': parts_json(),
        'related': related_document(invoice),
        'status_choices': Invoice.STATUS_CHOICES,
        'payment_statuses': INVOICE_STATUSES,
        'today': timezone.localdate(),
    })


def add_invoice_item(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        inventory_id = request.POST.get('inventory_id')
        quantity = to_int(request.POST.get('quantity'), 1, 1)
        custom_price = request.POST.get('unit_price')
        custom_desc = request.POST.get('description', '').strip()

        if inventory_id:
            inv_item = InventoryItem.objects.filter(id=inventory_id).first()
            desc = custom_desc or (f"{inv_item.part_name} ({inv_item.part_code})" if inv_item and inv_item.part_code else (inv_item.part_name if inv_item else 'Item'))
            unit_price = to_decimal(custom_price, default=(inv_item.unit_cost if inv_item else 0), minimum=0)
        else:
            inv_item = None
            desc = custom_desc or 'Billed Item / Service'
            unit_price = to_decimal(custom_price, minimum=0)

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
    return redirect('finance:dashboard')


def delete_invoice(request, invoice_id):
    """Delete an invoice and return to the client page."""
    if request.method == 'POST':
        invoice = get_object_or_404(Invoice, id=invoice_id)
        client_id = invoice.customer.id if invoice.customer else None
        number = invoice.invoice_number
        invoice.delete()
        log_activity(request, 'invoice_deleted', number)
        messages.success(request, _("%(n)s deleted.") % {'n': number})
        if client_id and request.POST.get('next') == 'client':
            return redirect('finance:client_ledger', client_id=client_id)
    return redirect('finance:dashboard')


def update_invoice_details(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        status = request.POST.get('status', invoice.status)
        if status in STATUS_CODES:
            invoice.status = status
        invoice.google_drive_url = request.POST.get('google_drive_url', invoice.google_drive_url or '').strip()
        raw_due_date = request.POST.get('due_date')
        if raw_due_date:
            try:
                invoice.due_date = date.fromisoformat(raw_due_date)
            except ValueError:
                pass
        invoice.save()
        log_activity(request, 'invoice_updated', f'{invoice.invoice_number} · {invoice.get_status_display()}', reverse('finance:invoice_detail', args=[invoice.id]))
        messages.success(request, _("%(n)s updated.") % {'n': invoice.invoice_number})
    return redirect('finance:invoice_detail', invoice_id=invoice.id)


def edit_invoice(request, invoice_id):
    return redirect('finance:invoice_detail', invoice_id=invoice_id)


DRIVE_URL = re.compile(r'https?://(?:drive|docs)\.google\.com/\S+')
DOC_NUMBER = re.compile(r'\b(?:INV|ORD)-[\w-]+\b', re.IGNORECASE)


@transaction.atomic
def bulk_import(request):
    """Attach Google Drive PDF links to invoices/orders.
    Each pasted line needs a Drive link plus the document number, e.g.  INV-1042 https://drive.google.com/...
    Lines without a matching number are listed so they can be attached by hand."""
    results = []
    if request.method == 'POST':
        overwrite = request.POST.get('overwrite') == '1'
        for raw_line in request.POST.get('raw_data', '').splitlines():
            line = raw_line.strip()
            if not line:
                continue
            url_match = DRIVE_URL.search(line)
            if not url_match:
                results.append({'line': line, 'outcome': 'skipped', 'note': _('No Google Drive link on this line')})
                continue
            url = url_match.group(0)
            number_match = DOC_NUMBER.search(line.replace(url, ' '))
            doc = Invoice.objects.filter(invoice_number__iexact=number_match.group(0)).first() if number_match else None
            if not doc:
                note = (_("No invoice or order numbered %(n)s") % {'n': number_match.group(0)}) if number_match else _("No INV-/ORD- number on this line")
                results.append({'line': line, 'outcome': 'unmatched', 'note': note})
            elif doc.google_drive_url and doc.google_drive_url != url and not overwrite:
                results.append({'line': line, 'outcome': 'kept', 'doc': doc, 'note': _('Already has a different link (kept)')})
            else:
                doc.google_drive_url = url
                doc.save(update_fields=['google_drive_url'])
                results.append({'line': line, 'outcome': 'attached', 'doc': doc, 'note': _('Link attached')})
        attached = sum(1 for r in results if r['outcome'] == 'attached')
        messages.success(request, _("Attached %(done)s of %(total)s links.") % {'done': attached, 'total': len(results)})

    return render(request, 'finance/bulk_import.html', {
        'results': results,
        'missing_links': Invoice.objects.exclude(status='DRAFT').filter(Q(google_drive_url='') | Q(google_drive_url__isnull=True))
                                 .select_related('customer').order_by('-issue_date')[:12],
    })


def pricelist_dashboard(request):
    if request.method == 'POST':
        name = request.POST.get('part_name', '').strip()
        if name:
            category = request.POST.get('category', '')
            availability = request.POST.get('availability', 'In Stock')
            item = MasterPricelistItem.objects.create(
                part_name=name,
                part_code=request.POST.get('part_code', '').strip(),
                brand=request.POST.get('brand', '').strip(),
                category=category if category in dict(PART_CATEGORIES) else guess_category(name, request.POST.get('part_code', '')),
                cost_price=to_decimal(request.POST.get('cost_price'), minimum=0),
                markup_percent=to_decimal(request.POST.get('markup_percent'), default='30', minimum=0),
                availability=availability if availability in dict(MasterPricelistItem.AVAILABILITY_CHOICES) else 'In Stock',
            )
            messages.success(request, _("%(part)s added at %(price)s €.") % {'part': item.part_name, 'price': item.client_price})
        return redirect('finance:pricelist_dashboard')

    query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', 'ALL')
    items = MasterPricelistItem.objects.all()
    if category_filter in dict(PART_CATEGORIES):
        items = items.filter(category=category_filter)
    if query:
        items = items.filter(Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(brand__icontains=query))

    # link each price-list line to the warehouse part with the same code or name (one query)
    rows = list(items)
    by_code, by_name = {}, {}
    matches = InventoryItem.objects.filter(
        Q(part_code__in=[i.part_code for i in rows if i.part_code]) | Q(part_name__in=[i.part_name for i in rows])
    )
    for part in matches:
        if part.part_code:
            by_code.setdefault(part.part_code.lower(), part)
        by_name.setdefault(part.part_name.lower(), part)
    for i in rows:
        i.stock_part = by_code.get((i.part_code or '').lower()) or by_name.get(i.part_name.lower())

    by_cat = dict(MasterPricelistItem.objects.values_list('category').annotate(n=Count('id')))
    return render(request, 'finance/pricelist.html', {
        'items': rows,
        'query': query,
        'category_filter': category_filter,
        'categories': [(code, label, by_cat.get(code, 0)) for code, label in PART_CATEGORIES],
        'availability_choices': MasterPricelistItem.AVAILABILITY_CHOICES,
    })


def price_history(request):
    if request.method == 'POST':
        part_name = request.POST.get('part_name', '').strip()
        party = request.POST.get('supplier_name', '').strip()
        if part_name and party:
            try:
                recorded = date.fromisoformat(request.POST.get('date_recorded', ''))
            except ValueError:
                recorded = timezone.localdate()
            currency = request.POST.get('currency', 'EUR')
            PriceRecord.objects.create(
                part_name=part_name,
                part_code=request.POST.get('part_code', '').strip(),
                supplier_or_client_name=party,
                customer=Customer.objects.filter(name__iexact=party).first(),
                unit_price=to_decimal(request.POST.get('unit_price'), minimum=0),
                currency=currency if currency in ('EUR', 'USD', 'GBP') else 'EUR',
                date_recorded=recorded,
                notes=request.POST.get('notes', '').strip(),
            )
            log_activity(request, 'price_logged', f'{part_name} · {party}', reverse('finance:price_history'))
            messages.success(request, _("Price for %(part)s logged.") % {'part': part_name})
        else:
            messages.error(request, _("Part name and supplier / client are required."))
        return redirect('finance:price_history')

    query = request.GET.get('q', '').strip()
    records = PriceRecord.objects.select_related('customer').order_by('-date_recorded', '-id')
    if query:
        records = records.filter(
            Q(part_name__icontains=query) | Q(part_code__icontains=query) | Q(supplier_or_client_name__icontains=query)
        )

    # Chart: price over time for the most-logged parts (up to 6 lines)
    top = list(records.values('part_name').annotate(n=Count('id')).order_by('-n')[:6].values_list('part_name', flat=True))
    points = records.filter(part_name__in=top).order_by('date_recorded').values_list('part_name', 'date_recorded', 'unit_price')
    dates = sorted({d for _p, d, _v in points})
    series = OrderedDict((name, {}) for name in top)
    for name, d, price in points:
        series[name][d] = float(price)
    chart = {
        'labels': [d.strftime('%d %b %Y') for d in dates],
        'series': [{'label': name, 'data': [vals.get(d) for d in dates]} for name, vals in series.items()],
    }

    # match each row to a warehouse part so it can link there
    part_lookup = {p.part_name.lower(): p.id for p in InventoryItem.objects.filter(part_name__in=records.values('part_name'))}
    rows = list(records[:200])
    for r in rows:
        r.part_id = part_lookup.get(r.part_name.lower())

    return render(request, 'finance/price_history.html', {
        'records': rows,
        'query': query,
        'total_records': records.count(),
        'unique_parts_count': records.values('part_name').distinct().count(),
        'party_count': records.values('supplier_or_client_name').distinct().count(),
        'chart': chart,
        'today': timezone.localdate(),
        'customers': Customer.objects.order_by('name').values_list('name', flat=True),
    })


def delete_price_record(request, record_id):
    if request.method == 'POST':
        get_object_or_404(PriceRecord, id=record_id).delete()
        messages.success(request, _("Price record deleted."))
    return redirect('finance:price_history')


def _csv_safe(value):
    """Stop spreadsheet formula injection: a cell starting with = + - @ would run as a formula in Excel."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@') else text


def export_finances(request):
    """Download every invoice/order as a CSV that opens cleanly in Excel (Greek-safe)."""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="marine-finances-{timezone.localdate().isoformat()}.csv"'
    response.write('﻿')  # BOM so Excel detects UTF-8
    writer = csv.writer(response)
    writer.writerow(['Number', 'Type', 'Client / Supplier', 'Status', 'Issue date', 'Due date', 'Total (EUR)'])

    invoices = Invoice.objects.select_related('customer', 'supplier').order_by('-issue_date', '-id')
    status = request.GET.get('status', '').upper()
    if status:
        invoices = invoices.filter(status=status)
    for inv in invoices:
        party = inv.customer.name if inv.customer_id else (inv.supplier.name if inv.supplier_id else '')
        writer.writerow([
            _csv_safe(inv.invoice_number), inv.invoice_type, _csv_safe(party), inv.status,
            inv.issue_date, inv.due_date or '', inv.total_amount,
        ])
    return response
