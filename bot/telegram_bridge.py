"""
Telegram bridge for the channel distribution + subscription billing flow.

This module owns everything the bot needs to:

  * render the inline keyboard attached to a published ChannelPost
    (Apply / Subscribe / View Details)
  * handle those button presses
  * run the subscribe -> pay (Chapa or manual transfer) -> upload receipt
    -> admin approval conversation
  * notify the user once the admin approves

Wire it into the running bot with one call in build_application():

    from telegram_bridge import register_bridge   # from the bot/ directory
    register_bridge(application)

Requires python-telegram-bot v20+, and Django set up (bot.py does this
before build_application() runs).
"""
from __future__ import annotations

import asyncio
import logging
import posixpath
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from billing import config
from billing.models import ChannelPost, PostApplication, Subscription
from billing.services import (
    has_active_subscription,
    init_chapa_checkout,
    record_application,
    resolve_chat_id,
)

logger = logging.getLogger("ethiogen.telegram.billing")


def _cfg(name: str, default=None):
    """
    Read a config value at call time.

    Deliberately not resolved at import: the admin can change these values
    while the bot is running, and we want each new message to see them.
    """
    try:
        return getattr(config, name)()
    except Exception as exc:  # config layer unavailable during early boot
        logger.debug('config.%s() failed: %s', name, exc)
        return default


def price() -> Decimal:
    return _cfg('subscription_price', Decimal('500.00'))


def days() -> int:
    return _cfg('subscription_days', 30)


def currency() -> str:
    return _cfg('currency', 'ETB')


def site_url() -> str:
    return str(_cfg('website_url', 'https://ethiogen.com')).rstrip('/')


def plan_name() -> str:
    return _cfg('plan_name', 'Channel Subscription')


# ======================================================================
# Helpers
# ======================================================================
def _get_user_factory():
    """
    Resolve the bot's get_or_create_user() helper.

    bot.py runs as __main__, so it is not importable as `bot.bot`.
    """
    import __main__

    fn = getattr(__main__, 'get_or_create_user', None)
    if callable(fn):
        return fn
    try:
        from bot.bot import get_or_create_user as module_fn  # type: ignore

        return module_fn
    except Exception:
        logger.warning('get_or_create_user not found; using local fallback')
        return None


async def _resolve_db_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Resolve and cache the Django user for this Telegram account.

    The bot's get_or_create_user() is decorated with @sync_to_async, so it
    MUST be awaited. Calling it without await yields a coroutine, which then
    gets passed into the ORM and blows up with
    "Field 'id' expected a number but got <coroutine ...>".
    """
    cached = context.user_data.get('db_user')
    if cached is not None:
        return cached

    tg_user = update.effective_user
    if tg_user is None:
        return None

    factory = _get_user_factory()
    if factory is not None:
        result = factory(chat_id=tg_user.id, username=tg_user.username)
        if asyncio.iscoroutine(result):
            db_user = await result
        else:
            db_user = result
    else:
        db_user = await asyncio.to_thread(get_or_create_local_user, tg_user)

    context.user_data['db_user'] = db_user
    return db_user


def get_or_create_local_user(tg_user):
    """Minimal local equivalent of the bot's get_or_create_user()."""
    import re

    from django.contrib.auth import get_user_model
    from django.contrib.auth.hashers import make_password

    from jobs.models import TelegramProfile

    User = get_user_model()
    base = (tg_user.username or f'tg_{tg_user.id}').strip()[:120]
    base = re.sub(r'[^A-Za-z0-9_.@+-]', '_', base) or f'tg_{tg_user.id}'
    user = User.objects.create_user(
        username=base,
        email='',
        # Unusable password: this account signs in via Telegram, not a form.
        # The project's UserManager has no make_random_password().
        password=make_password(None),
        first_name=tg_user.first_name or '',
        last_name=tg_user.last_name or '',
    )
    TelegramProfile.objects.create(
        user=user, chat_id=str(tg_user.id), username=tg_user.username
    )
    return user


def _get_or_create_subscription(user, chat_id: int) -> Subscription:
    """Return the user's open subscription, creating one if needed."""
    subscription = (
        Subscription.objects.filter(user=user)
        .filter(status__in=[
            Subscription.STATUS_AWAITING_PAYMENT,
            Subscription.STATUS_PENDING_REVIEW,
        ])
        .order_by('-created_at')
        .first()
    )
    if subscription is None:
        return Subscription.objects.create(
            user=user,
            telegram_chat_id=chat_id,
            amount=price(),
            duration_days=days(),
            plan_name=plan_name(),
        )
    if subscription.telegram_chat_id != chat_id:
        subscription.telegram_chat_id = chat_id
        subscription.save(update_fields=['telegram_chat_id'])
    return subscription


def _reply(update: Update, text: str, markup=None, parse_mode='Markdown') -> None:
    """Reply to a callback query (editing in place) or a plain message."""
    query = getattr(update, 'callback_query', None)
    if query is not None and query.message is not None:
        query.edit_message_text(text, parse_mode=parse_mode, reply_markup=markup)
    elif update.effective_message is not None:
        update.effective_message.reply_text(text, parse_mode=parse_mode, reply_markup=markup)


# ======================================================================
# Keyboards
# ======================================================================
def build_post_keyboard(post: ChannelPost) -> InlineKeyboardMarkup:
    """Inline keyboard attached to a published ChannelPost."""
    rows = []

    if post.source_url:
        rows.append([InlineKeyboardButton("\U0001F4CB View Details", url=post.source_url)])

    action_row = []
    if post.show_apply:
        action_row.append(
            InlineKeyboardButton("\u2705 Apply Now", callback_data=f"post:apply:{post.pk}")
        )
    if post.show_subscribe:
        action_row.append(
            InlineKeyboardButton("\U0001F514 Subscribe", callback_data=f"post:subscribe:{post.pk}")
        )
    if action_row:
        rows.append(action_row)

    rows.append([InlineKeyboardButton("\U0001F3E0 Open Ethiogen", url=site_url())])
    return InlineKeyboardMarkup(rows)


def build_subscribe_keyboard() -> InlineKeyboardMarkup:
    base = site_url()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001F4F1 Browse Jobs", url=f"{base}/"),
            InlineKeyboardButton("\U0001F50D Browse Talent", url=f"{base}/freelancer/"),
        ]
    ])


def build_payment_keyboard() -> InlineKeyboardMarkup:
    """Payment options shown after the user taps Subscribe."""
    rows = []
    if _cfg('chapa_enabled', False):
        rows.append([
            InlineKeyboardButton(
                "\U0001F4B3 Pay with Card / Telebirr", callback_data="pay:chapa"
            )
        ])
    if _cfg('telebirr_enabled', True):
        rows.append([
            InlineKeyboardButton("\U0001F4F1 Telebirr", callback_data="pay:telebirr")
        ])
    if _cfg('bank_enabled', True):
        rows.append([
            InlineKeyboardButton("\U0001F3E6 Bank Transfer", callback_data="pay:bank")
        ])
    rows.append([InlineKeyboardButton("\u274C Cancel", callback_data="pay:cancel")])
    return InlineKeyboardMarkup(rows)


# ======================================================================
# Channel post buttons
# ======================================================================
async def on_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'Apply Now' button on a published post."""
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(':')[-1])

    post = await asyncio.to_thread(
        lambda: ChannelPost.objects.filter(pk=post_id).first()
    )
    if post is None:
        await query.edit_message_text("This post is no longer available.")
        return

    db_user = await _resolve_db_user(update, context)
    if db_user is None:
        await query.edit_message_text(
            "Could not link your Telegram account. Please send /start and try again."
        )
        return

    if not await asyncio.to_thread(has_active_subscription, db_user):
        await query.edit_message_text(
            "\U0001F512 *Subscription required*\n\n"
            "You need an active subscription before you can apply to this post.\n\n"
            f"Price: *{price()} {currency()}* for {days()} days.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "\U0001F514 Subscribe to Continue",
                    callback_data=f"post:subscribe:{post_id}",
                )],
                [InlineKeyboardButton("\U0001F504 Back", callback_data="back_to_main")],
            ]),
        )
        return

    application = await asyncio.to_thread(record_application, post, db_user)

    await query.edit_message_text(
        "\u2705 *Application received!*\n\n"
        f"Post: *{post.title}*\n\n"
        "The employer will review your profile and contact you shortly.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "\U0001F3E0 Open My Dashboard", url=f"{site_url()}/miniapp/"
            )]
        ]),
    )
    logger.info('Application #%s: %s applied to post %s', application.pk, db_user, post_id)


async def on_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'Subscribe' button on a published post."""
    query = update.callback_query
    await query.answer()

    db_user = await _resolve_db_user(update, context)
    if db_user is None:
        await query.edit_message_text(
            "Could not link your Telegram account. Please send /start and try again."
        )
        return

    if await asyncio.to_thread(has_active_subscription, db_user):
        await query.edit_message_text(
            "\u2705 You already have an *active* subscription. You can Apply to any post.",
            parse_mode='Markdown',
            reply_markup=build_subscribe_keyboard(),
        )
        return

    await query.edit_message_text(
        "\U0001F514 *Ethiogen Subscription*\n\n"
        "Unlock every job and tender posted in this channel, and Apply directly "
        "from Telegram.\n\n"
        f"*Price:* {price()} {currency()}\n"
        f"*Duration:* {days()} days\n\n"
        "Choose how you would like to pay:",
        parse_mode='Markdown',
        reply_markup=build_payment_keyboard(),
    )


# ======================================================================
# Payment
# ======================================================================
async def on_pay_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    method = query.data.split(':')[-1]

    if method == 'cancel':
        context.user_data.pop('awaiting_receipt', None)
        await query.edit_message_text("Cancelled. Tap Subscribe again any time.")
        return

    db_user = await _resolve_db_user(update, context)
    if db_user is None:
        await query.edit_message_text("Please send /start first.")
        return

    subscription = await asyncio.to_thread(
        _get_or_create_subscription, db_user, update.effective_user.id
    )

    if method == 'chapa':
        result = await asyncio.to_thread(init_chapa_checkout, subscription)
        if not result.get('ok'):
            await query.edit_message_text(
                f"\u274C {result.get('error', 'Payment could not be started.')}\n\n"
                "Please use Telebirr or bank transfer instead.",
                parse_mode='Markdown',
                reply_markup=build_payment_keyboard(),
            )
            return
        await query.edit_message_text(
            "\U0001F4B3 *Complete your payment*\n\n"
            "Tap the button below to pay securely with Chapa. "
            "Your subscription activates automatically once payment succeeds.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001F6E2 Pay Now", url=result['checkout_url'])]
            ]),
        )
        return

    # Manual transfer (Telebirr / bank)
    method_value = (
        Subscription.PAYMENT_TELEBIRR if method == 'telebirr' else Subscription.PAYMENT_BANK
    )
    await asyncio.to_thread(
        lambda: Subscription.objects.filter(pk=subscription.pk).update(
            payment_method=method_value
        )
    )

    extra = _cfg('payment_instructions', '') or ''

    if method == 'telebirr':
        details = "\U0001F4F1 *Telebirr transfer*\n\n"
        if _cfg('telebirr_phone', ''):
            details += f"Phone: `{_cfg('telebirr_phone', '')}`\n"
        if _cfg('telebirr_name', ''):
            details += f"Name: *{_cfg('telebirr_name', '')}*\n"
        details += (
            f"Amount: *{price()} {currency()}*\n\n"
            "After sending, press the button below and send a photo of the "
            "confirmation SMS or receipt. An admin will verify it shortly."
        )
    else:
        details = "\U0001F3E6 *Bank transfer*\n\n"
        if _cfg('bank_name', ''):
            details += f"Bank: *{_cfg('bank_name', '')}*\n"
        if _cfg('bank_account_name', ''):
            details += f"Account name: *{_cfg('bank_account_name', '')}*\n"
        if _cfg('bank_account_number', ''):
            details += f"Account no: `{_cfg('bank_account_number', '')}`\n"
        details += (
            f"Amount: *{price()} {currency()}*\n\n"
            "After transferring, press the button below and send a photo of the "
            "transfer receipt. An admin will verify it shortly."
        )

    if extra:
        details += f"\n\n{extra}"

    await query.edit_message_text(
        details,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001F4F4 I Have Paid — Upload Receipt",
                                  callback_data="pay:receipt")],
            [InlineKeyboardButton("\u274C Cancel", callback_data="pay:cancel")],
        ]),
    )


async def on_receipt_requested(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Arm the receipt upload.

    Rather than a ConversationHandler state, we set a flag on user_data.
    The photo that follows arrives as an ordinary message and is handled by
    the module-level MessageHandler installed in register_bridge().

    Why not a ConversationHandler: these buttons live on a channel message,
    so every user shares one chat_id and the handler would track only the
    first user to tap. per_message=True fixes that but then forbids
    MessageHandler in states, which a photo upload requires. A user_data
    flag has neither problem.
    """
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_receipt'] = True
    await query.edit_message_text(
        "\U0001F4F4 *Upload your receipt*\n\n"
        "Please send a clear photo or screenshot of your payment confirmation. "
        "Put the transaction reference in the caption.\n\n"
        "_Send /cancel to abort._",
        parse_mode='Markdown',
    )


def _store_receipt_bytes(data: bytes, subscription: Subscription) -> str:
    """Save already-downloaded receipt bytes against the subscription."""
    stamp = int(timezone.now().timestamp())
    target = posixpath.join(
        'billing', 'receipts', f'sub_{subscription.pk}_{stamp}.jpg'
    )
    field = Subscription._meta.get_field('receipt_file')
    return field.storage.save(target, ContentFile(data))


async def on_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Store an uploaded receipt and flag the subscription for review.

    Runs as a module-level MessageHandler. It only acts once the user has
    tapped 'I Have Paid', so ordinary chat is ignored.
    """
    if not context.user_data.get('awaiting_receipt'):
        return

    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    db_user = await _resolve_db_user(update, context)
    if db_user is None:
        context.user_data.pop('awaiting_receipt', None)
        await message.reply_text("Please send /start first.")
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id

    if file_id is None:
        await message.reply_text(
            "That does not look like an image. Please send a photo of your receipt."
        )
        return

    subscription = await asyncio.to_thread(
        _get_or_create_subscription, db_user, chat.id
    )
    caption = (message.caption or '').strip()

    from jobs.telegram_utils import get_bot

    bot = get_bot()
    if bot is None:
        await message.reply_text(
            "\u274C Receipt upload is unavailable right now. Please contact support."
        )
        return

    try:
        # get_file / download_as_bytearray are coroutines in PTB v20+.
        handle = await bot.get_file(file_id)
        data = bytes(await handle.download_as_bytearray())
        path = await asyncio.to_thread(
            _store_receipt_bytes, data, subscription
        )
    except Exception as exc:
        logger.error('Receipt download failed for sub %s: %s', subscription.pk, exc)
        await message.reply_text("\u274C Could not save the receipt. Please try again.")
        return

    def _save():
        subscription.receipt_file = path
        subscription.payer_note = caption
        # A short caption that looks like a reference is stored as one.
        if caption and len(caption) <= 120 and not caption.startswith('http'):
            subscription.transaction_reference = caption
        subscription.status = Subscription.STATUS_PENDING_REVIEW
        subscription.save()

    await asyncio.to_thread(_save)
    context.user_data.pop('awaiting_receipt', None)

    # Email confirmation, but never let a mail failure break the flow.
    try:
        from billing import emails

        await asyncio.to_thread(emails.receipt_received, subscription)
    except Exception as exc:
        logger.error('Receipt email failed: %s', exc)

    await message.reply_text(
        "\u2703 *Receipt received!*\n\n"
        "Your payment is now waiting for admin approval. You will get a message "
        "here the moment it is approved.\n\n"
        f"Reference: `{subscription.transaction_reference or 'not provided'}`",
        parse_mode='Markdown',
    )
    logger.info('Receipt uploaded for subscription #%s by %s', subscription.pk, db_user)


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Abort a pending receipt upload (the cancel button or /cancel)."""
    if not context.user_data.get('awaiting_receipt') and not update.callback_query:
        return
    context.user_data.pop('awaiting_receipt', None)
    if update.callback_query:
        await update.callback_query.answer()
    await _reply(update, "Cancelled.", InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F4E2 Browse Ethiogen", url=site_url())]
    ]))


# ======================================================================
# Registration
# ======================================================================
def register_bridge(application) -> None:
    """
    Attach the billing bridge to a running python-telegram-bot Application.

    Call this inside build_application(), after the other handlers are added.

    No ConversationHandler is used: every step of the flow is a button tap,
    and the single non-callback step (sending the receipt photo) is gated on
    a user_data flag. That keeps per-user state correct even though the
    buttons live on one channel message shared by every viewer, which is
    exactly the case ConversationHandler mishandles.
    """
    application.add_handler(CallbackQueryHandler(on_apply, pattern=r"^post:apply:\d+$"))
    application.add_handler(
        CallbackQueryHandler(on_subscribe, pattern=r"^post:subscribe:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(on_pay_choice, pattern=r"^pay:(chapa|telebirr|bank|cancel)$")
    )
    application.add_handler(
        CallbackQueryHandler(on_receipt_requested, pattern=r"^pay:receipt$")
    )
    application.add_handler(CallbackQueryHandler(on_cancel, pattern=r"^pay:cancel$"))
    application.add_handler(CommandHandler('cancel', on_cancel))

    # Receipt upload: acts only while the awaiting_receipt flag is set.
    application.add_handler(MessageHandler(filters.PHOTO, on_receipt_received))
    application.add_handler(MessageHandler(filters.Document.IMAGE, on_receipt_received))

    logger.info("Billing bridge handlers registered.")
