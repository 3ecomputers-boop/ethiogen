"""
Template tags for site-wide branding.

Every logo in the project should be rendered with {% brand_logo %} so that
uploading a new image in the Django admin updates the header, footer,
dashboards and favicon at once.

Usage
-----
    {% load ethiogen_tags %}

    {# full lockup: image with the wordmark underneath #}
    {% brand_logo %}
    {% brand_logo class="h-10 w-auto" %}
    {% brand_logo height=40 show_caption=False %}

    {# just the image, no caption #}
    {% brand_logo show_caption=False class="footer-logo" %}

    {# the favicon URL, for <link rel="icon"> #}
    {% favicon_url %}
"""
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from billing import config

register = template.Library()

DEFAULT_FALLBACK = '/static/branding/ethiogen-logo.png'
MONO_FALLBACK = '/static/branding/ethiogen-logo-mono.png'
LIGHT_FALLBACK = '/static/branding/ethiogen-logo-light.png'
ONBRAND_FALLBACK = '/static/branding/ethiogen-logo-onbrand.png'

# The default (and any explicit "colour") is the brand artwork as drawn, with
# only the opaque white field removed. "mono" is the single-hue orange ramp for
# dark surfaces, where the artwork's blue leg drops to ~2.2:1 and goes muddy.
_VARIANTS = {
    'mono': MONO_FALLBACK,
    'dark': MONO_FALLBACK,
    'light': LIGHT_FALLBACK,
    'onbrand': ONBRAND_FALLBACK,
    'on-brand': ONBRAND_FALLBACK,
    'colour': DEFAULT_FALLBACK,
    'color': DEFAULT_FALLBACK,
    'full': DEFAULT_FALLBACK,
}


def _fallback_for(variant):
    """Bundled artwork matching the surface it will sit on."""
    return _VARIANTS.get(str(variant).strip().lower(), DEFAULT_FALLBACK)


@register.simple_tag
def brand_logo(height=None, show_caption=None, css_class='', link_url='', alt=None,
               variant='colour'):
    """
    Render the site logo, with an optional wordmark underneath.

    Falls back to the bundled static logo until an admin uploads one.

    `variant` picks the bundled artwork for the surface it will sit on.
    Omit it (or pass "colour") for the brand artwork as drawn. The ramps are
    not interchangeable: amber-400 reaches 10.69:1 on a slate-900 header but
    only 1.67:1 on white, where it washes out to a pale smudge, so "light"
    steps down to brand-700 / amber-700; "mono" is the orange ramp for dark
    surfaces where the artwork's blue leg drops to ~2.2:1; and "onbrand" is a
    knockout white for brand-coloured surfaces. Ignored once an admin has
    uploaded a logo, since that is one file for the whole site.
    """
    src = config.logo_url() or _fallback_for(variant)
    if src.startswith('/static/') and not src.startswith('/staticfiles/'):
        # make the static URL version-proof across DEBUG/collectstatic setups
        try:
            from django.templatetags.static import static

            src = static(src[len('/static/'):])
        except Exception:
            pass

    px = height if height else config.logo_height()
    caption = config.logo_show_caption() if show_caption is None else show_caption
    wordmark = config.logo_wordmark()
    label = alt or wordmark

    image = format_html(
        '<img src="{}" alt="{}" class="brand-logo-image {}" '
        'style="height:{}px;width:auto;max-width:100%;object-fit:contain;" >',
        src, label, css_class, px,
    )

    if not caption:
        return mark_safe(image)

    block = format_html(
        '<span class="brand-logo" style="display:inline-flex;flex-direction:column;'
        'align-items:center;justify-content:center;gap:2px;line-height:1;">{}'
        '<span class="brand-logo-caption" style="font-weight:800;letter-spacing:.02em;'
        'text-align:center;">{}</span></span>',
        image, wordmark,
    )

    if link_url:
        return format_html('<a href="{}" class="brand-logo-link">{}</a>', link_url, block)
    return mark_safe(block)


@register.simple_tag
def brand_wordmark():
    """Just the configured wordmark text, e.g. for an inline lockup."""
    return config.logo_wordmark()


# ============================================================================
# ADMIN NAVIGATION
# ============================================================================

# app_label -> bootstrap-icons glyph, for the admin sidebar.
APP_ICONS = {
    'accounts': 'bi-people',
    'auth': 'bi-shield-lock',
    'borker_network': 'bi-diagram-3',
    'employers': 'bi-buildings',
    'freelancer': 'bi-laptop',
    'jobs': 'bi-briefcase',
    'recruitment': 'bi-person-badge',
    'billing': 'bi-credit-card',
    'tenants': 'bi-diagram-2',
    'talent': 'bi-person-badge',
    'django_celery_beat': 'bi-clock-history',
}

# Human labels for app_labels whose auto-generated name is ugly.
APP_LABELS = {
    'borker_network': 'Borker Network',
    'auth': 'Auth & Permissions',
}


def _field(entry, key, default=''):
    """
    Read `key` from an admin app_list entry.

    available_apps holds plain dicts, not model instances. Django's template
    engine falls back to dict lookup for {{ app.app_label }}, so the template
    works either way -- but a Python filter using getattr() silently returns
    the default for a dict, which is how the app names came out blank.
    """
    if isinstance(entry, dict):
        value = entry.get(key, default)
    else:
        value = getattr(entry, key, default)
    return default if value is None else value


@register.filter
def app_icon(app_label):
    """Bootstrap Icons glyph for an admin app_label, with a sane fallback."""
    return APP_ICONS.get(str(app_label).lower(), 'bi-folder')


@register.filter
def app_label_of(app):
    """The app_label for an entry from the admin's app_list context."""
    return _field(app, 'app_label')


@register.filter
def app_name_of(app):
    """
    Display name for an app, replacing Django's auto-derived ones.

    Django derives "Borker_Network" from the module name, and "Authentication
    and Authorization" from django.contrib.auth -- neither reads well in a nav.
    """
    label = _field(app, 'app_label')
    return APP_LABELS.get(label) or _field(app, 'name') or label


@register.simple_tag(takes_context=True)
def admin_is_active(context, url):
    """True when the current request path starts with this admin url."""
    request = context.get('request')
    if not request or not url:
        return False
    path = request.path
    if url.endswith('/'):
        return path == url or path.startswith(url)
    return path.startswith(url + '/')


@register.simple_tag
def brand_logo_url():
    """The logo URL only (uploaded image, or the static fallback)."""
    return config.logo_url() or DEFAULT_FALLBACK


@register.simple_tag
def favicon_url():
    """URL for <link rel="icon">; the uploaded logo unless a favicon is set."""
    url = config.favicon_url()
    if url.startswith('/static/') and not url.startswith('/staticfiles/'):
        try:
            from django.templatetags.static import static

            url = static(url[len('/static/'):])
        except Exception:
            pass
    return url
