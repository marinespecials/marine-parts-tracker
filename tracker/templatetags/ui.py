"""Small template helpers shared by every page: icons, status badges, money, active nav links."""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()

STATUS_LABELS = {
    'DRAFT': 'Draft',
    'PENDING': 'Pending',
    'PROCESSING': 'Processing',
    'DELIVERED': 'Delivered',
    'UNPAID': 'Unpaid',
    'OVERDUE': 'Overdue',
    'PAID': 'Paid',
    'VOID': 'Void',
    'RECEIVED': 'Received',
    'SENT': 'Sent',
}


@register.simple_tag
def icon(name, extra_class=''):
    """{% icon "box" %} -> inline SVG from the sprite in partials/icons.html"""
    cls = f'icon {extra_class}'.strip()
    return format_html('<svg class="{}" aria-hidden="true"><use href="#i-{}"></use></svg>', cls, name)


@register.filter
def status_label(code):
    code = (code or '').upper()
    return STATUS_LABELS.get(code, code.title())


@register.simple_tag
def status_badge(code):
    code = (code or '').upper()
    return format_html('<span class="badge badge-{}">{}</span>', code.lower(), STATUS_LABELS.get(code, code.title()))


@register.filter
def money(value):
    """1234.5 -> '1,234.50 €'. Empty or bad values show as 0.00 € instead of a blank."""
    try:
        number = Decimal(str(value if value not in (None, '') else 0))
    except (InvalidOperation, ValueError):
        number = Decimal('0')
    return f'{number:,.2f} €'


@register.filter
def initials(name):
    parts = [p for p in str(name or '').replace('.', ' ').split() if p]
    return ''.join(p[0] for p in parts[:2]).upper() or '?'


@register.simple_tag(takes_context=True)
def active(context, *url_names):
    """{% active 'inventory_list' 'part_detail' %} -> 'active' when the current page matches."""
    match = getattr(context.get('request'), 'resolver_match', None)
    if not match:
        return ''
    names = {match.url_name, match.view_name}
    return 'active' if names & set(url_names) else ''


@register.filter
def percent_of(part, whole):
    try:
        return int(round(100 * float(part) / float(whole))) if float(whole) else 0
    except (TypeError, ValueError):
        return 0
