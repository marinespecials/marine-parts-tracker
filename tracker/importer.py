"""Excel / CSV import of warehouse items and clients (e.g. an export from the ERP).

Rules (agreed with the business):
- Nothing is ever deleted.
- Existing items are matched by part code (or exact name when there is no code). Their details and
  prices are updated, but their STOCK QUANTITY IS KEPT — the app's stock is maintained by orders/counts.
- New items get the quantity from the file (recorded in the stock history as 'New part').
- Clients are matched by ΑΦΜ, then ERP code, then exact name. Empty cells never wipe existing data.
"""
import csv
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (PART_CATEGORIES, Customer, InventoryItem, StockMovement, Supplier, SupplierPrice,
                     guess_category)

MAX_ROWS = 20000

# field -> (label, header keywords). Order = matching priority (specific fields first).
FIELDS = {
    'items': [
        ('part_code', _('Part code'), ['κωδικ', 'κωδ.', 'code', 'sku', 'part no', 'part number', 'p/n', 'item no']),
        ('unit_cost', _('Cost price'), ['τιμη αγορ', 'αγορ', 'κοστ', 'cost', 'purchase', 'buy']),
        ('sale_price', _('Selling price'), ['τιμη πωλ', 'πωλ', 'λιαν', 'χονδρ', 'sale', 'sell', 'retail', 'τιμη', 'price']),
        ('quantity', _('Quantity in stock'), ['υπολοιπ', 'αποθεμ', 'ποσοτ', 'διαθεσ', 'stock', 'qty', 'quantity', 'balance', 'on hand']),
        ('reorder_level', _('Reorder level'), ['ελαχ', 'reorder', 'min', 'ασφαλ']),
        ('location', _('Location / bin'), ['θεση', 'ραφι', 'αποθηκ', 'location', 'bin', 'shelf', 'warehouse']),
        ('category', _('Category'), ['κατηγορ', 'ομαδα', 'category', 'group', 'family']),
        ('supplier', _('Supplier'), ['προμηθευτ', 'supplier', 'vendor']),
        ('part_name', _('Part name / description'), ['περιγραφ', 'ονομα', 'ειδος', 'description', 'name', 'item', 'title']),
    ],
    'clients': [
        ('tax_id', _('Tax ID (ΑΦΜ)'), ['αφμ', 'α.φ.μ', 'vat', 'tax id', 'afm', 'tin']),
        ('tax_office', _('Tax office (ΔΟΥ)'), ['δου', 'δ.ο.υ', 'tax office', 'doy']),
        ('code', _('ERP code'), ['κωδικ', 'κωδ.', 'code']),
        ('email', _('Email'), ['email', 'e-mail', 'mail']),
        ('phone', _('Phone'), ['τηλ', 'κινητ', 'phone', 'mobile', 'tel']),
        ('address', _('Address'), ['διευθυνσ', 'οδος', 'address', 'street']),
        ('city', _('City'), ['πολη', 'περιοχ', 'city', 'town']),
        ('name', _('Client name'), ['επωνυμ', 'ονομ', 'πελατ', 'name', 'company', 'customer']),
    ],
}
REQUIRED = {'items': ('part_name', 'part_code'), 'clients': ('name',)}  # items need a name or a code


def norm(text):
    text = unicodedata.normalize('NFD', str(text or '')).lower()
    return ''.join(c for c in text if not unicodedata.combining(c)).strip()


def cell_text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 12345.0 from Excel -> "12345"
    return str(value).strip()


def cell_decimal(value):
    """Number from a cell, or None when empty/unreadable. Accepts 12,50 and 1.234,50."""
    if value is None or value == '':
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal('0.01'))
    text = str(value).strip().replace('€', '').replace(' ', '')
    if not text:
        return None
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.') if text.rfind(',') > text.rfind('.') else text.replace(',', '')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number.quantize(Decimal('0.01')) if number.is_finite() else None


def cell_int(value):
    number = cell_decimal(value)
    return None if number is None else max(0, int(round(number)))


# ---------------------------------------------------------------- reading files

class Rows(list):
    """Data rows plus the Excel line number of the first one (so 'Row 7' matches Excel)."""
    first_line = 2

def read_table(path):
    """Return (headers, rows) from .xlsx or .csv. Finds the header row automatically."""
    if str(path).lower().endswith('.csv'):
        raw = open(path, 'rb').read()
        for enc in ('utf-8-sig', 'cp1253', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=';,\t') if text.strip() else csv.excel
        grid = [row for row in csv.reader(io.StringIO(text), dialect)]
    else:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        grid = [list(row) for row in ws.iter_rows(values_only=True)]
        wb.close()
    first_line_of = [n for n, row in enumerate(grid, start=1) if any(cell_text(c) for c in row)]
    grid = [row for row in grid if any(cell_text(c) for c in row)]
    if not grid:
        return [], []
    keywords = {kw for kind in FIELDS.values() for _f, _l, kws in kind for kw in kws}
    header_index = 0
    for i, row in enumerate(grid[:15]):
        texts = [norm(c) for c in row if cell_text(c) and not isinstance(c, (int, float))]
        if len(texts) >= 2 and any(kw in t for t in texts for kw in keywords):
            header_index = i
            break
    headers = [cell_text(h) or f'#{n + 1}' for n, h in enumerate(grid[header_index])]
    rows = Rows(list(r) + [None] * (len(headers) - len(r)) for r in grid[header_index + 1:header_index + 1 + MAX_ROWS])
    rows.first_line = first_line_of[header_index] + 1
    return headers, rows


def guess_mapping(headers, kind):
    """{field: column index} from the header names."""
    mapping, taken = {}, set()
    normed = [norm(h) for h in headers]
    for field, _label, keywords in FIELDS[kind]:
        for kw in keywords:
            hit = next((i for i, h in enumerate(normed) if i not in taken and kw in h), None)
            if hit is not None:
                mapping[field] = hit
                taken.add(hit)
                break
    return mapping


def mapping_from_post(post, kind, headers):
    mapping = {}
    for field, _label, _kws in FIELDS[kind]:
        raw = post.get(f'map_{field}', '')
        if raw.isdigit() and int(raw) < len(headers):
            mapping[field] = int(raw)
    return mapping


def _get(row, mapping, field):
    i = mapping.get(field)
    return row[i] if i is not None and i < len(row) else None


CATEGORY_LOOKUP = {}
for _code, _label in PART_CATEGORIES:
    CATEGORY_LOOKUP[norm(_code)] = _code
    CATEGORY_LOOKUP[norm(str(_label))] = _code


def _category(value):
    key = norm(value)
    if not key:
        return None
    if key in CATEGORY_LOOKUP:
        return CATEGORY_LOOKUP[key]
    return next((code for k, code in CATEGORY_LOOKUP.items() if key in k or k in key), None)


# ---------------------------------------------------------------- items

def plan_items(rows, mapping):
    items = list(InventoryItem.objects.all())
    by_code = {norm(i.part_code): i for i in items if i.part_code}
    by_name = {norm(i.part_name): i for i in items}
    plan, seen = [], set()
    for n, row in enumerate(rows, start=getattr(rows, 'first_line', 2)):
        code = cell_text(_get(row, mapping, 'part_code'))
        name = cell_text(_get(row, mapping, 'part_name'))
        if not code and not name:
            continue
        key = norm(code) if code else 'name:' + norm(name)
        if key in seen:
            plan.append({'row': n, 'action': 'skip', 'code': code, 'name': name, 'reason': _('Duplicate of an earlier row in the file')})
            continue
        seen.add(key)
        values = {
            'part_name': name,
            'unit_cost': cell_decimal(_get(row, mapping, 'unit_cost')),
            'sale_price': cell_decimal(_get(row, mapping, 'sale_price')),
            'quantity': cell_int(_get(row, mapping, 'quantity')),
            'reorder_level': cell_int(_get(row, mapping, 'reorder_level')),
            'location': cell_text(_get(row, mapping, 'location'))[:100],
            'category': _category(_get(row, mapping, 'category')),
            'supplier': cell_text(_get(row, mapping, 'supplier'))[:255],
        }
        existing = by_code.get(norm(code)) if code else by_name.get(norm(name))
        if existing:
            changes = {}
            if name and name != existing.part_name:
                changes['part_name'] = name[:255]
            for field in ('unit_cost', 'sale_price', 'reorder_level'):
                if values[field] is not None and values[field] != getattr(existing, field):
                    changes[field] = values[field]
            if values['location'] and values['location'] != existing.location:
                changes['location'] = values['location']
            if values['category'] and values['category'] != existing.category:
                changes['category'] = values['category']
            plan.append({'row': n, 'action': 'update' if changes else 'same', 'item': existing, 'code': code,
                         'name': existing.part_name, 'changes': changes, 'values': values})
        elif not name:
            plan.append({'row': n, 'action': 'skip', 'code': code, 'name': '', 'reason': _('New item without a name')})
        else:
            plan.append({'row': n, 'action': 'create', 'code': code, 'name': name, 'values': values})
    return plan


@transaction.atomic
def apply_items(plan, user):
    now = timezone.now()
    new_items, movements, updated = [], [], []
    for p in plan:
        v = p.get('values', {})
        if p['action'] == 'create':
            item = InventoryItem(
                part_name=v['part_name'][:255], part_code=p['code'][:100] or '', quantity=v['quantity'] or 0,
                category=v['category'] or guess_category(v['part_name'], p['code']),
                reorder_level=v['reorder_level'] if v['reorder_level'] is not None else 5,
                location=v['location'] or 'Piraeus Warehouse', unit_cost=v['unit_cost'] or 0, sale_price=v['sale_price'],
            )
            new_items.append(item)
            p['item'] = item
        elif p['action'] == 'update':
            for field, value in p['changes'].items():
                setattr(p['item'], field, value)
            updated.append(p['item'])
    InventoryItem.objects.bulk_create(new_items, batch_size=500)
    for item in new_items:
        if item.quantity:
            movements.append(StockMovement(item=item, change=item.quantity, quantity_after=item.quantity,
                                           reason='NEW', note=str(_('Excel import')), user=user, created_at=now))
    StockMovement.objects.bulk_create(movements, batch_size=500)
    if updated:
        InventoryItem.objects.bulk_update(updated, ['part_name', 'unit_cost', 'sale_price', 'reorder_level', 'location', 'category'], batch_size=500)

    # supplier prices: one row per (item, supplier) — the cost from the file
    supplier_rows = [(p['item'], p['values']['supplier'], p['values']['unit_cost'])
                     for p in plan if p['action'] in ('create', 'update', 'same')
                     and p.get('values', {}).get('supplier') and p['values'].get('unit_cost') is not None]
    prices_saved = 0
    if supplier_rows:
        suppliers = {norm(s.name): s for s in Supplier.objects.all()}
        for _item, name, _cost in supplier_rows:
            if norm(name) not in suppliers:
                suppliers[norm(name)] = Supplier.objects.create(name=name)
        existing = {(sp.item_id, sp.supplier_id): sp for sp in SupplierPrice.objects.filter(item__in=[r[0] for r in supplier_rows])}
        to_create, to_update = [], []
        for item, name, cost in supplier_rows:
            supplier = suppliers[norm(name)]
            sp = existing.get((item.id, supplier.id))
            if sp is None:
                sp = SupplierPrice(item=item, supplier=supplier, price=cost)
                existing[(item.id, supplier.id)] = sp
                to_create.append(sp)
            elif sp.price != cost:
                sp.price = cost
                sp.updated_at = timezone.now()  # bulk_update skips auto_now
                to_update.append(sp)
        SupplierPrice.objects.bulk_create(to_create, batch_size=500)
        SupplierPrice.objects.bulk_update(to_update, ['price', 'updated_at'], batch_size=500)
        prices_saved = len(to_create) + len(to_update)
    return {'created': len(new_items), 'updated': len(updated), 'prices': prices_saved}


# ---------------------------------------------------------------- clients

CLIENT_FIELDS = ('code', 'tax_id', 'tax_office', 'phone', 'email', 'address', 'city')


def _fit(field, value):
    """Cut text to the database column's maximum length."""
    return value[:Customer._meta.get_field(field).max_length]


def _digits(text):
    return re.sub(r'\D', '', text or '')


def plan_clients(rows, mapping):
    clients = list(Customer.objects.all())
    by_tax = {_digits(c.tax_id): c for c in clients if _digits(c.tax_id)}
    by_code = {norm(c.code): c for c in clients if c.code}
    by_name = {norm(c.name): c for c in clients}
    plan, seen = [], set()
    for n, row in enumerate(rows, start=getattr(rows, 'first_line', 2)):
        values = {f: cell_text(_get(row, mapping, f)) for f in ('name',) + CLIENT_FIELDS}
        values['name'] = values['name'][:255]
        if not any(values.values()):
            continue
        key = _digits(values['tax_id']) or norm(values['code']) or norm(values['name'])
        if key in seen:
            plan.append({'row': n, 'action': 'skip', 'name': values['name'], 'reason': _('Duplicate of an earlier row in the file')})
            continue
        seen.add(key)
        existing = (by_tax.get(_digits(values['tax_id'])) if _digits(values['tax_id']) else None) \
            or (by_code.get(norm(values['code'])) if values['code'] else None) \
            or (by_name.get(norm(values['name'])) if values['name'] else None)
        if existing:
            changes = {f: _fit(f, values[f]) for f in ('name',) + CLIENT_FIELDS
                       if values[f] and _fit(f, values[f]) != getattr(existing, f)}
            if 'name' in changes and norm(changes['name']) in by_name and by_name[norm(changes['name'])] != existing:
                changes.pop('name')  # another client already uses that name — keep both as they are
            plan.append({'row': n, 'action': 'update' if changes else 'same', 'client': existing,
                         'name': existing.name, 'changes': changes, 'values': values})
        elif not values['name']:
            plan.append({'row': n, 'action': 'skip', 'name': '', 'reason': _('New client without a name')})
        else:
            by_name[norm(values['name'])] = True  # reserve the name for this file
            plan.append({'row': n, 'action': 'create', 'name': values['name'], 'values': values})
    return plan


@transaction.atomic
def apply_clients(plan):
    new, updated = [], []
    for p in plan:
        if p['action'] == 'create':
            v = p['values']
            new.append(Customer(name=v['name'], **{f: _fit(f, v[f]) for f in CLIENT_FIELDS}))
        elif p['action'] == 'update':
            for field, value in p['changes'].items():
                setattr(p['client'], field, value)
            updated.append(p['client'])
    Customer.objects.bulk_create(new, batch_size=500)
    if updated:
        Customer.objects.bulk_update(updated, ('name',) + CLIENT_FIELDS, batch_size=500)
    return {'created': len(new), 'updated': len(updated), 'prices': 0}


def summarize(plan):
    counts = {'create': 0, 'update': 0, 'same': 0, 'skip': 0}
    for p in plan:
        counts[p['action']] += 1
    return counts
