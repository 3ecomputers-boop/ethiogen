"""
Email notifications.

Telegram is the primary channel, but people miss messages. Every
notification is sent defensively: a mail failure must never roll back the
action that triggered it, so errors are logged and swallowed.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _sender() -> str:
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@ethiogen.com')


def _site() -> str:
    from . import config

    return config.website_url().rstrip('/')


def send(to, subject: str, body: str) -> bool:
    """Send one email. Returns True on success, False on failure."""
    if not to:
        return False
    # Honour a console backend in development instead of spamming a real inbox.
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    if 'console' in backend:
        logger.info('[email to %s] %s', to, subject)
        return True
    try:
        send_mail(
            subject=subject,
            message=strip_tags(body).strip(),
            from_email=_sender(),
            recipient_list=[to] if isinstance(to, str) else list(to),
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.error('Email to %s failed (%s): %s', to, subject, exc)
        return False


# ======================================================================
# Notifications
# ======================================================================
def application_received(application, post) -> bool:
    """Tell the employer someone applied."""
    employer = getattr(post, 'employer', None)
    if employer is None or not employer.email:
        return False
    return send(
        employer.email,
        f'New applicant: {post.title}',
        f'{application.applicant.get_full_name() or application.applicant} '
        f'applied to "{post.title}".\n\n'
        f'Status: {application.get_status_display()}\n'
        f'Review applicants: {_site()}/employers/\n',
    )


def receipt_received(subscription) -> bool:
    """Confirm to the payer that their receipt is being reviewed."""
    if not subscription.user.email:
        return False
    return send(
        subscription.user.email,
        f'Received your payment receipt — {subscription.plan_name}',
        f'Hi {subscription.user.first_name or "there"},\n\n'
        f'We received your payment receipt for {subscription.plan_name} '
        f'({subscription.amount} ETB).\n\n'
        f'Reference: {subscription.transaction_reference or "not provided"}\n\n'
        f'An admin will verify it shortly and you will get a message on '
        f'Telegram the moment it is approved.\n',
    )


def subscription_approved(subscription) -> bool:
    valid_until = ''
    if subscription.expires_at:
        from django.utils import timezone

        valid_until = timezone.localtime(subscription.expires_at).strftime('%d %b %Y')
    return send(
        subscription.user.email,
        f'Your Ethiogen subscription is active',
        f'Hi {subscription.user.first_name or "there"},\n\n'
        f'Your payment for {subscription.plan_name} has been approved.\n'
        f'Amount: {subscription.amount} ETB\n'
        + (f'Valid until: {valid_until}\n' if valid_until else '')
        + f'\nYou can now Apply to any post in the channel: {_site()}/\n',
    )


def subscription_rejected(subscription) -> bool:
    note = subscription.review_note or 'Your payment could not be verified.'
    return send(
        subscription.user.email,
        'Ethiogen subscription — payment not approved',
        f'Hi {subscription.user.first_name or "there"},\n\n'
        f'{note}\n\n'
        f'If you believe this is a mistake, reply with your transaction '
        f'reference and we will take another look.\n',
    )


def new_post_for_you(user, post) -> bool:
    """Email fallback for a matched alert (only sent in digest mode)."""
    if not user.email:
        return False
    link = post.source_url or f'{_site()}/'
    return send(
        user.email,
        f'New for you: {post.title}',
        f'{post.title}\n'
        + (f'{post.company}\n' if post.company else '')
        + (f'{post.location}\n' if post.location else '')
        + (f'\n{post.body}\n' if post.body else '')
        + f'\nApply here: {link}\n',
    )
