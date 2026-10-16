from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import urlencode
from django.urls import reverse


class LoginRequiredMiddleware:
    """Require a logged-in user for every page except login/logout/admin/static.

    The admin has its own login screen, so /admin/ is exempt here.
    Set REQUIRE_LOGIN=False in the environment to disable (not recommended).
    """

    EXEMPT_PREFIXES = ('/admin/', '/static/', '/login/', '/logout/', '/healthz/', '/i18n/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, 'REQUIRE_LOGIN', True)
            and not request.user.is_authenticated
            and not request.path.startswith(self.EXEMPT_PREFIXES)
        ):
            query = urlencode({'next': request.get_full_path()})
            # Resolve the view name (e.g. 'login') to a path (e.g. '/login/') first
            login_url = reverse(settings.LOGIN_URL)
            return redirect(f"{login_url}?{query}")
            
        return self.get_response(request)


class RoleAccessMiddleware:
    """Technicians can't open money pages; only Admins can open the Team page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            from django.contrib import messages
            from django.utils.translation import gettext as _
            from tracker.roles import ADMIN, ADMIN_ONLY, TECHNICIAN, TECHNICIAN_BLOCKED, user_role
            role = user_role(user)
            blocked = (request.path.startswith(ADMIN_ONLY) and role != ADMIN) or                       (role == TECHNICIAN and request.path.startswith(TECHNICIAN_BLOCKED))
            if blocked:
                messages.warning(request, _("That page isn't available for your role."))
                return redirect('app_hub')
        return self.get_response(request)
