"""One place that changes stock, so every change is logged in the part's stock history."""
from .models import ActivityLog, StockMovement


def _user(request_or_user):
    user = getattr(request_or_user, 'user', request_or_user)
    return user if getattr(user, 'is_authenticated', False) else None


def move_stock(item, delta, reason, who=None, note='', always_log=False):
    """Add (or remove, if negative) stock. Never goes below 0. Returns the real change."""
    before = item.quantity
    item.quantity = max(0, before + int(delta))
    if item.quantity != before:
        item.save(update_fields=['quantity'])
    actual = item.quantity - before
    if actual or always_log:
        StockMovement.objects.create(item=item, change=actual, quantity_after=item.quantity,
                                     reason=reason, note=(note or '')[:255], user=_user(who))
    return actual


def set_stock(item, new_quantity, reason, who=None, note='', always_log=False):
    return move_stock(item, max(0, int(new_quantity)) - item.quantity, reason, who, note, always_log)


def log_activity(request, action, target='', url=''):
    ActivityLog.objects.create(user=_user(request), action=action, target=str(target)[:255], url=url or '')
