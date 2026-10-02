"""Small helpers for safely reading numbers out of form posts."""
from decimal import Decimal, InvalidOperation


def to_decimal(value, default='0.00', minimum=None):
    """Parse money from user input. Never raises; bad input gives `default`.
    Accepts '12.50', '12,50' (Greek decimal comma) and '1,234.50'."""
    text = str(value if value is not None else '').strip()
    if ',' in text and '.' not in text:
        text = text.replace(',', '.')
    else:
        text = text.replace(',', '')
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        number = Decimal(str(default))
    if not number.is_finite():
        number = Decimal(str(default))
    if minimum is not None and number < Decimal(str(minimum)):
        number = Decimal(str(minimum))
    return number.quantize(Decimal('0.01'))


def to_int(value, default=1, minimum=None):
    """Parse a whole number from user input. Never raises."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        number = default
    if minimum is not None and number < minimum:
        number = minimum
    return number


def redirect_back(request, fallback, **kwargs):
    """Redirect to the page the user came from, but only if it is on this site."""
    from django.shortcuts import redirect
    from django.utils.http import url_has_allowed_host_and_scheme

    referer = request.META.get('HTTP_REFERER')
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(referer)
    return redirect(fallback, **kwargs)
