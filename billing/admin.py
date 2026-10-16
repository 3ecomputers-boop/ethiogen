"""
Admin for the Telegram channel distribution + billing flow.

This is where staff:
  * configure the Telegram token / channel / group, Chapa and Telebirr details
  * compose a post and push it to the channel (with inline buttons)
  * review uploaded payment receipts and approve / reject
  * read the applications that came in through the Apply button
"""
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html, mark_safe
from django.utils.safestring import mark_safe

from . import config
from .models import (
    AlertDelivery,
    ChannelPost,
    IntegrationSettings,
    PostApplication,
    Subscription,
)
from .services import activate_subscription, publish_post, reject_subscription


# ======================================================================
# Integration settings (singleton)
# ======================================================================
SECRET_FIELDS = (
    'telegram_bot_token',
    'chapa_secret_key',
    'telebirr_api_key',
    'facebook_page_access_token',
)


def _incoming_or_saved(form, name):
    """Return the submitted value for a field, or the currently saved one."""
    if name in form.data:
        return form.data.get(name)
    instance = form.instance
    return getattr(instance, name, '') if instance and instance.pk else ''


class IntegrationSettingsForm(forms.ModelForm):
    """
    Render secret fields as password boxes.

    The stored value is never rendered. Leaving a secret box empty keeps the
    value already saved, so editing an unrelated field cannot wipe a token.
    """

    class Meta:
        model = IntegrationSettings
        fields = '__all__'
        widgets = {
            'telegram_admin_ids': forms.Textarea(attrs={'rows': 3}),
            'payment_instructions': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SECRET_FIELDS:
            if name not in self.fields:
                continue
            self.fields[name].widget = forms.PasswordInput(
                render_value=False, attrs={'autocomplete': 'new-password'}
            )
            self.fields[name].required = False
            if self.instance and getattr(self.instance, name, ''):
                self.fields[name].help_text = (
                    'A value is saved. Leave blank to keep it.'
                )
        for name in ('logo_image', 'favicon_image'):
            if name in self.fields:
                self.fields[name].required = False
                self.fields[name].widget = forms.ClearableFileInput(
                    attrs={'accept': 'image/*'}
                )

    def clean(self):
        cleaned = super().clean()
        for name in SECRET_FIELDS:
            if not cleaned.get(name) and self.instance and getattr(self.instance, name, ''):
                cleaned[name] = getattr(self.instance, name)

        if cleaned.get('chapa_enabled') and not cleaned.get('chapa_secret_key'):
            self.add_error(
                'chapa_secret_key',
                'Enter a secret key to enable Chapa, or untick Chapa to use '
                'manual transfer only.',
            )
        if cleaned.get('telebirr_enabled') and not _incoming_or_saved(self, 'telebirr_phone'):
            self.add_error(
                'telebirr_phone',
                'Enter the Telebirr number users transfer to, or untick Telebirr.',
            )
        if cleaned.get('bank_enabled') and not _incoming_or_saved(self, 'bank_account_number'):
            self.add_error(
                'bank_account_number',
                'Enter the account number users transfer to, or untick Bank transfer.',
            )
        if cleaned.get('facebook_enabled') and not (
            cleaned.get('facebook_page_id')
            or _incoming_or_saved(self, 'facebook_page_id')
        ):
            self.add_error(
                'facebook_page_id',
                'Enter the Facebook Page ID, or untick Facebook.',
            )
        if cleaned.get('facebook_enabled') and not cleaned.get('facebook_page_access_token'):
            self.add_error(
                'facebook_page_access_token',
                'Enter the page access token, or untick Facebook.',
            )
        return cleaned


@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(admin.ModelAdmin):
    """
    Single-row editor. Adding a second row or deleting the row is blocked,
    because the config layer always reads pk=1.
    """

    form = IntegrationSettingsForm
    change_form_template = 'admin/billing/integration_settings.html'

    fieldsets = (
        ('Telegram', {
            'description': 'The bot must be an administrator of the channel and '
                           'group for posting and inline buttons to work.',
            'fields': (
                'telegram_bot_token', 'telegram_bot_username',
                'telegram_channel_id', 'telegram_channel_username',
                'telegram_group_id', 'telegram_admin_ids',
                'telegram_website_url',
            ),
        }),
        ('Chapa', {
            'description': 'Leave Chapa disabled to collect payment by manual '
                           'transfer only.',
            'fields': (
                'chapa_enabled', 'chapa_public_key', 'chapa_secret_key',
                'chapa_api_base', 'chapa_auto_approve', 'chapa_webhook_url',
            ),
        }),
        ('Telebirr', {
            'description': 'Telebirr has no public merchant API. Fill in the phone '
                           'and name for manual transfers; fill the gateway fields '
                           'only if you collect payment through a provider.',
            'fields': (
                'telebirr_enabled', 'telebirr_name', 'telebirr_phone',
                'telebirr_api_base', 'telebirr_api_key', 'telebirr_merchant_id',
                'telebirr_return_url',
            ),
        }),
        ('Bank transfer', {
            'fields': (
                'bank_enabled', 'bank_name', 'bank_account_name',
                'bank_account_number',
            ),
        }),
        ('Subscription', {
            'fields': (
                'currency', 'subscription_price', 'subscription_days',
                'site_url', 'payment_instructions',
            ),
        }),
        ('Branding', {
            'description': 'Upload the logo once here and every logo on the site '
                           '(header, footer, dashboards, favicon) is drawn from it.',
            'fields': (
                'logo_image', 'favicon_image', 'logo_wordmark',
                'logo_show_caption', 'logo_height_px',
            ),
        }),
        ('Facebook page', {
            'description': (
                'Generate a page access token with: '
                'GET /me/accounts?fields=id,name,access_token (Graph API '
                'Explorer, with a user token that has pages_manage_posts).'
            ),
            'fields': (
                'facebook_enabled', 'facebook_page_id', 'facebook_page_name',
                'facebook_page_access_token', 'facebook_api_version',
                'facebook_default_link',
            ),
        }),
        ('Notes', {'classes': ('collapse',), 'fields': ('notes',)}),
        ('Audit', {
            'classes': ('collapse',),
            'fields': ('updated_at', 'updated_by'),
        }),
    )

    readonly_fields = ('updated_at', 'updated_by')

    # --- singleton enforcement -------------------------------------------
    def has_add_permission(self, request):
        return not IntegrationSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    # --- superuser only: this page holds live credentials ---------------
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        # Make the new values visible to the bot process immediately.
        config.invalidate_cache()

    def changelist_view(self, request, extra_context=None):
        # Send staff straight to the single settings row.
        if not IntegrationSettings.objects.filter(pk=1).exists():
            return super().changelist_view(request, extra_context)
        from django.urls import reverse
        from django.shortcuts import redirect

        return redirect(
            reverse('admin:billing_integrationsettings_change', args=(1,))
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('updated_by')

    # --- live diagnostics for the change form ----------------------------
    def configuration_report(self):
        config.invalidate_cache()
        rows = []
        for label, ok, detail in config.configuration_report():
            colour = '#16a34a' if ok else '#dc2626'
            rows.append(
                '<tr>'
                f'<td style="padding:5px 10px;border-bottom:1px solid #e5e7eb">{label}</td>'
                f'<td style="padding:5px 10px;border-bottom:1px solid #e5e7eb;'
                f'color:{colour};font-weight:700">{"OK" if ok else "MISSING"}</td>'
                f'<td style="padding:5px 10px;border-bottom:1px solid #e5e7eb">'
                f'{detail if detail else "-"}</td>'
                '</tr>'
            )
        # The inner call had no args, which Django 6 rejects. The rows are markup
        # we assemble above, so mark_safe is the correct tool here.
        return format_html(
            '<table style="width:100%;border-collapse:collapse;font-size:12px">'
            '{}</table>',
            mark_safe(''.join(rows)),
        )


class PostApplicationInline(admin.TabularInline):
    model = PostApplication
    extra = 0
    fields = ('applicant', 'status', 'created_at', 'admin_note')
    readonly_fields = ('applicant', 'created_at')
    autocomplete_fields = ('applicant',)
    ordering = ('-created_at',)


@admin.register(ChannelPost)
class ChannelPostAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'kind', 'status', 'show_apply', 'show_subscribe',
        'delivery', 'published_at', 'created_by',
    )
    list_filter = ('kind', 'status', 'show_apply', 'show_subscribe', 'facebook_posted')
    search_fields = ('title', 'body', 'company', 'location')
    list_editable = ()
    readonly_fields = (
        'telegram_message_id', 'telegram_chat_id', 'status',
        'published_at', 'publish_error', 'preview', 'created_at',
        'facebook_posted', 'facebook_post_id', 'facebook_permalink',
        'facebook_posted_at', 'facebook_error', 'created_at',
        'employer', 'job_post', 'alerted_at',
    )
    actions = (
        'action_publish',
        'action_publish_facebook',
        'action_publish_both',
        'action_unpublish_note',
    )
    inlines = (PostApplicationInline,)
    fieldsets = (
        (None, {'fields': ('kind', 'title', 'body', 'source_url', 'preview')}),
        ('Details', {
            'fields': ('company', 'location', 'salary', 'deadline'),
            'classes': ('collapse',),
        }),
        ('Inline buttons', {
            'description': (
                'These determine the buttons attached to the message when it is '
                'published to Telegram.'
            ),
            'fields': ('show_apply', 'show_subscribe'),
        }),
        ('Telegram', {
            'classes': ('collapse',),
            'fields': ('telegram_chat_id', 'telegram_message_id', 'status',
                       'published_at', 'publish_error'),
        }),
        ('Facebook', {
            'classes': ('collapse',),
            'fields': ('facebook_posted', 'facebook_post_id', 'facebook_permalink',
                       'facebook_posted_at', 'facebook_error'),
        }),
        ('Alerts', {
            'description': 'Set when subscribers were last notified about this post.',
            'classes': ('collapse',),
            'fields': ('alerted_at',),
        }),
        ('Audit', {'classes': ('collapse',), 'fields': ('created_by', 'created_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')

    @admin.display(description='Delivered')
    def delivery(self, obj):
        tg = (
            '<span style="color:#16a34a;font-weight:700">TG</span>'
            if obj.telegram_message_id
            else '<span style="color:#9ca3af">TG &mdash;</span>'
        )
        fb = (
            '<span style="color:#16a34a;font-weight:700">FB</span>'
            if obj.facebook_posted
            else '<span style="color:#9ca3af">FB &mdash;</span>'
        )
        return mark_safe(f'{tg} &nbsp;|&nbsp; {fb}')

    @admin.display(description='Message preview')
    def preview(self, obj):
        if not obj.pk:
            return '(save first)'
        return format_html(
            '<pre style="white-space:pre-wrap;max-width:640px;font-size:12px;'
            'background:#f8fafc;padding:10px;border-radius:8px">{}</pre>',
            obj.build_text(),
        )

    @admin.action(description='Publish selected posts to the Telegram channel')
    def action_publish(self, request, queryset):
        published = failed = 0
        for post in queryset:
            result = publish_post(post)
            if result.get('ok'):
                published += 1
            else:
                failed += 1
                self.message_user(
                    request,
                    f'"{post.title}" failed: {result.get("error")}',
                    level=messages.ERROR,
                )
        if published:
            self.message_user(
                request, f'Published {published} post(s) to Telegram.', messages.SUCCESS
            )
        if failed:
            self.message_user(request, f'{failed} post(s) failed.', messages.WARNING)

    @admin.action(description='Publish selected posts to the Facebook page')
    def action_publish_facebook(self, request, queryset):
        from . import facebook

        if not facebook.is_configured():
            self.message_user(
                request,
                'Facebook is not configured. Enable it and fill in the page ID '
                'and page access token under Billing -> Integration settings.',
                level=messages.ERROR,
            )
            return
        done = failed = 0
        for post in queryset:
            result = facebook.publish_and_record(post)
            if result.get('ok'):
                done += 1
            else:
                failed += 1
                self.message_user(
                    request,
                    f'"{post.title}" failed: {result.get("error")}',
                    level=messages.ERROR,
                )
        if done:
            self.message_user(
                request, f'Posted {done} item(s) to Facebook.', messages.SUCCESS
            )
        if failed:
            self.message_user(request, f'{failed} failed.', messages.WARNING)

    @admin.action(description='Publish to BOTH Telegram and Facebook')
    def action_publish_both(self, request, queryset):
        self.action_publish(request, queryset)
        self.action_publish_facebook(request, queryset)

    @admin.action(description='Mark selected posts as draft (does not delete from Telegram)')
    def action_unpublish_note(self, request, queryset):
        updated = queryset.update(status=ChannelPost.STATUS_DRAFT)
        self.message_user(
            request,
            f'{updated} post(s) marked as draft. Note: existing Telegram messages '
            'remain in the channel and must be deleted manually.',
            messages.WARNING,
        )


@admin.register(AlertDelivery)
class AlertDeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscription', 'post', 'ok', 'attempts', 'created_at')
    list_filter = ('ok',)
    search_fields = ('subscription__user__username', 'post__title')
    readonly_fields = ('subscription', 'post', 'ok', 'error', 'attempts',
                       'created_at', 'last_attempt_at')
    actions = ('action_retry',)

    def has_add_permission(self, request):
        return False

    @admin.action(description='Retry delivery for the selected posts')
    def action_retry(self, request, queryset):
        from . import alerts

        post_ids = list({d.post_id for d in queryset})
        total = failed = 0
        for post in ChannelPost.objects.filter(pk__in=post_ids):
            result = alerts.send_immediate_alerts(post)
            total += result['sent']
            failed += result['failed']
        self.message_user(request, f'{total} alert(s) re-sent, {failed} still failing.')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'plan_name', 'amount', 'status',
        'payment_method', 'has_receipt', 'alerts_muted', 'alert_mode',
        'created_at', 'expires_at',
    )
    list_filter = ('status', 'payment_method', 'plan_name', 'alert_mode', 'alerts_muted')
    search_fields = (
        'user__username', 'user__email', 'transaction_reference',
        'chapa_reference', 'payer_note',
    )
    readonly_fields = (
        'user', 'telegram_chat_id', 'amount', 'duration_days',
        'chapa_reference', 'chapa_checkout_url', 'chapa_payload',
        'receipt_file', 'created_at', 'activated_at', 'expires_at',
        'status_badge',
    )
    actions = ('action_approve', 'action_reject')
    fieldsets = (
        (None, {'fields': ('user', 'telegram_chat_id', 'plan_name', 'amount',
                           'duration_days', 'status', 'status_badge')}),
        ('Payment', {
            'fields': ('payment_method', 'transaction_reference', 'receipt_file',
                       'payer_note', 'chapa_reference', 'chapa_checkout_url',
                       'chapa_payload'),
        }),
        ('Job alerts', {
            'description': 'How this subscriber hears about new posts. They can '
                           'change this themselves in the mini app; this is the '
                           'admin view of the same setting.',
            'fields': ('alert_mode', 'digest_hour', 'alerts_muted'),
        }),
        ('Review', {
            'fields': ('review_note', 'reviewed_by', 'reviewed_at'),
        }),
        ('Audit', {
            'classes': ('collapse',),
            'fields': ('created_at', 'activated_at', 'expires_at'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'reviewed_by')

    @admin.display(boolean=True, description='Receipt')
    def has_receipt(self, obj):
        return bool(obj.receipt_file)

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            Subscription.STATUS_ACTIVE: '#16a34a',
            Subscription.STATUS_PENDING_REVIEW: '#d97706',
            Subscription.STATUS_AWAITING_PAYMENT: '#64748b',
            Subscription.STATUS_REJECTED: '#dc2626',
            Subscription.STATUS_CANCELLED: '#64748b',
        }
        color = colors.get(obj.status, '#64748b')
        return format_html(
            '<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
            'background:{};color:#fff;font-weight:700;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.action(description='Approve selected subscriptions')
    def action_approve(self, request, queryset):
        count = 0
        for subscription in queryset:
            if subscription.status == Subscription.STATUS_ACTIVE:
                continue
            activate_subscription(subscription, reviewed_by=request.user)
            count += 1
        self.message_user(
            request, f'Approved {count} subscription(s); users were notified.', messages.SUCCESS
        )

    @admin.action(description='Reject selected subscriptions')
    def action_reject(self, request, queryset):
        count = 0
        for subscription in queryset:
            if subscription.status == Subscription.STATUS_REJECTED:
                continue
            reject_subscription(subscription, reviewed_by=request.user)
            count += 1
        self.message_user(
            request, f'Rejected {count} subscription(s); users were notified.', messages.WARNING
        )


@admin.register(PostApplication)
class PostApplicationAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'applicant', 'status', 'created_at')
    list_filter = ('status', 'post__kind')
    search_fields = ('applicant__username', 'applicant__email', 'post__title')
    readonly_fields = ('post', 'applicant', 'created_at', 'updated_at')
    autocomplete_fields = ('applicant',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('post', 'applicant')
