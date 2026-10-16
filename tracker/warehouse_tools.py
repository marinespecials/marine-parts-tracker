"""Warehouse tools: QR labels, the phone scan page, stock counts and the dead stock report."""
from datetime import timedelta
from urllib.parse import quote

import segno
from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from core.utils import to_int
from .models import InventoryItem, PART_CATEGORIES
from .stock import log_activity, move_stock, set_stock
from .views import STOCK_VALUE, CATEGORY_CODES


def qr_svg(url, scale=3):
    """QR code drawn on the server (no outside QR service needed)."""
    return mark_safe(segno.make(url, error='m').svg_inline(scale=scale, border=1, dark='#000', light='#fff'))


def _locations():
    return list(InventoryItem.objects.order_by('location').values_list('location', flat=True).distinct())


def print_labels(request):
    kind = request.GET.get('kind', 'parts')
    category = request.GET.get('category', 'ALL')
    location = request.GET.get('location', 'ALL')
    query = request.GET.get('q', '').strip()
    labels = []
    if kind == 'shelves':
        shelves = InventoryItem.objects.values('location').order_by('location').distinct()
        if location != 'ALL':
            shelves = shelves.filter(location=location)
        for row in shelves:
            url = request.build_absolute_uri(reverse('stock_count')) + '?location=' + quote(row['location'])
            n = InventoryItem.objects.filter(location=row['location']).count()
            labels.append({'title': row['location'], 'sub': _('%(n)s parts · scan to count') % {'n': n}, 'qr': qr_svg(url)})
    else:
        items = InventoryItem.objects.order_by('location', 'part_name')
        if category in CATEGORY_CODES:
            items = items.filter(category=category)
        if location != 'ALL':
            items = items.filter(location=location)
        if query:
            items = items.filter(Q(part_name__icontains=query) | Q(part_code__icontains=query))
        for item in items[:300]:
            url = request.build_absolute_uri(reverse('scan_part', args=[item.id]))
            labels.append({'title': item.part_name, 'sub': item.part_code or '', 'meta': item.location, 'qr': qr_svg(url)})
    return render(request, 'tracker/labels.html', {
        'labels': labels, 'kind': kind, 'category': category, 'location': location, 'query': query,
        'categories': PART_CATEGORIES, 'locations': _locations(),
    })


@transaction.atomic
def scan_part(request, item_id):
    """What a phone opens after scanning a part label: quick +/- and 'set counted quantity'."""
    item = get_object_or_404(InventoryItem, id=item_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        note = request.POST.get('note', '').strip()
        if action in ('plus', 'minus'):
            amount = to_int(request.POST.get('amount'), 1, 1)
            changed = move_stock(item, amount if action == 'plus' else -amount, 'ADJUST', request, note)
            messages.success(request, _("Stock is now %(q)s (%(c)+d).") % {'q': item.quantity, 'c': changed})
        elif action == 'count':
            counted = to_int(request.POST.get('counted'), item.quantity, 0)
            diff = set_stock(item, counted, 'COUNT', request, note, always_log=True)
            messages.success(request, _("Counted %(q)s (difference %(c)+d).") % {'q': item.quantity, 'c': diff})
        return redirect('scan_part', item_id=item.id)
    return render(request, 'tracker/scan_part.html', {
        'item': item,
        'movements': item.movements.select_related('user')[:5],
        'last_count': item.movements.filter(reason='COUNT').first(),
    })


@transaction.atomic
def stock_count(request):
    """Walk a shelf, type what you actually find; the app shows and records the differences."""
    location = request.GET.get('location') or request.POST.get('location') or ''
    items = InventoryItem.objects.order_by('part_name')
    if location and location != 'ALL':
        items = items.filter(location=location)
    results = None
    if request.method == 'POST':
        results = []
        for item in items:
            raw = request.POST.get(f'count_{item.id}', '').strip()
            if raw == '':
                continue
            expected = item.quantity
            counted = to_int(raw, expected, 0)
            set_stock(item, counted, 'COUNT', request, _('Shelf count: %(l)s') % {'l': location or _('all')}, always_log=True)
            results.append({'item': item, 'expected': expected, 'counted': counted, 'diff': counted - expected})
        differences = sum(1 for r in results if r['diff'])
        log_activity(request, 'stock_count', f"{location or _('all')}: {len(results)} / {differences}",
                     reverse('stock_count') + (f'?location={quote(location)}' if location else ''))
        messages.success(request, _("Counted %(n)s parts — %(d)s differences recorded.") % {'n': len(results), 'd': differences})
        results.sort(key=lambda r: (r['diff'] == 0, -abs(r['diff'])))
    last_counts = {}
    if location:
        from .models import StockMovement
        for m in StockMovement.objects.filter(reason='COUNT', item__in=items).values('item_id').annotate(last=Max('created_at')):
            last_counts[m['item_id']] = m['last']
    rows = [{'item': i, 'last': last_counts.get(i.id)} for i in items] if location else []
    return render(request, 'tracker/stock_count.html', {
        'location': location, 'locations': _locations(), 'rows': rows, 'results': results,
    })


def dead_stock(request):
    """Parts with stock that haven't sold in N months — the clean-out list."""
    months = to_int(request.GET.get('months'), 12, 1)
    if months not in (6, 12, 24):
        months = 12
    cutoff = timezone.localdate() - timedelta(days=round(30.4 * months))
    items = (InventoryItem.objects.filter(quantity__gt=0)
             .annotate(last_sold=Max('orderitem__order__issue_date'), stock_value=STOCK_VALUE)
             .filter(Q(last_sold__isnull=True) | Q(last_sold__lt=cutoff))
             .order_by('-stock_value', 'part_name'))
    return render(request, 'tracker/dead_stock.html', {
        'items': items,
        'months': months,
        'total_value': items.aggregate(v=Sum(STOCK_VALUE))['v'] or 0,
        'never_sold': sum(1 for i in items if i.last_sold is None),
    })
