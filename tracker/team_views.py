"""Team members, roles, the activity log and 'change my password'."""
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from .models import ActivityLog, StockMovement
from .roles import ADMIN, ROLE_CHOICES, ROLE_HELP, set_role, user_role
from .stock import log_activity

ROLE_CODES = {code for code, _label in ROLE_CHOICES}


def _check_password(request, password, confirm, user):
    if password != confirm:
        messages.error(request, _("The two passwords don't match."))
        return False
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)
        return False
    return True


@transaction.atomic
def team(request):
    if user_role(request.user) != ADMIN:
        raise PermissionDenied

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            username = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            role = request.POST.get('role')
            password = request.POST.get('password', '')
            if not username or role not in ROLE_CODES:
                messages.error(request, _("Username and role are required."))
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, _("The username %(u)s is already taken.") % {'u': username})
            elif _check_password(request, password, request.POST.get('password2', ''), User(username=username, first_name=first_name)):
                member = User.objects.create_user(username=username, password=password, first_name=first_name)
                set_role(member, role)
                log_activity(request, 'user_created', f'{username} · {dict(ROLE_CHOICES)[role]}')
                messages.success(request, _("%(u)s can now sign in.") % {'u': username})

        elif action == 'update':
            member = get_object_or_404(User, id=request.POST.get('user_id'))
            role = request.POST.get('role')
            active = request.POST.get('is_active') == '1'
            password = request.POST.get('password', '')
            if member == request.user and (not active or (role and role != ADMIN)):
                messages.error(request, _("You can't remove your own admin access."))
                return redirect('team')
            changes = []
            if role in ROLE_CODES and not member.is_superuser and role != user_role(member):
                set_role(member, role)
                changes.append(str(dict(ROLE_CHOICES)[role]))
            if member.is_active != active:
                member.is_active = active
                member.save(update_fields=['is_active'])
                changes.append(_('active') if active else _('deactivated'))
            if password:
                if not _check_password(request, password, request.POST.get('password2', ''), member):
                    return redirect('team')
                member.set_password(password)
                member.save(update_fields=['password'])
                changes.append(_('new password'))
            if changes:
                log_activity(request, 'user_updated', f"{member.username} · {', '.join(changes)}")
                messages.success(request, _("%(u)s updated.") % {'u': member.username})
        return redirect('team')

    members = list(User.objects.prefetch_related('groups').order_by('-is_active', 'username'))
    for m in members:
        m.role = user_role(m)
    return render(request, 'tracker/team.html', {
        'members': members,
        'role_choices': ROLE_CHOICES,
        'role_help': [(code, label, ROLE_HELP[code]) for code, label in ROLE_CHOICES],
    })


def activity(request):
    tab = request.GET.get('tab', 'actions')
    who = request.GET.get('user', '')
    logs = ActivityLog.objects.select_related('user')
    moves = StockMovement.objects.select_related('item', 'user')
    if who.isdigit():
        logs, moves = logs.filter(user_id=who), moves.filter(user_id=who)
    return render(request, 'tracker/activity.html', {
        'tab': tab,
        'who': who,
        'logs': logs[:200],
        'moves': moves[:200],
        'people': User.objects.order_by('username'),
    })


class PasswordChange(auth_views.PasswordChangeView):
    template_name = 'tracker/password_change.html'
    success_url = reverse_lazy('app_hub')

    def form_valid(self, form):
        messages.success(self.request, _("Your password was changed."))
        return super().form_valid(form)
