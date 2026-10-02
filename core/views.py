import os

from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.http import HttpResponse


class ThrottledLoginView(LoginView):
    """Login that locks an IP out for 15 minutes after 5 wrong passwords.

    Note: the counter lives in Django's default per-process cache, so with several
    gunicorn workers the effective limit is a little looser. Still stops guessing bots.
    """
    template_name = 'auth/login.html'
    max_attempts = 5
    window_seconds = 15 * 60

    def _key(self):
        ip = self.request.META.get('REMOTE_ADDR', 'unknown')
        if os.environ.get('RENDER'):  # behind Render's proxy the real IP is in this header
            forwarded = self.request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip = forwarded.split(',')[0].strip() or ip
        return f'login-fail:{ip}'

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if request.method == 'POST' and cache.get(self._key(), 0) >= self.max_attempts:
            return HttpResponse(
                'Too many failed sign-in attempts. Please wait 15 minutes and try again.',
                status=429, content_type='text/plain',
            )
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._key()
        cache.add(key, 0, self.window_seconds)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, self.window_seconds)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._key())
        return super().form_valid(form)
