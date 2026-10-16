"""
Models for the Telegram channel distribution + subscription/payment flow.

A ChannelPost is a message the bot publishes to the Telegram channel/group.
It carries inline buttons so viewers can Apply (job seekers) or Subscribe
(anyone). Subscriptions are paid for either through Chapa or by manual
transfer with a receipt, and are approved from the Django admin.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class IntegrationSettings(models.Model):
    """
    Singleton row holding every external integration setting.

    Values here take precedence over settings.py / environment variables, so
    an administrator can change the Telegram token, channel, group, Chapa and
    Telebirr details from the Django admin without editing .env or
    restarting the bot.

    The bot process re-reads this row periodically (see billing/config.py),
    so changes take effect without a restart.
    """

    SINGLETON_NAME = 'default'

    # ----- Telegram -----
    telegram_bot_token = models.CharField(
        'Bot token', max_length=120, blank=True,
        help_text='From @BotFather. Leave blank to fall back to TELEGRAM_BOT_TOKEN.',
    )
    telegram_bot_username = models.CharField(max_length=120, blank=True)
    telegram_channel_id = models.CharField(
        'Channel ID', max_length=64, blank=True,
        help_text='Numeric ID, e.g. -1003795541703. The bot must be an admin here.',
    )
    telegram_channel_username = models.CharField(
        max_length=120, blank=True, help_text='Without the leading @'
    )
    telegram_group_id = models.CharField(
        'Group ID', max_length=64, blank=True,
        help_text='Optional discussion group, used by the /joingroup command.',
    )
    telegram_admin_ids = models.TextField(
        'Admin Telegram IDs', blank=True,
        help_text='Comma or newline separated. These users may run /scrape and /tenders.',
    )
    telegram_website_url = models.URLField(blank=True, default='https://ethiogen.com')

    # ----- Chapa -----
    chapa_enabled = models.BooleanField(default=False)
    chapa_public_key = models.CharField(max_length=120, blank=True)
    chapa_secret_key = models.CharField(
        'Secret key', max_length=120, blank=True,
        help_text='Leave blank to run in manual-only mode.',
    )
    chapa_api_base = models.CharField(
        max_length=200, blank=True, default='https://api.chapa.co/v1'
    )
    chapa_auto_approve = models.BooleanField(
        default=True,
        help_text='Activate immediately when Chapa reports a successful payment. '
                  'Uncheck to review every payment in this admin.',
    )
    chapa_webhook_url = models.URLField(
        blank=True,
        help_text='Leave blank to derive from site URL + /billing/chapa/webhook/.',
    )

    # ----- Telebirr -----
    telebirr_enabled = models.BooleanField(
        default=True, help_text='Show the Telebirr transfer option.'
    )
    telebirr_name = models.CharField(max_length=160, blank=True)
    telebirr_phone = models.CharField(max_length=40, blank=True)
    telebirr_api_base = models.CharField(
        'Telebirr gateway URL', max_length=200, blank=True,
        help_text='Telebirr has no public merchant API. If you collect payment through '
                  'an aggregator or bank gateway, put its base URL here; otherwise '
                  'leave blank for manual transfer only.',
    )
    telebirr_api_key = models.CharField('Gateway API key', max_length=200, blank=True)
    telebirr_merchant_id = models.CharField(max_length=120, blank=True)
    telebirr_return_url = models.URLField(blank=True)

    # ----- Bank transfer -----
    bank_enabled = models.BooleanField(default=True)
    bank_name = models.CharField(max_length=160, blank=True)
    bank_account_name = models.CharField(max_length=160, blank=True)
    bank_account_number = models.CharField(max_length=64, blank=True)

    # ----- Subscription defaults -----
    currency = models.CharField(max_length=10, default='ETB')
    subscription_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('500.00')
    )
    subscription_days = models.PositiveIntegerField(default=30)
    site_url = models.URLField(default='https://ethiogen.com')
    payment_instructions = models.TextField(
        blank=True,
        help_text='Extra text shown to the user before they upload a receipt.',
    )
    notes = models.TextField(blank=True)

    # ----- Branding -----
    logo_image = models.ImageField(
        upload_to='branding/', blank=True, null=True,
        help_text='Upload the logo once here. Every logo in the site is drawn '
                  'from this file, so replacing it updates the header, footer, '
                  'dashboards and favicon together.',
    )
    logo_wordmark = models.CharField(
        max_length=60, default='Ethiogen',
        help_text='Caption shown under the logo image.',
    )
    logo_show_caption = models.BooleanField(
        default=True, help_text='Show the wordmark under the logo image.'
    )
    logo_height_px = models.PositiveIntegerField(
        default=48, help_text='Rendered height of the logo image, in pixels.'
    )
    favicon_image = models.ImageField(
        upload_to='branding/', blank=True, null=True,
        help_text='Optional square favicon. Falls back to the main logo.',
    )

    # ----- Facebook page -----
    facebook_enabled = models.BooleanField(
        default=False, help_text='Allow publishing posts to the Facebook page.'
    )
    facebook_page_id = models.CharField(
        'Page ID', max_length=64, blank=True,
        help_text='From your page URL: facebook.com/YOURPAGE -> Page ID, or '
                  'use Graph API Explorer. Usually a long numeric ID.',
    )
    facebook_page_name = models.CharField(max_length=160, blank=True)
    facebook_page_access_token = models.CharField(
        'Page access token', max_length=400, blank=True,
        help_text='Never the App Secret. Generate with: '
                  'GET /me/accounts?fields=id,name,access_token',
    )
    facebook_api_version = models.CharField(
        max_length=10, blank=True, default='v21.0',
        help_text='Graph API version, e.g. v21.0',
    )
    facebook_default_link = models.URLField(
        blank=True,
        help_text='Optional fallback link when a post has no source_url.',
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='billing_settings_updates',
    )

    class Meta:
        verbose_name = 'Integration settings'
        verbose_name_plural = 'Integration settings'

    def __str__(self):
        return f'Integration settings ({self.SINGLETON_NAME})'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover - admin blocks this
        pass

    @classmethod
    def load(cls):
        """Return the settings row, or None if it has never been saved."""
        try:
            return cls.objects.filter(pk=1).first()
        except Exception:
            return None

    @property
    def telegram_admin_id_list(self) -> list:
        raw = (self.telegram_admin_ids or '').replace('\n', ',').replace(' ', ',')
        return [int(v.strip()) for v in raw.split(',') if v.strip().isdigit()]

    @property
    def is_chapa_live(self) -> bool:
        return bool(self.chapa_enabled and self.chapa_secret_key)

    @property
    def resolved_chapa_webhook(self) -> str:
        if self.chapa_webhook_url:
            return self.chapa_webhook_url
        return f"{str(self.site_url).rstrip('/')}/billing/chapa/webhook/"


class ChannelPost(models.Model):
    """A message published to the Telegram channel/group."""

    KIND_JOB = 'job'
    KIND_TENDER = 'tender'
    KIND_GENERAL = 'general'
    KIND_CHOICES = [
        (KIND_JOB, 'Job'),
        (KIND_TENDER, 'Tender'),
        (KIND_GENERAL, 'General'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_FAILED, 'Publish failed'),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_JOB)
    title = models.CharField(max_length=255)
    body = models.TextField(
        blank=True,
        help_text='Markdown is supported. Leave empty to auto-format from the title.',
    )
    source_url = models.URLField(
        blank=True,
        help_text='Link behind the "View Details" button and the /apply reference.',
    )
    company = models.CharField(max_length=255, blank=True)
    category_tag = models.CharField(
        max_length=120, blank=True,
        help_text='Short category/skill tag, e.g. "Django, Python". Used to '
                  'match posts against a subscriber profile.',
    )
    location = models.CharField(max_length=255, blank=True)
    salary = models.CharField(max_length=120, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)

    # Which inline buttons to attach when publishing.
    show_apply = models.BooleanField(
        default=True,
        help_text='Attach an "Apply Now" button (job posts).',
    )
    show_subscribe = models.BooleanField(
        default=True,
        help_text='Attach a "Subscribe" button.',
    )

    # Telegram bookkeeping.
    telegram_chat_id = models.CharField(max_length=64, blank=True)
    telegram_message_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True
    )
    publish_error = models.TextField(blank=True)

    # Facebook delivery bookkeeping.
    facebook_posted = models.BooleanField(default=False, db_index=True)
    facebook_post_id = models.CharField(max_length=120, blank=True)
    facebook_permalink = models.URLField(blank=True)
    facebook_posted_at = models.DateTimeField(null=True, blank=True)
    facebook_error = models.TextField(blank=True)

    # Set when an employer posts this from the mini app, so they can manage
    # it (and see applicants) without touching the Django admin.
    employer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employer_posts',
    )
    organization = models.ForeignKey(
        'tenants.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='channel_posts',
    )
    job_post = models.ForeignKey(
        'jobs.JobPost',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='channel_posts',
    )
    alerted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When subscribers were last alerted about this post.',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='channel_posts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Channel post'
        verbose_name_plural = 'Channel posts'

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.title}"

    def build_text(self) -> str:
        """Render the Markdown body actually sent to Telegram."""
        header = {
            self.KIND_JOB: '\U0001F4CD *JOB OPENING*',
            self.KIND_TENDER: '\U0001F4E6 *TENDER NOTICE*',
            self.KIND_GENERAL: '\U0001F4E2 *ETHIOGEN UPDATE*',
        }.get(self.kind, '\U0001F4E2 *ETHIOGEN UPDATE*')

        lines = [header, '', f"*{self.title}*"]

        if self.company:
            lines.append(f"\U0001F3E2 {self.company}")
        if self.location:
            lines.append(f"\U0001F4CD {self.location}")
        if self.salary:
            lines.append(f"\U0001F4B0 {self.salary}")
        if self.deadline:
            lines.append(
                f"\U0001F552 Deadline: {timezone.localtime(self.deadline):%d %b %Y, %H:%M}"
            )

        if self.body:
            lines += ['', self.body]
        if self.source_url:
            lines += ['', f"\U0001F517 [View Details]({self.source_url})"]

        return '\n'.join(lines)


class SubscriptionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(
            status=Subscription.STATUS_ACTIVE,
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        )

    def pending_review(self):
        return self.filter(status=Subscription.STATUS_PENDING_REVIEW)


class Subscription(models.Model):
    """A user's request to unlock channel content, and its payment state."""

    STATUS_AWAITING_PAYMENT = 'awaiting_payment'
    STATUS_PENDING_REVIEW = 'pending_review'
    STATUS_ACTIVE = 'active'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_AWAITING_PAYMENT, 'Awaiting payment'),
        (STATUS_PENDING_REVIEW, 'Pending review'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    PAYMENT_CHAPA = 'chapa'
    PAYMENT_TELEBIRR = 'telebirr'
    PAYMENT_BANK = 'bank'
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_CHAPA, 'Chapa (card / telebirr)'),
        (PAYMENT_TELEBIRR, 'Telebirr transfer'),
        (PAYMENT_BANK, 'Bank transfer'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='billing_subscriptions',
    )
    # Cached so approval can DM the user even if the TelegramProfile is gone.
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    plan_name = models.CharField(max_length=120, default='Channel Subscription')
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    duration_days = models.PositiveIntegerField(default=30)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_AWAITING_PAYMENT, db_index=True
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True
    )

    # Chapa
    chapa_reference = models.CharField(max_length=120, blank=True, db_index=True)
    chapa_checkout_url = models.URLField(blank=True)
    chapa_payload = models.JSONField(blank=True, null=True)

    # Manual transfer
    receipt_file = models.ImageField(upload_to='billing/receipts/%Y/%m/', null=True, blank=True)
    transaction_reference = models.CharField(max_length=120, blank=True)
    payer_note = models.TextField(blank=True)

    # Review
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='billing_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ----- How this subscriber wants to hear about new posts -----
    ALERT_IMMEDIATE = 'immediate'
    ALERT_DIGEST = 'digest'
    ALERT_MATCHED = 'matched'
    ALERT_MODE_CHOICES = [
        (ALERT_IMMEDIATE, 'Every new post, immediately'),
        (ALERT_DIGEST, 'One daily digest'),
        (ALERT_MATCHED, 'Only posts matching my profile'),
    ]
    alert_mode = models.CharField(
        max_length=20, choices=ALERT_MODE_CHOICES, default=ALERT_IMMEDIATE,
    )
    digest_hour = models.PositiveSmallIntegerField(
        default=8,
        help_text='Local hour (0-23) the daily digest is sent. Only used by '
                  'the "One daily digest" mode.',
    )
    alerts_muted = models.BooleanField(
        default=False, help_text='Pause all job alerts without cancelling.'
    )

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'

    def __str__(self):
        return f'{self.user} — {self.plan_name} ({self.get_status_display()})'

    @property
    def is_active(self) -> bool:
        return (
            self.status == self.STATUS_ACTIVE
            and (self.expires_at is None or self.expires_at > timezone.now())
        )

    @property
    def needs_review(self) -> bool:
        return self.status == self.STATUS_PENDING_REVIEW


class AlertDelivery(models.Model):
    """
    One row per (subscription, post) alert attempt.

    Exists so a post is never announced twice to the same person, and so
    failed sends can be inspected or retried.
    """

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name='deliveries'
    )
    post = models.ForeignKey(
        ChannelPost, on_delete=models.CASCADE, related_name='deliveries'
    )
    ok = models.BooleanField(default=False)
    error = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('subscription', 'post')]
        verbose_name = 'Alert delivery'
        verbose_name_plural = 'Alert deliveries'

    def __str__(self):
        mark = 'ok' if self.ok else 'failed'
        return f'{self.subscription_id} <- {self.post_id} ({mark})'


class PostApplication(models.Model):
    """A job seeker applying to a ChannelPost via the inline Apply button."""

    STATUS_SUBMITTED = 'submitted'
    STATUS_REVIEWING = 'reviewing'
    STATUS_SHORTLISTED = 'shortlisted'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_REVIEWING, 'Reviewing'),
        (STATUS_SHORTLISTED, 'Shortlisted'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    post = models.ForeignKey(
        ChannelPost, on_delete=models.CASCADE, related_name='applications'
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_applications',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True
    )
    cover_note = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('post', 'applicant')]
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'

    def __str__(self):
        return f'{self.applicant} → {self.post.title[:40]}'
