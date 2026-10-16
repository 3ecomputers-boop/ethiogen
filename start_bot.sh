#!/bin/bash
# Start the Ethiogen Telegram bot.
#
# The bot lives at bot/bot.py. It resolves its token, channel id and group
# id from (in order):
#   1. Django admin  ->  Billing -> Integration settings
#   2. the environment (including anything loaded from .env below)
# so the admin can rotate the token without editing this file.
#
# NO SECRETS BELOW. A real token used to be hardcoded here as a fallback,
# which leaked it into git. The token now lives in .env (gitignored) and in
# the admin, never in a tracked file.

PROJECT_DIR="/home/syorelig/ethiogen/job_portal"
VENV_PYTHON="/home/syorelig/virtualenv/ethiogen/3.13/bin/python"
BOT_SCRIPT="bot/bot.py"
LOG_FILE="$PROJECT_DIR/bot.log"
PID_FILE="$PROJECT_DIR/bot.pid"

cd "$PROJECT_DIR" || exit 1

# Load secrets from .env if it exists. It is gitignored, so this is the
# right place for them.
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

# Already running?
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null; then
        echo "Bot is already running with PID $PID"
        exit 0
    fi
    echo "Stale PID file found. Removing..."
    rm -f "$PID_FILE"
fi

if pgrep -f "$BOT_SCRIPT" > /dev/null; then
    echo "Bot process is already running."
    exit 0
fi

# Fail loudly rather than starting with no token: it looks like it works
# and then silently does nothing.
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN is not set."
    echo "  Put it in $PROJECT_DIR/.env, or set it in Billing -> Integration settings."
    exit 1
fi

export ETHIOGEN_BOT_USERNAME="${ETHIOGEN_BOT_USERNAME:-ethiogenjob_bot}"
export ETHIOGEN_CHANNEL_USERNAME="${ETHIOGEN_CHANNEL_USERNAME:-ethiogenjob}"

echo "Starting Ethiogen Bot..."
nohup "$VENV_PYTHON" "$PROJECT_DIR/$BOT_SCRIPT" > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "Bot started with PID $(cat $PID_FILE)"