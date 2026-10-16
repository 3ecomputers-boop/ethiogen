#!/bin/bash
# keep_alive.sh - Restart the Ethiogen bot if it dies.
#
# The bot is bot/bot.py (the single, authoritative bot). It used to point at
# telegram_invite.py, which does not exist in this directory.
#
# Note: for cPanel, use the root start_bot.sh instead; this script is for a
# plain Linux/VPS or a cron-driven watchdog.
#
# NO SECRETS BELOW -- see start_bot.sh. The token comes from .env or the
# admin, never from a tracked file.

PROJECT_DIR="/home/syorelig/ethiogen/job_portal"
VENV_PYTHON="/home/syorelig/virtualenv/ethiogen/3.13/bin/python"
BOT_SCRIPT="bot/bot.py"
LOG_FILE="$PROJECT_DIR/bot.log"

cd "$PROJECT_DIR" || exit 1

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

if ! pgrep -f "$BOT_SCRIPT" > /dev/null; then
    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        echo "$(date): TELEGRAM_BOT_TOKEN is not set; not restarting." >> "$LOG_FILE"
        exit 1
    fi
    echo "$(date): Bot not found. Restarting..." >> "$LOG_FILE"
    nohup "$VENV_PYTHON" "$PROJECT_DIR/$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PROJECT_DIR/bot.pid"
    echo "$(date): Restarted with PID $!" >> "$LOG_FILE"
else
    echo "$(date): Bot is running."
fi