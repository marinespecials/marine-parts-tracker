"""Team roles. Admin: everything + Team page. Office: everything except Team.
Technician: orders, packing, live board and warehouse — no money pages."""
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

ADMIN, OFFICE, TECHNICIAN = 'Admin', 'Office', 'Technician'
ROLE_CHOICES = [(ADMIN, _('Admin')), (OFFICE, _('Office')), (TECHNICIAN, _('Technician'))]
ROLE_HELP = {
    ADMIN: _('Everything, plus adding team members'),
    OFFICE: _('Everything except the Team page'),
    TECHNICIAN: _('Orders, packing, live board and warehouse — no invoices, clients or suppliers'),
}

# Pages a technician cannot open (money, clients, suppliers, team).
TECHNICIAN_BLOCKED = ('/finance/', '/clients/', '/catalog/', '/research/', '/purchasing/', '/suppliers/', '/team/', '/activity/')
ADMIN_ONLY = ('/team/',)


def user_role(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    if user.is_superuser:
        return ADMIN
    names = {g.name for g in user.groups.all()}
    for role in (ADMIN, TECHNICIAN, OFFICE):
        if role in names:
            return role
    return OFFICE  # existing accounts without a role keep full access


def set_role(user, role):
    groups = [Group.objects.get_or_create(name=r)[0] for r, _label in ROLE_CHOICES]
    user.groups.remove(*groups)
    user.groups.add(Group.objects.get_or_create(name=role)[0])


def can_see_money(user):
    return user_role(user) in (ADMIN, OFFICE)
