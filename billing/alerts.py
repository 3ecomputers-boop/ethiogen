"""
Job alerts.

A paid subscription has to be worth something, so new posts are pushed to
subscribers. Each subscriber picks how they want to hear about them:

    immediate  every new post, as soon as it is published
    digest     one summary per day (see the send_digest command)
    matched    only posts whose category/location/skills match their profile

Telegram rate-limits bulk sends, so delivery goes through a small
de-duplicating queue: each (user, post) pair is attempted at most once, and
failures are retried rather than dropped.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.db import models
from django.utils import timezone

from .models import ChannelPost, Subscription
from .services import send_to_user, target_chat_id

logger = logging.getLogger(__name__)

# Telegram allows ~30 messages/second to distinct users. Keep a small gap
# between sends so a large fan-out does not trip flood control.
SEND_DELAY_SECONDS = 0.05
BATCH_LIMIT = 500


# ======================================================================
# Who should hear about this post?
# ======================================================================
def active_alert_subscriptions(extra=None) -> models.QuerySet:
    """Active, un-muted subscriptions that can receive alerts."""
    qs = Subscription.objects.active().exclude(
        telegram_chat_id=None
    ).exclude(alerts_muted=True)
    if extra is not None:
        qs = qs.extra(where=extra)
    return qs.select_related('user')


def _profile_for(user):
    """Return a JobSeekerProfile for the user, or None."""
    return getattr(user, 'job_seeker_profile', None)


def _tokenise(value: str) -> set:
    return {t for t in re.split(r'[^a-z0-9+#.]+', (value or '').lower()) if len(t) > 2}


def post_matches_profile(post: ChannelPost, user) -> bool:
    """
    Does this post look relevant to the user?

    Deliberately generous: a post is 'matched' when we have enough signal
    and something overlaps. When the profile is thin we fall back to True
    rather than silently dropping every alert.
    """
    profile = _profile_for(user)
    if profile is None:
        return True

    haystack = ' '.join(filter(None, [post.title, post.body, post.company,
                                      post.location, post.category_tag]))
    haystack_tokens = _tokenise(haystack)

    signals = 0
    matched = False

    # Location
    location = (getattr(profile, 'city', '') or getattr(profile, 'country', '') or '')
    if location and post.location:
        signals += 1
        if location.strip().lower() in post.location.lower():
            matched = True

    # Skills
    skills = profile.skills if isinstance(getattr(profile, 'skills', None), list) else []
    if skills and post.category_tag:
        signals += 1
        wanted = set()
        for skill in skills:
            wanted |= _tokenise(str(skill))
        if wanted & _tokenise(post.category_tag):
            matched = True

    # Title / profession
    profession = getattr(profile, 'title', '') or ''
    if profession:
        signals += 1
        if _tokenise(profession) & haystack_tokens:
            matched = True

    # Too little profile data to judge: do not suppress alerts.
    if signals == 0:
        return True
    return matched


def recipients_for(post: ChannelPost) -> list:
    """
    Subscriptions that should receive an immediate alert for this post.

    Covers the 'immediate' and 'matched' modes; 'digest' is handled
    separately by the send_digest command.
    """
    out = []
    for subscription in active_alert_subscriptions():
        if subscription.alert_mode == Subscription.ALERT_DIGEST:
            continue
        if subscription.alert_mode == Subscription.ALERT_MATCHED:
            if not post_matches_profile(post, subscription.user):
                continue
        out.append(subscription)
    return out


def digest_recipients(hour: int = None) -> list:
    """Digest-mode subscriptions whose digest is due."""
    out = []
    for subscription in active_alert_subscriptions():
        if subscription.alert_mode != Subscription.ALERT_DIGEST:
            continue
        if hour is not None and subscription.digest_hour != hour:
            continue
        out.append(subscription)
    return out


# ======================================================================
# Messaging
# ======================================================================
def post_alert_text(post: ChannelPost) -> str:
    header = {
        ChannelPost.KIND_JOB: '\U0001F4CD *New job*',
        ChannelPost.KIND_TENDER: '\U0001F4E6 *New tender*',
    }.get(post.kind, '\U0001F4E2 *New post*')

    lines = [header, '', f"*{post.title}*"]
    if post.company:
        lines.append(f"\U0001F3E2 {post.company}")
    if post.location:
        lines.append(f"\U0001F4CD {post.location}")
    if post.salary:
        lines.append(f"\U0001F4B0 {post.salary}")
    if post.deadline:
        lines.append(
            f"\U0001F552 Deadline: {timezone.localtime(post.deadline):%d %b %Y}"
        )
    if post.body:
        body = post.body if len(post.body) <= 600 else post.body[:600] + '…'
        lines += ['', body]
    lines += ['', 'Tap below to apply.']
    return '\n'.join(lines)


def send_immediate_alerts(post: ChannelPost, dry_run: bool = False) -> dict:
    """
    Push a newly published post to immediate/matched subscribers.

    De-duplicates per (subscription, post) so a double publish does not
    message the same person twice.
    """
    import time

    from .models import AlertDelivery

    recipients = recipients_for(post)
    sent = skipped = failed = 0

    for subscription in recipients:
        if AlertDelivery.objects.filter(
            subscription=subscription, post=post, ok=True
        ).exists():
            skipped += 1
            continue
        if dry_run:
            sent += 1
            continue

        ok = send_to_user(
            subscription.telegram_chat_id,
            post_alert_text(post),
            reply_markup=_keyboard_for(post),
        )
        AlertDelivery.objects.create(
            subscription=subscription, post=post, ok=ok
        )
        if ok:
            sent += 1
            time.sleep(SEND_DELAY_SECONDS)
        else:
            failed += 1

    post.alerted_at = timezone.now()
    post.save(update_fields=['alerted_at'])

    logger.info(
        'Alerts for post %s: sent=%s skipped=%s failed=%s',
        post.pk, sent, skipped, failed,
    )
    return {'sent': sent, 'skipped': skipped, 'failed': failed,
            'recipients': len(recipients)}


def _keyboard_for(post: ChannelPost):
    from bot.telegram_bridge import build_post_keyboard

    return build_post_keyboard(post)


def send_digests(hour: int = None, dry_run: bool = False,
                 lookback_hours: int = 24) -> dict:
    """
    Send one summary to digest subscribers.

    Posts published in the last `lookback_hours` that the subscriber has
    not already been alerted about individually.
    """
    import time

    from .models import AlertDelivery

    since = timezone.now() - timedelta(hours=lookback_hours)
    posts = list(
        ChannelPost.objects.filter(
            status=ChannelPost.STATUS_PUBLISHED, published_at__gte=since
        ).order_by('-published_at')[:50]
    )

    sent = failed = empty = 0
    for subscription in digest_recipients(hour=hour):
        seen = set(
            AlertDelivery.objects
            .filter(subscription=subscription, ok=True)
            .values_list('post_id', flat=True)
        )
        relevant = [p for p in posts if p.pk not in seen][:10]
        if not relevant:
            empty += 1
            continue

        if dry_run:
            sent += 1
            continue

        lines = [
            f"\U0001F4CB *Your Ethiogen digest* — {len(relevant)} new post"
            f"{'s' if len(relevant) != 1 else ''}\n",
        ]
        for post in relevant:
            lines.append(f"\u2022 *{post.title}*")
            detail = [d for d in (post.company, post.location, post.salary) if d]
            if detail:
                lines.append(f"   {' · '.join(detail)}")
        lines.append('\nOpen Ethiogen to apply.')

        ok = send_to_user(subscription.telegram_chat_id, '\n'.join(lines))
        for post in relevant:
            AlertDelivery.objects.create(
                subscription=subscription, post=post, ok=ok
            )
        if ok:
            sent += 1
            time.sleep(SEND_DELAY_SECONDS)
        else:
            failed += 1

    return {'sent': sent, 'failed': failed, 'no_new_posts': empty,
            'posts_in_window': len(posts)}


def alert_stats() -> dict:
    """Counts for the admin dashboard."""
    # Count muted from the full active set: active_alert_subscriptions()
    # already excludes muted rows, so filtering that again is always 0.
    active = Subscription.objects.active().exclude(telegram_chat_id=None)
    live = active.filter(alerts_muted=False)
    return {
        'active': live.count(),
        'immediate': live.filter(alert_mode=Subscription.ALERT_IMMEDIATE).count(),
        'digest': live.filter(alert_mode=Subscription.ALERT_DIGEST).count(),
        'matched': live.filter(alert_mode=Subscription.ALERT_MATCHED).count(),
        'muted': active.filter(alerts_muted=True).count(),
    }
