# Billing and Telegram

This document describes the paid-channel model: how a subscription is created, paid for, reviewed, activated, and used, plus how posts reach Telegram and how subscribers are alerted.

## 1. Components

| Component | Location | Role |
|---|---|---|
| `ChannelPost` | `billing.models` | Content to publish (job, tender, general) |
| `Subscription` | `billing.models` | A user's paid access and payment state |
| `PostApplication` | `billing.models` | Application from a channel post |
| `AlertDelivery` | `billing.models` | De-duplicated alert log |
| `IntegrationSettings` | `billing.models` | Singleton configuration |
| `billing.services` | Python | Telegram sends, publishing, Chapa, approvals |
| `billing.alerts` | Python | Immediate alerts, digests, matching |
| `bot/bot.py` | Process | Telegram bot and conversation flows |
| `bot/telegram_bridge.py` | Python | Inline buttons, payment flow, receipt upload |
| `billing/views.py` | Django | Chapa webhook, analytics, Telegram login |

## 2. Subscription lifecycle

```
                    ┌──────────────────┐
                    │ awaiting_payment │  (created when the user taps Subscribe)
                    └────────┬─────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   Chapa checkout      Telebirr transfer    Bank transfer
          │                  │                  │
          ▼                  ▼                  ▼
   Chapa webhook       receipt upload      receipt upload
          │                  │                  │
          ▼                  ▼                  ▼
   auto-approve?       pending_review      pending_review
     │      │                 │                  │
    yes     no                └──────┬───────────┘
     │      └──► pending_review      │
     ▼                               ▼
   active  ◄────────────── approve ──┘
     │
     ├── expires_at passes → expired (renewal_reminders)
     └── reject → rejected
```

### Statuses

| Status | Meaning |
|---|---|
| `awaiting_payment` | Created, no payment method completed |
| `pending_review` | Receipt uploaded or Chapa checkout started; awaiting review/confirmation |
| `active` | Paid and valid |
| `rejected` | Payment could not be verified |
| `cancelled` | Cancelled/abandoned |
| `expired` | Was active, past `expires_at` |

### Payment methods

| Value | Label |
|---|---|
| `chapa` | Chapa (card / Telebirr) |
| `telebirr` | Telebirr transfer |
| `bank` | Bank transfer |

## 3. How a user subscribes

1. The user sees a published `ChannelPost` with an inline **Subscribe** button.
2. Tapping it runs `telegram_bridge.on_subscribe`.
3. If the user already has an active subscription, they are told so.
4. Otherwise they see price, duration, and payment options:
   - **Pay with Card / Telebirr** (shown only if Chapa is enabled)
   - **Telebirr**
   - **Bank Transfer**
5. A `Subscription` is created with `amount`/`duration_days` from the current configuration.

### Chapa path

1. `init_chapa_checkout(subscription)` posts to `POST {CHAPA_API_BASE}/transaction/initialize`.
2. Chapa returns a `checkout_url`; the bot shows a **Pay Now** button.
3. The subscription moves to `pending_review`.
4. Chapa calls `POST /billing/chapa/webhook/` when the payment completes.
5. `handle_chapa_webhook` finds the subscription by `meta.subscription_id`, `reference`, or `sub-<id>`.
6. If the payload status is `success` and `chapa_auto_approve` is on, the subscription is activated immediately. Otherwise staff approve it at `/admin/subscriptions/`.

### Manual transfer path

1. The bot shows the configured Telebirr or bank details plus the amount.
2. The user taps **I Have Paid — Upload Receipt**.
3. `on_receipt_received` downloads the photo/document, stores it in `media/billing/receipts/`, records the caption as `payer_note` (and as `transaction_reference` when short), and sets `pending_review`.
4. Staff review the receipt and approve/reject at `/admin/subscriptions/` or with `/approve` / `/reject` in Telegram.

### Approval side effects

`activate_subscription`:

- Sets `status=active`, `activated_at=now`, `expires_at=now + duration_days`.
- Records `reviewed_by`, `reviewed_at`, and the note.
- Sends a Telegram DM with a "Browse Jobs / Browse Talent" keyboard when a chat ID resolves.
- Sends an approval email (failures are logged, never raised).

`reject_subscription`:

- Sets `status=rejected` and records the reviewer/note.
- Sends a Telegram DM with the rejection note.
- Sends a rejection email.

## 4. Publishing posts

### Create a post

Use `/django-admin/billing/channelpost/add/` or the employer API.

Important fields:

| Field | Purpose |
|---|---|
| `kind` | `job`, `tender`, `general` |
| `title`, `body` | Content; body supports Markdown |
| `source_url` | "View Details" link |
| `company`, `location`, `salary`, `deadline` | Formatted into the message |
| `category_tag` | Used for matched alerts |
| `show_apply`, `show_subscribe` | Which inline buttons to attach |
| `organization` | Optional tenant owner; enforces plan quota |
| `job_post` | Optional link to a portal job |
| `alerted_at` | Set after an alert fan-out |

### Publish

From the dashboard: `/admin/posts/` → **Publish**.
From Python:

```python
from billing.models import ChannelPost
from billing.services import publish_post

post = ChannelPost.objects.get(pk=1)
result = publish_post(post)          # publishes + alerts subscribers
print(result)
```

What happens:

1. **Quota gate** — if `post.organization` is set and `kind='job'`, `tenants.services.can_publish_job()` must allow it. Blocked posts become `failed` with a `publish_error`; no quota is consumed.
2. **Telegram send** — `sendMessage` to the configured channel with the inline keyboard from `build_post_keyboard`.
3. **Bookkeeping** — on success: `status=published`, `published_at`, `telegram_message_id`, `telegram_chat_id`. On failure: `status=failed`, `publish_error`.
4. **Quota consumption** — only successful job publishes call `consume_job_post()` and write a `TenantAuditLog` entry.
5. **Alerts** — if `alert=True` and the send succeeded, `alerts.send_immediate_alerts(post)` runs. Alert failures never fail the publish.

### Inline keyboard

`build_post_keyboard(post)` produces:

- **View Details** (URL) if `source_url` is set
- **Apply Now** (callback `post:apply:<id>`) if `show_apply`
- **Subscribe** (callback `post:subscribe:<id>`) if `show_subscribe`
- **Open Ethiogen** (site URL)

## 5. Applying from a channel

`on_apply`:

1. Resolves the Telegram user to a Django user.
2. Requires an active subscription (`has_active_subscription`).
3. Calls `record_application(post, user)`, which is idempotent per `(post, applicant)`.
4. Sends an email to the applicant (`emails.application_received`).

Staff can review applications at `/admin/applications/` and update status. `notify_application_status(application, note)` sends Telegram + email updates to the applicant.

## 6. Alerts

Subscribers choose an `alert_mode`:

| Mode | Behaviour |
|---|---|
| `immediate` | Every published post, right away |
| `digest` | One daily summary at `digest_hour` |
| `matched` | Only posts that match the profile |

### Immediate alerts

- Recipients: active, un-muted subscriptions with a `telegram_chat_id`, excluding `digest` mode; `matched` mode is filtered by `post_matches_profile`.
- De-duplication: an `AlertDelivery` row with `ok=True` for `(subscription, post)` prevents a second send.
- Sends are spaced by `0.05s` to avoid Telegram flood control.
- `post.alerted_at` is updated after the fan-out.

### Matching heuristic

`post_matches_profile` is deliberately generous. It compares:

- Profile `city`/`country` against `post.location`
- Profile `skills` against `post.category_tag`
- Profile `title` against the post title/body/company/location/tag

If the profile is too thin to judge (`signals == 0`), the post is considered a match so alerts are not silently dropped.

### Digests

`send_digests`:

- Looks back `--lookback` hours (default 24) at published posts.
- Skips posts already delivered successfully.
- Sends up to 10 posts per subscriber.
- Records an `AlertDelivery` row per included post.

### Scheduling

```cron
# every hour: send digests to whoever chose this hour
0 * * * * cd /path/to/project && venv/bin/python manage.py send_digest

# once a day: expire lapsed plans and remind people 3 days out
0 6 * * * cd /path/to/project && venv/bin/python manage.py renewal_reminders --days 3
```

`send_digest` options:

| Option | Effect |
|---|---|
| `--hour 8` | Only subscribers whose `digest_hour` is 8 |
| `--all-hours` | Ignore stored hours; digest everyone now |
| `--lookback 48` | Widen the window |
| `--dry-run` | Report only |

`renewal_reminders` options:

| Option | Effect |
|---|---|
| `--days 7` | Remind 7 days before expiry |
| `--dry-run` | Report only |

## 7. Bot commands

| Command | Access | Purpose |
|---|---|---|
| `/start` | Everyone | Onboarding, referral argument, subscription gate |
| `/invite` | Everyone | Referral link |
| `/test` | Everyone | Confirms the bot is alive |
| `/scrape` | Admin IDs | Runs `post_website_update` |
| `/tenders` | Admin IDs | Runs `scrape_tenders` |
| `/approve <subscription_id>` | Admin IDs | Activates a subscription |
| `/reject <subscription_id> [note]` | Admin IDs | Rejects a subscription |
| `/stats` | Admin IDs | Subscription/post/application counts |
| `/cancel` | Everyone | Aborts a pending receipt upload |

Admin IDs come from `IntegrationSettings.telegram_admin_ids` first, then `TELEGRAM_ADMIN_IDS` / `ETHIOGEN_ADMIN_IDS`.

The bot also exposes inline callbacks for browsing/filtering talent, searching, job posting, applications, hiring, ratings, favorites, nearby search, language/currency settings, and profile creation.

## 8. Telegram mini app login

Endpoint: `POST /billing/auth/telegram/` with JSON:

```json
{ "initData": "<Telegram WebApp initData string>" }
```

`billing/telegram_auth.py`:

1. Verifies the HMAC signature using the bot token.
2. Rejects missing/invalid/expired data.
3. Upserts the Django user and `TelegramProfile`.
4. Logs the user in via the Django session.
5. Returns `success`, `created`, and a small user object with `role` (`employer`, `job_seeker`, or `new`).

The mini app shell is at `/miniapp/`.

## 9. Webhooks

| Webhook | Method | Notes |
|---|---|---|
| `/billing/chapa/webhook/` | POST | CSRF-exempt, always returns 200 so Chapa does not retry on handler errors |
| `/telegram-webhook/` or `/tg/wh/` | POST | Telegram updates |
| `/billing/auth/telegram/` | POST | Mini app sign-in |

For Chapa, register the absolute URL in the Chapa dashboard:

```
https://your-domain/billing/chapa/webhook/
```

For Telegram, either run the bot in polling mode (`bot/bot.py`) **or** register a webhook. Do not run both against the same bot token.

## 10. Employer APIs

| Endpoint | Method | Purpose |
|---|---|---|
| `/billing/api/employer/post-job/` | POST | Create and publish an employer job post |
| `/billing/api/employer/my-posts/` | GET | Posts scoped to the employer/workspace |
| `/billing/api/employer/applications/` | GET | Applications for the employer's posts |
| `/billing/api/employer/applications/<id>/` | PATCH/POST | Update application status |
| `/billing/api/alerts/preferences/` | GET | Read alert preferences |
| `/billing/api/alerts/preferences/set/` | POST | Update alert mode/hour/mute |

See [API_REFERENCE.md](API_REFERENCE.md).

## 11. Data and auditing

Useful admin pages:

| What | Where |
|---|---|
| Subscriptions | `/django-admin/billing/subscription/` or `/admin/subscriptions/` |
| Receipts | Open a subscription row; `receipt_file` |
| Channel posts | `/django-admin/billing/channelpost/` or `/admin/posts/` |
| Alert deliveries | `/django-admin/billing/alertdelivery/` |
| Applications | `/django-admin/billing/postapplication/` or `/admin/applications/` |
| Integration settings | `/admin/settings/` or `/django-admin/billing/integrationsettings/` |
| Tenant audit | `/django-admin/tenants/tenantauditlog/` |

## 12. Verification and testing

### Offline

```bash
python manage.py simulate_bot
```

Runs 31 checks across the inline-button handlers, payment choices, receipt flow, approvals, and keyboard construction without touching Telegram.

### Live

```bash
python manage.py verify_telegram
python manage.py verify_telegram --publish
python manage.py verify_telegram --publish --delete-after
```

Checks token validity (`getMe`), channel reachability (`getChat`), admin status (`getChatMember`), keyboard serialization, and optionally sends a test message.

### End-to-end

1. Create a `ChannelPost` with Apply/Subscribe buttons.
2. Publish it from `/admin/posts/`.
3. In Telegram, tap Subscribe.
4. Choose a manual method and upload a receipt.
5. Approve at `/admin/subscriptions/`.
6. Confirm the user receives the activation DM.
7. Tap Apply on the post; confirm a `PostApplication` row.
8. Run `renewal_reminders --dry-run` and `send_digest --dry-run`.

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `TELEGRAM_BOT_TOKEN is not configured` | Neither env nor admin row has a token | Set it in `/admin/settings/` |
| `TELEGRAM_CHANNEL_ID is not configured` | No channel ID | Set `telegram_channel_id`; use the numeric ID |
| `chat not found` | Wrong ID or bot not in chat | Add the bot; use `-100...` ID |
| `CHAT_ADMIN_REQUIRED` | Bot is not an admin | Promote the bot in the channel |
| Network timeout to `api.telegram.org` | Host/firewall blocks Telegram | Test from the production host; use `simulate_bot` locally |
| Chapa checkout fails | Missing/invalid secret key | Set the secret key; check API base |
| Chapa webhook returns 200 but no activation | Auto-approve off, status not success, or reference not matched | Check logs and review manually |
| Receipt upload says unavailable | `get_bot()` returned None | Check token/configuration |
| Alerts not sent | No `telegram_chat_id`, muted, digest mode, or already delivered | Check the subscription and `AlertDelivery` |
| Duplicate application | Unique `(post, applicant)` constraint | Expected; `record_application` is idempotent |

## 14. Security notes

- Treat the bot token, Chapa secret, and page access token as secrets. They are visible to staff in the settings UI.
- The Chapa webhook is CSRF-exempt by design; verify payloads against Chapa's signature/reference logic before trusting amounts in a custom integration.
- Receipt images are user-uploaded content. Serve `media/` only to authorized staff in production, or store receipts in private storage.
- Restrict `/admin/` and `/django-admin/` to staff and consider IP allow-listing.
- Do not run polling and a webhook for the same bot simultaneously.
