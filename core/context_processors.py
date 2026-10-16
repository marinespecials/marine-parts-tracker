from django.db.models import Count, F, Q


def nav_counts(request):
    """Small numbers shown next to sidebar links (active orders, low stock, overdue invoices).
    Two cheap COUNT queries, and only for signed-in pages."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    from finance.models import Invoice
    from tracker.models import InventoryItem

    counts = Invoice.objects.aggregate(
        active_orders=Count('id', filter=Q(status__in=['PENDING', 'PROCESSING'])),
        overdue=Count('id', filter=Q(status='OVERDUE')),
    )
    counts['low_stock'] = InventoryItem.objects.filter(quantity__lte=F('reorder_level')).count()
    from tracker.roles import ADMIN, TECHNICIAN, user_role
    role = user_role(request.user)
    return {'nav_counts': counts, 'role': role, 'can_money': role != TECHNICIAN, 'is_admin': role == ADMIN}
