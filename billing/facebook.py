"""
Facebook Page publishing (Graph API).

Setup, once:

  1. Create a Meta app (Business / "Other") and add the "pages_manage_posts"
     permission, then get a *user* access token from Graph API Explorer.
  2. Exchange it for a page token:
         GET /me/accounts?fields=id,name,access_token&access_token=<USER_TOKEN>
     The `access_token` for your page in that response is what goes into
     "Facebook -> Page access token" in the admin.
  3. Paste the page `id` into "Page ID".

The page token is a long-lived secret, so it is stored like the Telegram
token: never rendered in the admin, and superuser-only.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from . import config

logger = logging.getLogger(__name__)

GRAPH_BASE = 'https://graph.facebook.com'
REQUEST_TIMEOUT = 30


# ======================================================================
# Config helpers
# ======================================================================
def enabled() -> bool:
    row = config.get_row()
    if row is not None:
        return bool(row.facebook_enabled and row.facebook_page_id
                    and row.facebook_page_access_token)
    return False


def page_id() -> str:
    return str(config._pick('facebook_page_id', 'FACEBOOK_PAGE_ID', '') or '').strip()


def page_access_token() -> str:
    return str(
        config._pick('facebook_page_access_token', 'FACEBOOK_PAGE_ACCESS_TOKEN', '') or ''
    ).strip()


def api_version() -> str:
    version = str(
        config._pick('facebook_api_version', 'FACEBOOK_API_VERSION', 'v21.0') or 'v21.0'
    ).strip()
    return version.lstrip('/')


def default_link() -> str:
    return str(config._pick('facebook_default_link', 'FACEBOOK_DEFAULT_LINK', '') or '')


def is_configured() -> bool:
    """True when enough is present to attempt a publish."""
    return bool(enabled() and page_id() and page_access_token())


# ======================================================================
# Graph API plumbing
# ======================================================================
def _graph_url(path: str) -> str:
    return f'{GRAPH_BASE}/{api_version()}/{path.lstrip("/")}'


def _request(method: str, path: str, token: str, **params) -> dict:
    """
    Call a Graph API endpoint.

    Returns {'ok': True, 'data': {...}} or {'ok': False, 'error': '...'}.
    """
    if not token:
        return {'ok': False, 'error': 'No access token configured.'}

    payload = dict(params)
    payload['access_token'] = token

    try:
        response = requests.request(
            method, _graph_url(path), params=payload, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        logger.error('Facebook %s %s failed: %s', method, path, exc)
        return {'ok': False, 'error': f'network error: {exc}'}
    except Exception as exc:
        # This runs inside an admin action, so never let an unexpected error
        # (bad payload, encoding problem, unexpected exception type) escape.
        logger.exception('Facebook %s %s raised', method, path)
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}

    try:
        data = response.json()
    except ValueError:
        return {
            'ok': False,
            'error': f'HTTP {response.status_code} with a non-JSON body',
        }

    if not data.get('id') and 'error' in data:
        err = data['error']
        message = err.get('message', 'unknown error') if isinstance(err, dict) else str(err)
        code = err.get('code') if isinstance(err, dict) else None
        sub = err.get('error_subcode') if isinstance(err, dict) else None
        detail = f'{message} (code={code}, subcode={sub})' if code else message
        return {'ok': False, 'error': detail}

    if response.status_code >= 400:
        return {'ok': False, 'error': f'HTTP {response.status_code}'}

    return {'ok': True, 'data': data}


def page_info() -> dict:
    """Fetch the page's name and id to confirm the credentials work."""
    result = _request('GET', page_id(), page_access_token(), fields='id,name,link')
    if not result['ok']:
        return result
    return {
        'ok': True,
        'id': result['data'].get('id', ''),
        'name': result['data'].get('name', ''),
        'link': result['data'].get('link', ''),
    }


# ======================================================================
# Publishing
# ======================================================================
def build_message(post) -> str:
    """Plain-text caption for a ChannelPost, shared with Facebook."""
    lines = []
    if post.title:
        lines.append(post.title)
        lines.append('')
    if post.company:
        lines.append(f'Company: {post.company}')
    if post.location:
        lines.append(f'Location: {post.location}')
    if post.salary:
        lines.append(f'Salary: {post.salary}')
    if post.body:
        lines += ['', post.body]
    lines += ['', 'Read the full post and apply on Ethiogen.']
    return '\n'.join(lines)


def post_to_facebook(post) -> dict:
    """
    Publish a ChannelPost to the configured Facebook page.

    Returns {'ok': True, 'post_id': ..., 'permalink': ...} or
    {'ok': False, 'error': '...'}. Never raises.
    """
    if not is_configured():
        return {
            'ok': False,
            'error': 'Facebook is not configured. Enable it and fill in the '
                     'page ID and page access token under '
                     'Billing -> Integration settings.',
        }

    link = post.source_url or default_link()
    params = {'message': build_message(post)}
    if link:
        params['link'] = link

    result = _request('POST', f'{page_id()}/feed', page_access_token(), **params)
    if not result['ok']:
        return result

    post_id = result['data'].get('id', '')
    permalink = ''
    if post_id:
        detail = _request('GET', post_id, page_access_token(), fields='permalink_url')
        if detail['ok']:
            permalink = detail['data'].get('permalink_url', '')

    # A photo post looks far better on a page feed than a bare text/link post.
    image_url = _post_image_url(post)
    if image_url:
        photo = _request(
            'POST', f'{page_id()}/photos', page_access_token(),
            url=image_url, caption=build_message(post),
        )
        if photo['ok']:
            post_id = photo['data'].get('post_id') or photo['data'].get('id', post_id)
            if photo['data'].get('permalink_url'):
                permalink = photo['data']['permalink_url']

    return {'ok': True, 'post_id': post_id, 'permalink': permalink}


def _post_image_url(post) -> str:
    """A publicly reachable image for the post, if the logo is set."""
    row = config.get_row()
    if row is not None and getattr(row, 'logo_image', None):
        try:
            return row.logo_image.url
        except Exception:
            return ''
    return ''


def publish_and_record(post) -> dict:
    """Publish to Facebook and store the outcome on the post."""
    result = post_to_facebook(post)
    if result.get('ok'):
        post.facebook_posted = True
        post.facebook_post_id = result.get('post_id', '') or ''
        post.facebook_permalink = result.get('permalink', '') or ''
        post.facebook_error = ''
        from django.utils import timezone

        post.facebook_posted_at = timezone.now()
    else:
        post.facebook_posted = False
        post.facebook_error = result.get('error', 'unknown error')
    post.save(
        update_fields=[
            'facebook_posted', 'facebook_post_id', 'facebook_permalink',
            'facebook_posted_at', 'facebook_error',
        ]
    )
    return result
