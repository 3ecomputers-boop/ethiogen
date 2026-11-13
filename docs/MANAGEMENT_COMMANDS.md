# Management Commands

All custom commands are run from the project root with the virtualenv Python.

```powershell
.\venv\Scripts\python.exe manage.py <command> [options]
```

```bash
venv/bin/python manage.py <command> [options]
```

Use `--help` on any command for the authoritative option list:

```bash
python manage.py renewal_reminders --help
```

## Overview

| Command | App | Purpose |
|---|---|---|
| `backfill_user_roles` | jobs | Create roles and assign users from profiles |
| `check_url_references` | jobs | Find `{% url %}` tags that cannot be reversed |
| `create_user` | jobs | Create a verified seeker/client without OTP |
| `post_website_update` | jobs | Scrape ethiojobs and post to Telegram |
| `reprice_talents` | jobs | Reconcile talent prices with the rate card |
| `reset_placeholder_verifications` | jobs | Unverify seeded placeholder profiles |
| `scrape_tenders` | jobs | Scrape 2merkato tenders and post to Telegram |
| `seed_professional_rates` | jobs | Seed/publish weekly professional rates |
| `seed_talents` | jobs | Seed initial talents |
| `start_file_watcher` | jobs | Watch files and notify the owner |
| `sync_talents` | jobs | Sync `Talent` rows from verified profiles |
| `transcribe_news` | jobs | Transcribe a YouTube video and post to Telegram |
| `renewal_reminders` | billing | Remind expiring subscribers and expire lapsed plans |
| `send_digest` | billing | Send daily digests |
| `simulate_bot` | billing | Exercise button handlers offline |
| `verify_telegram` | billing | Live Telegram connectivity/permission check |
| `seed_tenants_from_clients` | tenants | Create organizations from client profiles |

---

## jobs commands

### `backfill_user_roles`

Creates the `Role` rows and assigns `accounts.User.role` based on existing profiles. Safe by default (dry run).

```bash
python manage.py backfill_user_roles            # report only
python manage.py backfill_user_roles --apply    # write changes
python manage.py backfill_user_roles --apply --with-permissions
```

| Option | Effect |
|---|---|
| `--apply` | Actually write; without it nothing changes |
| `--with-permissions` | Attach a read-only permission baseline to roles |

### `check_url_references`

Scans templates for `{% url %}` tags that cannot be reversed. Useful after URL refactors.

```bash
python manage.py check_url_references
python manage.py check_url_references --paths templates jobs accounts
```

`--paths` limits the scan to directories relative to `BASE_DIR`.

### `create_user`

Creates a job seeker or client user without the OTP flow.

```bash
python manage.py create_user --type seeker \
  --username jane --email jane@example.com --password 'StrongPass123!' \
  --first-name Jane --last-name Doe --title "Django Developer" \
  --city "Addis Ababa" --country ET

python manage.py create_user --type client \
  --username acme --email hr@acme.com --password 'StrongPass123!' \
  --company "Acme PLC" --city "Addis Ababa"
```

| Option | Required | Notes |
|---|---|---|
| `--type {seeker,client}` | Yes | Profile type |
| `--username` | Yes | |
| `--email` | Yes | |
| `--password` | Yes | |
| `--first-name`, `--last-name` | No | |
| `--title` | No | Default `Professional` (seeker) |
| `--company` | No | Client company name |
| `--country` | No | Default `ET` |
| `--city` | No | |

### `post_website_update`

Scrapes job data and posts updates to Telegram groups/channels.

```bash
python manage.py post_website_update \
  --url "https://ethiojobs.net/api/..." \
  --groups -1001234567890 \
  --force
```

| Option | Required | Notes |
|---|---|---|
| `--url` | Yes | Source JSON endpoint |
| `--groups` | Yes | One or more Telegram chat IDs |
| `--selector` | No | Legacy; ignored for Next.js sites |
| `--force` | No | Repost already-seen items |

Requires network access to the source and Telegram.

### `reprice_talents`

Reconciles `Talent.price` with the published professional rate card. Dry run by default.

```bash
python manage.py reprice_talents
python manage.py reprice_talents --apply
```

Check `--help` for the exact write flag name in your checkout.

### `reset_placeholder_verifications`

Sets `is_verified=False` on seeded placeholder profiles. Dry run by default.

```bash
python manage.py reset_placeholder_verifications
python manage.py reset_placeholder_verifications --apply
python manage.py reset_placeholder_verifications --apply --include-detailed
```

`--include-detailed` also clears hand-registered profiles with detailed data.

### `scrape_tenders`

Scrapes full tender details from 2merkato and posts them to Telegram. Requires `MERKATO_EMAIL` / `MERKATO_PASSWORD` for login.

```bash
python manage.py scrape_tenders --groups -1001234567890
```

| Option | Required |
|---|---|
| `--groups` | Yes (one or more chat IDs) |

### `seed_professional_rates`

Seeds or publishes weekly professional rates.

```bash
python manage.py seed_professional_rates
python manage.py seed_professional_rates --week 2026-11-09
python manage.py seed_professional_rates --reset
```

`--week` targets the Monday that starts the week; `--reset` deletes existing rates and replaces them from the built-in seed table.

### `seed_talents`

Seeds the database with initial talent records. Intended for a fresh environment.

```bash
python manage.py seed_talents
```

### `start_file_watcher`

Starts the file system watcher that monitors changes and notifies the owner. Requires the optional `watchdog` package.

```bash
pip install -r requirements-optional.txt
python manage.py start_file_watcher
```

This is a long-running process; run it in its own terminal or under a supervisor.

### `sync_talents`

Creates or updates `Talent` records for every verified `JobSeekerProfile`.

```bash
python manage.py sync_talents
```

Run after bulk verification or profile imports.

### `transcribe_news`

Downloads YouTube audio, transcribes it, optionally translates to Amharic, and posts to Telegram. Requires optional dependencies (`yt-dlp`, `openai-whisper`, `deep-translator`) and is CPU/GPU heavy.

```bash
python manage.py transcribe_news --url "https://www.youtube.com/watch?v=..." --model base
python manage.py transcribe_news --url "..." --no-translate
```

| Option | Notes |
|---|---|
| `--url` | YouTube URL (required) |
| `--no-translate` | Skip translation |
| `--model` | Whisper size: tiny/base/small/medium/large |

---

## billing commands

### `renewal_reminders`

Expires lapsed subscriptions and reminds subscribers whose plan expires soon.

```bash
python manage.py renewal_reminders
python manage.py renewal_reminders --days 7
python manage.py renewal_reminders --dry-run
```

| Option | Default | Effect |
|---|---|---|
| `--days` | `3` | Reminder window |
| `--dry-run` | off | Report only; send nothing |

What it does:

1. Finds `active` subscriptions with `expires_at < now` and sets them to `expired`.
2. Finds `active` subscriptions expiring within the window.
3. Sends a Telegram DM when a chat ID resolves.
4. Sends an email when the user has an email address.

Schedule daily:

```cron
0 6 * * * cd /path/to/project && venv/bin/python manage.py renewal_reminders --days 3
```

### `send_digest`

Sends the daily summary to `digest`-mode subscribers.

```bash
python manage.py send_digest
python manage.py send_digest --hour 8
python manage.py send_digest --all-hours
python manage.py send_digest --lookback 48
python manage.py send_digest --dry-run
```

| Option | Default | Effect |
|---|---|---|
| `--hour` | all due | Only subscribers whose `digest_hour` matches |
| `--all-hours` | off | Ignore stored hours and digest everyone now |
| `--lookback` | `24` | Hours of posts to include |
| `--dry-run` | off | Report only |

Schedule hourly:

```cron
0 * * * * cd /path/to/project && venv/bin/python manage.py send_digest
```

### `simulate_bot`

Offline exercise of the inline-button handlers. Does not call Telegram.

```bash
python manage.py simulate_bot
```

Expected: `31/31` checks pass. Use this on a machine that cannot reach `api.telegram.org`.

### `verify_telegram`

Live checks against the Telegram Bot API.

```bash
python manage.py verify_telegram
python manage.py verify_telegram --publish
python manage.py verify_telegram --publish --delete-after
python manage.py verify_telegram --title "Deploy check"
```

Checks:

1. Token valid (`getMe`)
2. Channel reachable (`getChat`)
3. Bot is an administrator (`getChatMember`)
4. Inline keyboard serializes correctly
5. Optional test post

| Option | Effect |
|---|---|
| `--publish` | Send a test message |
| `--delete-after` | Delete the test message |
| `--title` | Test post title |

Network timeouts here usually mean the host cannot reach Telegram, not that the token is wrong.

---

## tenants commands

### `seed_tenants_from_clients`

Creates `Organization` rows from existing `ClientProfile` rows. Dry run by default.

```bash
python manage.py seed_tenants_from_clients
python manage.py seed_tenants_from_clients --apply
python manage.py seed_tenants_from_clients --apply --plan professional
```

| Option | Default | Effect |
|---|---|---|
| `--apply` | off | Actually write |
| `--plan` | `professional` | Plan slug for the seeded subscription |

---

## Standard Django commands used often

| Command | Purpose |
|---|---|
| `migrate` | Apply migrations |
| `makemigrations` | Create migrations after model changes |
| `showmigrations` | List migration state |
| `check` | System checks |
| `createsuperuser` | Create an admin |
| `changepassword <user>` | Reset a password |
| `collectstatic` | Collect static files |
| `shell` | Python shell with Django loaded |
| `dbshell` | Database shell |
| `test` | Run tests |
| `sendtestemail <addr>` | Verify email configuration |
| `dumpdata` / `loaddata` | Export/import fixtures |

## Operational schedule example

```cron
# Daily digest fan-out
0 * * * * cd /path/to/project && venv/bin/python manage.py send_digest >> logs/digest.log 2>&1

# Expiry reminders + expirations
0 6 * * * cd /path/to/project && venv/bin/python manage.py renewal_reminders --days 3 >> logs/reminders.log 2>&1

# Optional scrapers
*/30 * * * * cd /path/to/project && venv/bin/python manage.py post_website_update --url "$SCRAPER_URL" --groups "$CHANNEL_ID" >> logs/scraper.log 2>&1
```

Keep the Telegram bot running separately (polling) or use the webhook. Do not run both.

## Exit codes and logging

All custom commands print to stdout/stderr and exit non-zero on unhandled exceptions. Wrap cron jobs with `>> logs/<name>.log 2>&1` and monitor the log. `verify_telegram` exits non-zero on failed checks.
