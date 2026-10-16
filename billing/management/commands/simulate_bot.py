"""
Drive the real button handlers locally, with no Telegram connection.

    python manage.py simulate_bot

This calls the actual functions in bot/telegram_bridge.py with lightweight
stand-ins for a telegram Update / ContextTypes, so you can verify the whole
flow on a machine that cannot reach api.telegram.org:

    Subscribe  -> payment options
    Telebirr   -> bank details + "I Have Paid"
    Upload     -> receipt stored, status = pending_review
    Approve    -> subscription active, expiry set
    Apply      -> gated without a subscription, works with one

Everything it creates is deleted at the end.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from billing.models import ChannelPost, PostApplication, Subscription
from billing.services import activate_subscription, has_active_subscription

User = get_user_model()

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(label, ok, detail=''):
    results.append(ok)
    mark = PASS if ok else FAIL
    print(f'  {mark}  {label}' + (f'  -- {detail}' if detail else ''))


# ======================================================================
# Minimal stand-ins for a telegram Update
# ======================================================================
class FakeUser:
    def __init__(self, uid, username='tester', first_name='Test'):
        self.id = uid
        self.username = username
        self.first_name = first_name
        self.last_name = 'User'


class FakeChat:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, chat_id):
        self.chat = FakeChat(chat_id)
        self.photo = None
        self.document = None
        self.caption = None
        self.replies = []
        self.text = ''

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.text = text
        return self


class FakeQuery:
    def __init__(self, data, chat_id, message):
        self.data = data
        self.message = message
        self.answered = False
        self.edits = []
        self.text = ''

    async def answer(self, *a, **k):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(text)
        self.text = text
        return self


class FakeUpdate:
    def __init__(self, data, chat_id, user, photo_file_id=None, caption=None):
        self.effective_user = user
        self.effective_chat = FakeChat(chat_id)
        self.message = FakeMessage(chat_id)
        self.callback_query = FakeQuery(data, chat_id, self.message)
        if photo_file_id:
            self.message.photo = [FakePhoto(photo_file_id)]
            self.message.caption = caption

    @property
    def effective_message(self):
        return self.message


class FakePhoto:
    def __init__(self, file_id):
        self.file_id = file_id


class FakeContext:
    def __init__(self):
        self.user_data = {}
        self.chat_data = {}


# ======================================================================
class Command(BaseCommand):
    help = 'Exercise the inline-button handlers locally without Telegram.'

    def handle(self, *args, **options):
        from bot import telegram_bridge as tb

        user = User.objects.filter(username='sim_bot_user').first()
        if user is None:
            user = User.objects.create_user(
                username='sim_bot_user', email='sim@example.test',
                first_name='Test', last_name='User',
            )
        # Start from a clean slate for this user.
        Subscription.objects.filter(user=user).delete()
        PostApplication.objects.filter(applicant=user).delete()

        tg_id = 999000111
        post = ChannelPost.objects.create(
            kind=ChannelPost.KIND_JOB,
            title='Simulation Job',
            body='Local test',
            show_apply=True, show_subscribe=True,
        )

        self.stdout.write(self.style.HTTP_INFO('Simulating inline button taps'))
        self.stdout.write('')

        # ---- 1. the keyboard that gets attached to the post ---------------
        from billing.services import _serialize_reply_markup
        markup = _serialize_reply_markup(tb.build_post_keyboard(post))
        buttons = [b for row in markup['inline_keyboard'] for b in row]
        labels = [b['text'] for b in buttons]
        callbacks = [b.get('callback_data') for b in buttons if b.get('callback_data')]
        print('Keyboard Telegram would receive:')
        print(f'  {json_dumps(markup)}')
        print('')
        check('Apply button present', any('Apply' in l for l in labels), str(labels))
        check('Subscribe button present', any('Subscribe' in l for l in labels))
        check('callback data is Telegram-safe (<=64 bytes)',
              all(len(c.encode()) <= 64 for c in callbacks), str(callbacks))

        # ---- 2. Apply WITHOUT a subscription -> should be refused ----------
        ctx = FakeContext()
        up = FakeUpdate(f'post:apply:{post.pk}', tg_id, FakeUser(tg_id))
        asyncio.run(tb.on_apply(up, ctx))
        check('Apply is refused without a subscription',
              'Subscription required' in up.callback_query.text,
              up.callback_query.text[:60])
        check('no application row was created',
              not PostApplication.objects.filter(post=post, applicant=user).exists())

        # ---- 3. Subscribe -> payment options -------------------------------
        ctx = FakeContext()
        up = FakeUpdate(f'post:subscribe:{post.pk}', tg_id, FakeUser(tg_id))
        asyncio.run(tb.on_subscribe(up, ctx))
        text = up.callback_query.text
        check('Subscribe shows the price', 'Price' in text, text.splitlines()[-1][:50])
        check('Subscribe shows the duration', 'days' in text)
        check('callback was answered (no spinner hang)', up.callback_query.answered)

        # ---- 4. choose Telebirr -> transfer details ------------------------
        kb = _serialize_reply_markup(tb.build_payment_keyboard())
        pay_options = [b.get('callback_data') for row in kb['inline_keyboard']
                       for b in row if b.get('callback_data')]
        check('payment menu offers telebirr', 'pay:telebirr' in pay_options, str(pay_options))
        check('payment menu offers bank transfer', 'pay:bank' in pay_options)
        check('payment menu offers cancel', 'pay:cancel' in pay_options)

        ctx = FakeContext()
        up = FakeUpdate('pay:telebirr', tg_id, FakeUser(tg_id))
        asyncio.run(tb.on_pay_choice(up, ctx))
        check('Telebirr shows transfer instructions', 'Telebirr' in up.callback_query.text,
              up.callback_query.text[:50])
        check('Telebirr asks for the receipt', 'receipt' in up.callback_query.text.lower())

        sub = Subscription.objects.filter(
            user__telegram_profile__chat_id=str(tg_id)
        ).first()
        check('a subscription row was created', sub is not None)
        if sub is None:
            self.stdout.write(self.style.ERROR(
                '  no subscription row — the bridge user could not be resolved'))
            return
        bridge_user = sub.user
        check('payment method recorded',
              sub.payment_method == Subscription.PAYMENT_TELEBIRR, sub.payment_method)
        check('price copied from config',
              str(sub.amount) == str(tb.price()), f'{sub.amount} vs {tb.price()}')
        check('duration copied from config',
              sub.duration_days == tb.days(),
              f'{sub.duration_days} vs {tb.days()}')

        # ---- 5. tap "I Have Paid" then upload a receipt --------------------
        ctx = FakeContext()
        up = FakeUpdate('pay:receipt', tg_id, FakeUser(tg_id))
        asyncio.run(tb.on_receipt_requested(up, ctx))
        check('receipt prompt shown', 'receipt' in up.callback_query.text.lower())
        check('awaiting_receipt flag set', ctx.user_data.get('awaiting_receipt') is True)

        # Feed a fake photo through the real receipt handler. The download
        # step is stubbed so no network call happens.
        tmpdir = tempfile.mkdtemp()
        try:
            real_store = tb._store_receipt_bytes

            def fake_store(data, subscription):
                from pathlib import Path
                import posixpath
                stamp = int(__import__('django.utils.timezone',
                                       fromlist=['now']).now().timestamp())
                name = posixpath.join('billing', 'receipts', f'sim_{stamp}.jpg')
                field = Subscription._meta.get_field('receipt_file')
                from django.core.files.base import ContentFile
                return field.storage.save(name, ContentFile(b'fake-jpeg-bytes'))

            tb._store_receipt_bytes = fake_store

            class FakeFile:
                file_id = 'FAKE'

            class FakeHandle:
                async def download_as_bytearray(self):
                    return b'fake-jpeg-bytes'

            import jobs.telegram_utils as tgutils

            class FakeBot:
                async def get_file(self, file_id):
                    return FakeHandle()

            real_get_bot = tgutils.get_bot
            tgutils.get_bot = lambda: FakeBot()

            try:
                ctx = FakeContext()
                ctx.user_data['awaiting_receipt'] = True
                up = FakeUpdate(None, tg_id, FakeUser(tg_id),
                                photo_file_id='FAKE', caption='FT12345')
                asyncio.run(tb.on_receipt_received(up, ctx))
            finally:
                tgutils.get_bot = real_get_bot
                tb._store_receipt_bytes = real_store

            check('receipt confirmed to the user',
                  any('Receipt received' in m for m in up.message.replies),
                  str(up.message.replies)[:70])
            sub.refresh_from_db()
            check('status moved to pending_review',
                  sub.status == Subscription.STATUS_PENDING_REVIEW, sub.status)
            check('receipt file stored', bool(sub.receipt_file), str(sub.receipt_file))
            check('transaction reference captured from the caption',
                  sub.transaction_reference == 'FT12345', sub.transaction_reference)
            check('awaiting_receipt flag cleared',
                  ctx.user_data.get('awaiting_receipt') is None)
            check('not active until approved', not has_active_subscription(bridge_user))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        # ---- 6. admin approves --------------------------------------------
        activate_subscription(sub, reviewed_by=user, note='simulated approval')
        sub.refresh_from_db()
        check('approval activates the subscription',
              sub.status == Subscription.STATUS_ACTIVE, sub.status)
        check('expiry set from the configured duration',
              sub.expires_at is not None, str(sub.expires_at))
        check('has_active_subscription now true', has_active_subscription(bridge_user))

        # ---- 7. Apply WITH a subscription -> should succeed ----------------
        ctx = FakeContext()
        up = FakeUpdate(f'post:apply:{post.pk}', tg_id, FakeUser(tg_id))
        asyncio.run(tb.on_apply(up, ctx))
        check('Apply now succeeds', 'Application received' in up.callback_query.text,
              up.callback_query.text[:60])
        app = PostApplication.objects.filter(post=post, applicant=bridge_user).first()
        check('application row created', app is not None)
        asyncio.run(tb.on_apply(
            FakeUpdate(f'post:apply:{post.pk}', tg_id, FakeUser(tg_id)), FakeContext()))
        check('tapping Apply twice does not duplicate',
              PostApplication.objects.filter(post=post, applicant=bridge_user).count() == 1)

        # ---- 8. cleanup ----------------------------------------------------
        Subscription.objects.filter(user=bridge_user).delete()
        PostApplication.objects.filter(applicant=bridge_user).delete()
        for extra in (bridge_user,):
            if extra is not user:
                extra.delete()
        post.delete()
        user.delete()

        passed = sum(1 for r in results if r)
        self.stdout.write('')
        if passed == len(results):
            self.stdout.write(self.style.SUCCESS(
                f'{passed}/{len(results)} checks passed — the button logic works.'))
            self.stdout.write('')
            self.stdout.write(self.style.HTTP_INFO('To test against real Telegram:'))
            self.stdout.write('  1. python manage.py verify_telegram --publish')
            self.stdout.write('  2. python bot\\bot.py')
            self.stdout.write('  3. open the channel in the Telegram APP and tap')
        else:
            self.stdout.write(self.style.ERROR(f'{passed}/{len(results)} checks passed'))


def json_dumps(value):
    import json

    return json.dumps(value, ensure_ascii=False)
