"""
Service layer for the Telegram billing flow.

Everything that talks to the outside world (Telegram, Chapa) lives here so
that admin views, bot callbacks and management commands all share one
implementation.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import requests
from django.conf import settings
from django.utils import timezone

from . import config
from .models import ChannelPost, PostApplication, Subscription
from tenants.models import TenantAuditLog

logger = logging.getLogger(__name__)


# ======================================================================
# Telegram
# ======================================================================
#
# NOTE: python-telegram-bot v20+ exposes only an *async* API. Calling
# Bot.send_message() from Django (admin views, webhooks, management
# commands) returns an un-awaited coroutine and silently sends nothing.
# The Django side therefore talks to the Bot HTTP API directly, the same
# way jobs/management/commands/post_website_update.py does. The bot
# process itself keeps using the async client (see bot/telegram_bridge.py).
#
TELEGRAM_API_BASE = 'https://api.telegram.org'


def get_bot_token() -> str:
    return config.telegram_token()


def target_chat_id() -> str:
    return config.telegram_channel_id()


def _telegram_call(method: str, payload: dict, timeout: int = 20) -> dict:
    """
    POST to a Bot API method. Returns a normalised dict:
        {'ok': True, 'result': {...}}  or  {'ok': False, 'error': '...'}
    """
    token = get_bot_token()
    if not token:
        return {'ok': False, 'error': 'TELEGRAM_BOT_TOKEN is not configured'}

    url = f'{TELEGRAM_API_BASE}/bot{token}/{method}'
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.error('Telegram %s request failed: %s', method, exc)
        return {'ok': False, 'error': f'network error: {exc}'}

    if response.status_code != 200:
        return {'ok': False, 'error': f'HTTP {response.status_code}'}
    try:
        data = response.json()
    except ValueError:
        return {'ok': False, 'error': 'invalid JSON from Telegram'}

    if not data.get('ok'):
        return {'ok': False, 'error': data.get('description', 'unknown Telegram error')}
    return {'ok': True, 'result': data.get('result') or {}}


def _serialize_reply_markup(reply_markup) -> Optional[dict]:
    """Convert a PTB InlineKeyboardMarkup into Bot API JSON."""
    if reply_markup is None:
        return None
    rows = getattr(reply_markup, 'inline_keyboard', None)
    if rows is None:
        return None
    serialized = []
    for row in rows:
        line = []
        for button in row:
            if getattr(button, 'url', None):
                line.append({'text': button.text, 'url': button.url})
            else:
                line.append({
                    'text': button.text,
                    'callback_data': button.callback_data,
                })
        if line:
            serialized.append(line)
    return {'inline_keyboard': serialized}


def send_to_channel(text: str, reply_markup=None, parse_mode: str = 'Markdown') -> dict:
    """
    Send a message to the configured channel/group.

    Returns {'ok': True, 'message_id': int} on success, otherwise
    {'ok': False, 'error': '...'}. Never raises.
    """
    chat_id = target_chat_id()
    if not chat_id:
        return {'ok': False, 'error': 'TELEGRAM_CHANNEL_ID is not configured'}

    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    markup = _serialize_reply_markup(reply_markup)
    if markup:
        payload['reply_markup'] = markup

    result = _telegram_call('sendMessage', payload)
    if not result['ok']:
        return result
    return {'ok': True, 'message_id': result['result'].get('message_id')}


def send_to_user(
    chat_id: int, text: str, reply_markup=None, parse_mode: str = 'Markdown'
) -> bool:
    """Send a direct message to a user. Returns True on success."""
    if not chat_id:
        return False
    payload = {'chat_id': int(chat_id), 'text': text, 'parse_mode': parse_mode}
    markup = _serialize_reply_markup(reply_markup)
    if markup:
        payload['reply_markup'] = markup

    result = _telegram_call('sendMessage', payload)
    if not result['ok']:
        logger.error('send_to_user(%s) failed: %s', chat_id, result['error'])
        return False
    return True


def resolve_chat_id(user) -> Optional[int]:
    """Best-effort Telegram chat id for a Django user."""
    telegram_id = (
        Subscription.objects.filter(user=user)
        .exclude(telegram_chat_id=None)
        .values_list('telegram_chat_id', flat=True)
        .first()
    )
    if telegram_id:
        return int(telegram_id)
    profile = getattr(user, 'telegram_profile', None)
    return int(profile.chat_id) if profile else None


# ======================================================================
# Channel posts
# ======================================================================
def publish_post(post: ChannelPost, alert: bool = True) -> dict:
    """
    Send a ChannelPost to Telegram and record the resulting message id.

    Safe to call from admin actions: failures are stored on the post rather
    than raised. When `alert` is true, active subscribers are notified too.

    This is the single chokepoint every channel publish goes through, so it
    is also where the tenant quota is enforced. A post owned by an
    Organization may only be published while that organization has an
    active plan and posts remaining. Posts with no organization (admin
    broadcasts, historical rows) are unaffected.
    """
    from bot.telegram_bridge import build_post_keyboard

    # --- tenant quota gate ------------------------------------------
    organization = getattr(post, 'organization', None)
    quota_blocked = False
    if organization is not None and post.kind == ChannelPost.KIND_JOB:
        from tenants import services as tenant_services

        allowed, reason = tenant_services.can_publish_job(organization)
        if not allowed:
            quota_blocked = True
            post.status = ChannelPost.STATUS_FAILED
            post.publish_error = reason
            post.save(update_fields=['status', 'publish_error'])
            logger.info('Quota blocked post %s for %s: %s',
                        post.pk, organization.slug, reason)
            return {'ok': False, 'error': reason, 'quota_blocked': True}

    result = send_to_channel(
        post.build_text(),
        reply_markup=build_post_keyboard(post),
    )
    if result.get('ok'):
        post.telegram_message_id = result['message_id']
        post.telegram_chat_id = target_chat_id()
        post.status = ChannelPost.STATUS_PUBLISHED
        post.published_at = timezone.now()
        post.publish_error = ''
    else:
        post.status = ChannelPost.STATUS_FAILED
        post.publish_error = result.get('error', 'unknown error')
    post.save(
        update_fields=[
            'telegram_message_id', 'telegram_chat_id', 'status',
            'published_at', 'publish_error',
        ]
    )

    # --- charge the quota -------------------------------------------
    # Only a successful publish consumes a unit; a Telegram failure must
    # not cost the employer a post.
    if result.get('ok') and organization is not None \
            and post.kind == ChannelPost.KIND_JOB:
        from tenants import services as tenant_services

        tenant_services.consume_job_post(organization)
        TenantAuditLog.record(
            organization, post.employer, 'job_post.published',
            obj=post, message_id=post.telegram_message_id,
        )

    if result.get('ok') and alert:
        try:
            from . import alerts

            alerts.send_immediate_alerts(post)
        except Exception as exc:
            # Alerting must never turn a successful post into a failure.
            logger.error('Alert fan-out failed for post %s: %s', post.pk, exc)
    return result


# ======================================================================
# Chapa
# ======================================================================
def chapa_enabled() -> bool:
    return config.chapa_enabled()


def init_chapa_checkout(subscription: Subscription) -> dict:
    """
    Create a Chapa checkout session for a subscription.

    Returns {'ok': True, 'checkout_url': ...} or {'ok': False, 'error': ...}.
    """
    secret = config.chapa_secret_key()
    if not secret:
        return {
            'ok': False,
            'error': 'Chapa is not configured. Set the Chapa secret key in '
                     'Billing → Integration settings.',
        }

    base = config.chapa_api_base()
    bot_username = config.telegram_bot_username() or 'ethiogenjob_bot'

    payload = {
        'amount': str(subscription.amount),
        'currency': config.currency(),
        'ref': f'sub-{subscription.pk}',
        'first_name': subscription.user.first_name or 'Ethiogen',
        'last_name': subscription.user.last_name or 'User',
        'email': subscription.user.email or 'user@example.com',
        'callback_url': config.chapa_webhook_url(),
        'return_url': f'https://t.me/{bot_username}',
        'customization': {
            'title': subscription.plan_name,
            'description': 'Unlock all Ethiogen job and tender posts',
        },
        'meta': {
            'subscription_id': subscription.pk,
            'telegram_chat_id': subscription.telegram_chat_id or '',
        },
    }

    # Optional Telebirr-direct gateway details, when one is configured.
    if config.telebirr_has_gateway() and config.telebirr_merchant_id():
        payload['meta']['telebirr_merchant_id'] = config.telebirr_merchant_id()

    try:
        response = requests.post(
            f'{base}/transaction/initialize',
            json=payload,
            headers={
                'Authorization': f'Bearer {secret}',
                'Content-Type': 'application/json',
            },
            timeout=30,
        )
        data = response.json()
    except Exception as exc:
        logger.error('Chapa initialize failed: %s', exc)
        return {'ok': False, 'error': f'Could not reach Chapa: {exc}'}

    if response.status_code != 200 or not data.get('status'):
        message = (data.get('message') or {}).get('reason') if isinstance(data.get('message'), dict) else data.get('message')
        logger.error('Chapa rejected the request: %s', data)
        return {'ok': False, 'error': message or 'Chapa rejected the request.'}

    subscription.chapa_reference = data.get('data', {}).get('ref', '') or f'sub-{subscription.pk}'
    subscription.chapa_checkout_url = data.get('data', {}).get('checkout_url', '')
    subscription.chapa_payload = data
    subscription.payment_method = Subscription.PAYMENT_CHAPA
    if subscription.status == Subscription.STATUS_AWAITING_PAYMENT:
        subscription.status = Subscription.STATUS_PENDING_REVIEW
    subscription.save(
        update_fields=[
            'chapa_reference', 'chapa_checkout_url', 'chapa_payload',
            'payment_method', 'status',
        ]
    )
    return {'ok': True, 'checkout_url': subscription.chapa_checkout_url}


def handle_chapa_webhook(data: dict) -> Optional[Subscription]:
    """
    Process a Chapa webhook payload.

    Returns the affected Subscription, or None if the payload is not a
    successful, recognised payment.
    """
    ref = ''
    trx = data.get('data') or {}
    meta = trx.get('meta') or {}
    if meta.get('subscription_id'):
        ref = str(meta['subscription_id'])
    elif trx.get('reference'):
        ref = str(trx['reference'])
    elif trx.get('ref', '').startswith('sub-'):
        ref = trx['ref'].split('-', 1)[1]

    subscription = None
    if ref.isdigit():
        subscription = Subscription.objects.filter(pk=int(ref)).first()
    if subscription is None and trx.get('reference'):
        subscription = Subscription.objects.filter(
            chapa_reference=trx['reference']
        ).first()

    if subscription is None:
        logger.warning('Chapa webhook for unknown reference: %s', ref)
        return None

    if data.get('status') != 'success':
        logger.info('Chapa payment not successful for sub %s: %s', subscription.pk, data.get('status'))
        return subscription

    if config.chapa_auto_approve():
        activate_subscription(subscription, reviewed_by=None, note='Auto-approved via Chapa webhook.')
    return subscription


# ======================================================================
# Approve / reject
# ======================================================================
def activate_subscription(subscription: Subscription, reviewed_by=None, note: str = '') -> bool:
    """Activate a subscription and notify the user over Telegram + email."""
    already_active = subscription.status == Subscription.STATUS_ACTIVE
    if not already_active:
        days = subscription.duration_days or getattr(settings, 'BILLING_SUBSCRIPTION_DAYS', 30)
        now = timezone.now()
        subscription.status = Subscription.STATUS_ACTIVE
        subscription.activated_at = now
        subscription.expires_at = now + timezone.timedelta(days=days)
        if reviewed_by is not None:
            subscription.reviewed_by = reviewed_by
        subscription.reviewed_at = now
        if note:
            subscription.review_note = note
        subscription.save()

    chat_id = subscription.telegram_chat_id or resolve_chat_id(subscription.user)
    if chat_id:
        from bot.telegram_bridge import build_subscribe_keyboard

        message = (
            "\u2705 *Subscription active!*\n\n"
            f"Your payment for *{subscription.plan_name}* has been approved.\n\n"
            f"Amount: {subscription.amount} {getattr(settings, 'BILLING_CURRENCY', 'ETB')}"
        )
        if subscription.expires_at:
            valid_until = timezone.localtime(subscription.expires_at)
            message += f"\nValid until: {valid_until:%d %b %Y}"
        message += "\n\nYou can now Apply to any post in the channel."

        send_to_user(
            chat_id,
            message,
            reply_markup=build_subscribe_keyboard(),
            parse_mode='Markdown',
        )

    if not already_active:
        try:
            from . import emails

            emails.subscription_approved(subscription)
        except Exception as exc:
            logger.error('Approval email failed: %s', exc)
    return True


def reject_subscription(subscription: Subscription, reviewed_by=None, note: str = '') -> bool:
    subscription.status = Subscription.STATUS_REJECTED
    subscription.reviewed_by = reviewed_by
    subscription.reviewed_at = timezone.now()
    if note:
        subscription.review_note = note
    subscription.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])

    chat_id = subscription.telegram_chat_id or resolve_chat_id(subscription.user)
    if chat_id:
        send_to_user(
            chat_id,
            "\u274C *Payment not approved*\n\n"
            + (note or 'Your payment could not be verified. Please contact support.')
            + "\n\nIf you believe this is a mistake, reply with your transaction reference.",
        )

    try:
        from . import emails

        emails.subscription_rejected(subscription)
    except Exception as exc:
        logger.error('Rejection email failed: %s', exc)
    return True


def has_active_subscription(user) -> bool:
    return Subscription.objects.active().filter(user=user).exists()


def record_application(post: ChannelPost, user) -> PostApplication:
    """Create (or fetch) an application, keeping the unique constraint safe."""
    application, _ = PostApplication.objects.get_or_create(
        post=post, applicant=user, defaults={'status': PostApplication.STATUS_SUBMITTED}
    )
    # Let the employer know, but never let a mail failure break the tap.
    try:
        from . import emails

        emails.application_received(application, post)
    except Exception as exc:
        logger.error('Applicant email failed: %s', exc)
    return application
