"""
Central configuration accessor.

Resolution order for every value:

    1. IntegrationSettings row (edited from the Django admin)
    2. settings.py / environment variable
    3. built-in default

The row is cached for CACHE_TTL_SECONDS so the long-running bot process
picks up admin changes without a restart, while a single request does not
hammer the database.
"""
from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from typing import Optional

from django.conf import settings as dj_settings

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30

_lock = threading.Lock()
_cache: dict = {'loaded_at': 0.0, 'row': None}


# ======================================================================
# Row access
# ======================================================================
def get_row():
    """Return the cached IntegrationSettings row (or None)."""
    now = time.monotonic()
    with _lock:
        if _cache['row'] is None or (now - _cache['loaded_at']) > CACHE_TTL_SECONDS:
            from .models import IntegrationSettings

            try:
                _cache['row'] = IntegrationSettings.load()
            except Exception as exc:  # table missing during initial migrate
                logger.debug('IntegrationSettings unavailable: %s', exc)
                _cache['row'] = None
            _cache['loaded_at'] = now
        return _cache['row']


def invalidate_cache() -> None:
    """Force the next get_row() to hit the database."""
    with _lock:
        _cache['row'] = None
        _cache['loaded_at'] = 0.0


def _pick(field: str, setting_name: str, default=None):
    """DB value if set, else the Django setting, else default."""
    row = get_row()
    if row is not None:
        value = getattr(row, field, None)
        if value not in (None, ''):
            return value
    value = getattr(dj_settings, setting_name, None)
    if value not in (None, ''):
        return value
    return default


# ======================================================================
# Telegram
# ======================================================================
def telegram_token() -> str:
    token = _pick('telegram_bot_token', 'TELEGRAM_BOT_TOKEN', '')
    return str(token or '').strip()


def telegram_bot_username() -> str:
    return str(
        _pick('telegram_bot_username', 'TELEGRAM_CHANNEL_USERNAME', '') or ''
    ).lstrip('@')


def telegram_channel_id() -> str:
    return str(_pick('telegram_channel_id', 'TELEGRAM_CHANNEL_ID', '') or '').strip()


def telegram_channel_url() -> str:
    username = telegram_bot_username()
    return f'https://t.me/{username}' if username else ''


def telegram_group_id() -> Optional[int]:
    raw = str(_pick('telegram_group_id', 'TELEGRAM_GROUP_ID', '') or '').strip()
    return int(raw) if raw.lstrip('-').isdigit() and raw else None


def telegram_admin_ids() -> set:
    row = get_row()
    if row is not None and row.telegram_admin_ids:
        return set(row.telegram_admin_id_list)
    raw = str(
        getattr(dj_settings, 'TELEGRAM_ADMIN_IDS', '')
        or __import__('os').getenv('ETHIOGEN_ADMIN_IDS', '')
    )
    return {int(v) for v in raw.replace('\n', ',').split(',') if v.strip().isdigit()}


def website_url() -> str:
    return str(
        _pick('telegram_website_url', 'BILLING_SITE_URL', 'https://ethiogen.com')
    ).rstrip('/')


# ======================================================================
# Chapa
# ======================================================================
def chapa_secret_key() -> str:
    return str(_pick('chapa_secret_key', 'CHAPA_SECRET_KEY', '') or '').strip()


def chapa_public_key() -> str:
    return str(_pick('chapa_public_key', 'CHAPA_PUBLIC_KEY', '') or '').strip()


def chapa_api_base() -> str:
    return str(
        _pick('chapa_api_base', 'CHAPA_API_BASE', 'https://api.chapa.co/v1')
    ).rstrip('/')


def chapa_enabled() -> bool:
    row = get_row()
    if row is not None:
        return bool(row.is_chapa_live)
    return bool(chapa_secret_key())


def chapa_auto_approve() -> bool:
    row = get_row()
    if row is not None:
        return bool(row.chapa_auto_approve)
    raw = str(getattr(dj_settings, 'CHAPA_AUTO_APPROVE', '1'))
    return raw.lower() not in ('0', 'false', 'no')


def chapa_webhook_url() -> str:
    row = get_row()
    if row is not None and row.chapa_webhook_url:
        return str(row.chapa_webhook_url)
    if row is not None and row.site_url:
        return row.resolved_chapa_webhook
    return f"{website_url()}/billing/chapa/webhook/"


# ======================================================================
# Telebirr / bank
# ======================================================================
def telebirr_enabled() -> bool:
    row = get_row()
    if row is not None:
        return bool(row.telebirr_enabled)
    return True


def telebirr_name() -> str:
    return str(_pick('telebirr_name', 'BILLING_TELEBIRR_NAME', '') or '')


def telebirr_phone() -> str:
    return str(_pick('telebirr_phone', 'BILLING_TELEBIRR_PHONE', '') or '')


def telebirr_api_base() -> str:
    return str(_pick('telebirr_api_base', 'TELEBIRR_API_BASE', '') or '').rstrip('/')


def telebirr_api_key() -> str:
    return str(_pick('telebirr_api_key', 'TELEBIRR_API_KEY', '') or '')


def telebirr_merchant_id() -> str:
    return str(_pick('telebirr_merchant_id', 'TELEBIRR_MERCHANT_ID', '') or '')


def telebirr_has_gateway() -> bool:
    return bool(telebirr_api_base())


def bank_enabled() -> bool:
    row = get_row()
    if row is not None:
        return bool(row.bank_enabled)
    return True


def bank_name() -> str:
    return str(_pick('bank_name', 'BILLING_BANK_NAME', '') or '')


def bank_account_name() -> str:
    return str(_pick('bank_account_name', 'BILLING_BANK_ACCOUNT_NAME', '') or '')


def bank_account_number() -> str:
    return str(_pick('bank_account_number', 'BILLING_BANK_ACCOUNT_NUMBER', '') or '')


# ======================================================================
# Subscription defaults
# ======================================================================
def currency() -> str:
    return str(_pick('currency', 'BILLING_CURRENCY', 'ETB') or 'ETB')


def subscription_price() -> Decimal:
    value = _pick('subscription_price', 'BILLING_SUBSCRIPTION_PRICE', '500.00')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('500.00')


def subscription_days() -> int:
    try:
        return int(_pick('subscription_days', 'BILLING_SUBSCRIPTION_DAYS', 30) or 30)
    except Exception:
        return 30


def plan_name() -> str:
    return 'Channel Subscription'


def payment_instructions() -> str:
    return str(_pick('payment_instructions', 'BILLING_PAYMENT_INSTRUCTIONS', '') or '')


# ======================================================================
# Branding
# ======================================================================
def logo_url() -> str:
    """
    URL of the uploaded logo, or '' when none has been uploaded yet.

    Callers should fall back to their own static logo in that case.
    """
    row = get_row()
    if row is not None and getattr(row, 'logo_image', None):
        try:
            return row.logo_image.url
        except Exception:
            return ''
    return ''


def logo_fallback_url() -> str:
    """Static logo used until an admin uploads one."""
    return '/static/branding/ethiogen-logo.png'


def logo_wordmark() -> str:
    return str(_pick('logo_wordmark', 'BRAND_WORDMARK', 'Ethiogen') or 'Ethiogen')


def logo_show_caption() -> bool:
    row = get_row()
    if row is not None:
        return bool(row.logo_show_caption)
    return True


def logo_height() -> int:
    try:
        return int(_pick('logo_height_px', 'BRAND_LOGO_HEIGHT_PX', 48) or 48)
    except Exception:
        return 48


def favicon_url() -> str:
    row = get_row()
    if row is not None and getattr(row, 'favicon_image', None):
        try:
            return row.favicon_image.url
        except Exception:
            pass
    return logo_url() or logo_fallback_url()


# ======================================================================
# Facebook
# ======================================================================
def facebook_page_id() -> str:
    return str(_pick('facebook_page_id', 'FACEBOOK_PAGE_ID', '') or '').strip()


def facebook_page_name() -> str:
    return str(_pick('facebook_page_name', 'FACEBOOK_PAGE_NAME', '') or '')


def facebook_page_token() -> str:
    return str(
        _pick('facebook_page_access_token', 'FACEBOOK_PAGE_ACCESS_TOKEN', '') or ''
    ).strip()


def facebook_enabled() -> bool:
    row = get_row()
    if row is not None:
        return bool(
            row.facebook_enabled
            and row.facebook_page_id
            and row.facebook_page_access_token
        )
    return bool(facebook_page_token())


def facebook_api_version() -> str:
    version = str(
        _pick('facebook_api_version', 'FACEBOOK_API_VERSION', 'v21.0') or 'v21.0'
    )
    return version.lstrip('/')


# ======================================================================
# Diagnostics
# ======================================================================
def configuration_report() -> list:
    """
    Return a list of (label, ok, detail) for the admin 'Test connections'
    display. Performs no network calls.
    """
    row = get_row()
    source = 'admin settings' if row is not None else 'settings.py / environment'
    report = [
        ('Configuration source', True, source),
        ('Telegram bot token', bool(telegram_token()), 'set' if telegram_token() else 'missing'),
        ('Telegram channel ID', bool(telegram_channel_id()),
         telegram_channel_id() or 'missing'),
        ('Telegram bot username', bool(telegram_bot_username()),
         telegram_bot_username() or 'missing'),
        ('Telegram group ID', telegram_group_id() is not None,
         str(telegram_group_id() or 'not set')),
        ('Telegram admin IDs', bool(telegram_admin_ids()),
         ', '.join(str(i) for i in sorted(telegram_admin_ids())) or 'none'),
        ('Chapa live', chapa_enabled(),
         'enabled' if chapa_enabled() else 'manual-only (no secret key)'),
        ('Chapa auto-approve', chapa_auto_approve(), 'on' if chapa_auto_approve() else 'manual review'),
        ('Chapa webhook', bool(chapa_webhook_url()), chapa_webhook_url() or 'missing'),
        ('Telebirr transfer', telebirr_enabled(),
         telebirr_phone() or 'enabled but no phone set'),
        ('Telebirr gateway API', telebirr_has_gateway(),
         telebirr_api_base() or 'none (manual transfer only)'),
        ('Bank transfer', bank_enabled(),
         bank_account_number() or 'enabled but no account set'),
        ('Subscription price', True,
         f"{subscription_price()} {currency()} / {subscription_days()} days"),
        ('Site URL', bool(website_url()), website_url() or 'missing'),
        ('Logo uploaded', bool(logo_url()),
         logo_url() or 'not uploaded (using static fallback)'),
        ('Facebook page', facebook_enabled(),
         f"{facebook_page_name()} ({facebook_page_id()})" if facebook_enabled()
         else 'disabled'),
        ('Facebook API version', bool(facebook_api_version()), f'v={facebook_api_version()}'),
    ]
    return report
