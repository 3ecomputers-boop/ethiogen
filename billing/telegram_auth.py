"""
Telegram Web App authentication.

The mini app runs inside Telegram, which passes a signed `initData` blob.
Telegram signs it with an HMAC derived from the bot token, so the client
cannot forge a user id.

Verification, per https://core.telegram.org/bots/webapps#validating-data:
    1. read the auth_key that follows the "hash=" field, sort the rest
       alphabetically, drop "hash", join as "key=value" with \n
    2. secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
    3. computed = HMAC_SHA256(key=secret, msg=data_check_string)
    4. compare with the hash we were given, and check auth_date freshness

There is also a second layer: call getMe-ish info back from Telegram via
answerWebAppQuery is not needed, but we do validate the auth_date so a
leaked initData string cannot be replayed forever.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Optional

from django.conf import settings
from django.contrib.auth.hashers import make_password

# Telegram initData older than this is rejected (24 hours).
MAX_AUTH_AGE_SECONDS = 24 * 60 * 60


def _bot_token() -> str:
    from . import config

    return config.telegram_token()


def _parse_init_data(init_data: str) -> dict:
    """Turn the urlencoded blob into a dict, last value wins."""
    pairs = {}
    for chunk in (init_data or '').split('&'):
        if not chunk:
            continue
        key, _, value = chunk.partition('=')
        pairs[key] = value
    return pairs


def _decode(value: str) -> str:
    """URL-decode a single component."""
    from urllib.parse import unquote

    return unquote(value)


def verify_init_data(init_data: str, max_age: int = MAX_AUTH_AGE_SECONDS) -> dict:
    """
    Validate a Telegram initData string.

    Returns {'ok': True, 'user': {...}} on success, or
    {'ok': False, 'error': '...'} with a human-readable reason.
    """
    if not init_data:
        return {'ok': False, 'error': 'initData is empty'}

    token = _bot_token()
    if not token:
        return {'ok': False, 'error': 'bot token is not configured'}

    pairs = _parse_init_data(init_data)
    received_hash = pairs.pop('hash', None)
    if not received_hash:
        return {'ok': False, 'error': 'initData has no hash'}

    # data_check_string: remaining keys, sorted, excluding 'signature'
    pairs.pop('signature', None)
    check_string = '\n'.join(
        f'{key}={value}' for key, value in sorted(pairs.items())
    )

    secret_key = hmac.new(
        b'WebAppData', token.encode('utf-8'), hashlib.sha256
    ).digest()
    computed = hmac.new(
        secret_key, check_string.encode('utf-8'), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        return {'ok': False, 'error': 'signature mismatch'}

    # Freshness
    try:
        auth_date = int(pairs.get('auth_date', '0'))
    except (TypeError, ValueError):
        return {'ok': False, 'error': 'auth_date is not a number'}
    if auth_date and max_age and (time.time() - auth_date) > max_age:
        return {'ok': False, 'error': 'initData has expired, reopen the app'}

    raw_user = pairs.get('user')
    if not raw_user:
        return {'ok': False, 'error': 'initData has no user'}
    try:
        user = json.loads(_decode(raw_user))
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'user payload is not valid JSON'}

    return {'ok': True, 'user': user, 'auth_date': auth_date,
            'start_param': _decode(pairs.get('start_param', ''))}


def is_telegram_context() -> bool:
    """True when the server looks like it is being viewed inside Telegram."""
    agent = ''
    try:
        from django.http import request as _request

        if _request.current_request:
            agent = _request.current_request.META.get('HTTP_USER_AGENT', '')
    except Exception:
        pass
    return 'TelegramBot' in agent


def upsert_user_from_telegram(telegram_user: dict):
    """
    Find or create the Django user behind a verified Telegram identity.

    Returns (user, created).
    """
    from django.contrib.auth import get_user_model

    from jobs.models import TelegramProfile

    User = get_user_model()
    tg_id = telegram_user.get('id')
    if not tg_id:
        raise ValueError('Telegram user has no id')

    profile = TelegramProfile.objects.filter(chat_id=str(tg_id)).first()
    if profile:
        # Keep the display name fresh.
        changed = []
        first = telegram_user.get('first_name') or ''
        last = telegram_user.get('last_name') or ''
        username = telegram_user.get('username') or ''
        if first and profile.user.first_name != first:
            profile.user.first_name = first
            changed.append('first_name')
        if last and profile.user.last_name != last:
            profile.user.last_name = last
            changed.append('last_name')
        if username and profile.username != username:
            profile.username = username
            changed.append('username')
        if changed:
            profile.save(update_fields=['username'])
            profile.user.save(update_fields=changed)
        return profile.user, False

    import re

    base = (telegram_user.get('username')
            or f'tg_{tg_id}').strip()[:120]
    base = re.sub(r'[^A-Za-z0-9_.@+-]', '_', base) or f'tg_{tg_id}'

    user = User.objects.create_user(
        username=base,
        email='',
        # make_password(None) gives an unusable password: this account signs
        # in via Telegram initData, never with a password. The project's
        # custom UserManager has no make_random_password().
        password=make_password(None),
        first_name=telegram_user.get('first_name') or '',
        last_name=telegram_user.get('last_name') or '',
    )
    TelegramProfile.objects.create(
        user=user,
        chat_id=str(tg_id),
        username=telegram_user.get('username') or '',
    )
    return user, True
