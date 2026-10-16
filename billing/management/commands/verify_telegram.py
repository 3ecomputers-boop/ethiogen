"""
Verify the Telegram integration end to end against the real API.

    python manage.py verify_telegram                 # safe checks + optional post
    python manage.py verify_telegram --publish       # also post a test message
    python manage.py verify_telegram --publish --delete-after

Reports, in order:
  1. is the bot token valid          (getMe)
  2. can the bot reach the channel   (getChat)
  3. is the bot an ADMIN there       (getChatMember)  <-- the usual failure
  4. does Telegram accept our inline keyboard        (sendMessage with reply_markup)
  5. can the bot send you a DM       (getChat on your own id, optional)
"""
from __future__ import annotations

import json
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from billing import config
from billing.models import ChannelPost

API = 'https://api.telegram.org'


class Command(BaseCommand):
    help = 'Check the Telegram token, channel, permissions and inline keyboard.'

    def add_arguments(self, parser):
        parser.add_argument('--publish', action='store_true',
                            help='Actually post a test message to the channel.')
        parser.add_argument('--delete-after', action='store_true',
                            help='Delete the test message once it is sent.')
        parser.add_argument('--title', default='Connectivity test',
                            help='Title used for the test post.')

    def handle(self, *args, **options):
        token = config.telegram_token()
        chat_id = config.telegram_channel_id()

        self.stdout.write(self.style.HTTP_INFO('Ethiogen — Telegram verification'))
        self.stdout.write(f'  config source : '
                          f'{"admin settings" if config.get_row() else "settings.py / env"}')
        self.stdout.write(f'  channel id    : {chat_id or "(not set)"}')
        self.stdout.write(f'  channel name  : {config.telegram_bot_username() or "(not set)"}')
        self.stdout.write('')

        if not token:
            self.fail_('No bot token. Set it in Billing -> Integration settings, '
                       'or export TELEGRAM_BOT_TOKEN.')
        if not chat_id:
            self.fail_('No channel id. Set TELEGRAM_CHANNEL_ID in '
                       'Billing -> Integration settings.')

        # --- 1. token valid? -------------------------------------------------
        me = self.api('GET', 'getMe', token=token)
        if not me['ok']:
            self.fail_(f'The bot token was rejected: {me["error"]}')
        bot = me['data']['result']
        self.ok(f'Token valid — bot is @{bot.get("username")} (id {bot["id"]})')

        # --- 2. can the bot read the target chat? ---------------------------
        chat = self.api('GET', f'getChat?chat_id={chat_id}', token=token)
        if not chat['ok']:
            self.fail_(f'The bot cannot access chat {chat_id}: {chat["error"]}\n'
                       f'          Add the bot to that channel/group first.')
        chat_data = chat['data']['result']
        self.ok(f'Chat reachable — "{chat_data.get("title")}" '
                f'(type {chat_data.get("type")})')

        # --- 3. is the bot an admin there? -----------------------------------
        member = self.api('GET', f'getChatMember?chat_id={chat_id}'
                                f'&user_id={bot["id"]}', token=token)
        if not member['ok']:
            self.fail_(f'Could not read the bot\'s membership: {member["error"]}')
        status = member['data']['result'].get('status')
        can_post = member['data']['result'].get('can_post_messages', False)
        if status not in ('administrator', 'creator'):
            self.fail_(f'The bot is "{status}" in that chat, but it must be an '
                       f'ADMINISTRATOR to post messages and inline buttons.\n'
                       f'          Chat -> Administrators -> Add administrator.')
        self.ok(f'Bot is an administrator (can_post_messages={can_post})')

        # --- 4. does Telegram accept our inline keyboard? --------------------
        post = ChannelPost.objects.filter(status=ChannelPost.STATUS_PUBLISHED).first()
        if post is None:
            post = ChannelPost(
                kind=ChannelPost.KIND_GENERAL,
                title=options['title'],
                body='Verification message from manage.py verify_telegram.',
                show_apply=True, show_subscribe=True,
            )
        else:
            post = ChannelPost.objects.filter(pk=post.pk).first()

        from bot.telegram_bridge import build_post_keyboard
        from billing.services import _serialize_reply_markup

        markup = _serialize_reply_markup(build_post_keyboard(post))
        self.ok(f'Keyboard built with '
                f'{sum(len(r) for r in markup["inline_keyboard"])} button(s): '
                f'{[b["text"] for row in markup["inline_keyboard"] for b in row]}')

        if options['publish']:
            result = self.api(
                'POST', 'sendMessage', token=token,
                data={
                    'chat_id': chat_id,
                    'text': f'*{post.title}*\n\nVerification message from '
                            f'`manage.py verify_telegram`.',
                    'parse_mode': 'Markdown',
                    'reply_markup': json.dumps(markup),
                },
            )
            if not result['ok']:
                self.fail_(f'Telegram rejected the post: {result["error"]}')
            message_id = result['data']['result']['message_id']
            self.ok(f'Posted to the channel — message_id {message_id}')
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                '  Now open that channel in the Telegram app and tap a button.'))

            if options['delete_after']:
                time.sleep(2)
                deleted = self.api('POST', f'deleteMessage?chat_id={chat_id}'
                                             f'&message_id={message_id}', token=token)
                if deleted['ok']:
                    self.ok('Test message deleted.')
                else:
                    self.warn(f'Could not delete the test message: {deleted["error"]}')
        else:
            self.stdout.write('')
            self.stdout.write('  Re-run with --publish to send a real test message.')

        # --- 5. reminder about how callbacks arrive --------------------------
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('How the buttons actually work'))
        self.stdout.write('  1. Telegram sends the button tap to the BOT process,')
        self.stdout.write('     not to Django. The bot must be running locally:')
        self.stdout.write('       venv\\Scripts\\python.exe bot\\bot.py')
        self.stdout.write('  2. Inline buttons on a CHANNEL message only respond')
        self.stdout.write('     inside the Telegram app (phone/desktop), not t.me web.')
        self.stdout.write('  3. To test the handlers with no Telegram at all:')
        self.stdout.write('       venv\\Scripts\\python.exe manage.py simulate_bot')
        self.stdout.write('')

    # -- helpers ----------------------------------------------------------
    def api(self, method, path, token, data=None):
        url = f'{API}/bot{token}/{path}'
        try:
            if data is not None:
                response = requests.post(url, data=data, timeout=25)
            else:
                response = requests.get(url, timeout=25)
        except requests.RequestException as exc:
            return {'ok': False, 'error': f'network error: {exc}'}
        try:
            body = response.json()
        except ValueError:
            return {'ok': False, 'error': f'HTTP {response.status_code} (non-JSON)'}
        if not body.get('ok'):
            return {'ok': False, 'error': body.get('description', 'unknown error')}
        return {'ok': True, 'data': body}

    def ok(self, message):
        self.stdout.write(self.style.SUCCESS(f'  PASS  {message}'))

    def warn(self, message):
        self.stdout.write(self.style.WARNING(f'  WARN  {message}'))

    def fail_(self, message):
        self.stdout.write(self.style.ERROR(f'  FAIL  {message}'))
        raise SystemExit(1)
