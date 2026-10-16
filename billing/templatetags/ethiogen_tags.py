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
LIGHT_FALLBACK = '/static/branding/ethiogen-logo-light.png'
ONBRAND_FALLBACK = '/static/branding/ethiogen-logo-onbrand.png'

_VARIANTS = {
    'light': LIGHT_FALLBACK,
    'onbrand': ONBRAND_FALLBACK,
    'on-brand': ONBRAND_FALLBACK,
}


def _fallback_for(variant):
    """Bundled artwork matching the surface it will sit on."""
    return _VARIANTS.get(str(variant).strip().lower(), DEFAULT_FALLBACK)


@register.simple_tag
def brand_logo(height=None, show_caption=None, css_class='', link_url='', alt=None,
               variant='dark'):
    """
    Render the site logo, with an optional wordmark underneath.

    Falls back to the bundled static logo until an admin uploads one.

    `variant` picks the bundled artwork to use on a dark, light or
    brand-coloured surface. The ramps are not interchangeable: amber-400
    reaches 10.69:1 on the slate-900 headers but only 1.67:1 on a white one,
    where it washes out to a pale smudge. The light variant steps down to
    brand-700 / amber-700 so the mark keeps at least 3:1 on white, and
    `onbrand` is a knockout white for brand-coloured surfaces. Ignored once an
    admin has uploaded a logo, since that is one file for the whole site.
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
