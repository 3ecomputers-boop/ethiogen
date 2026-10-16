# jobs/telegram_utils.py
import os
import logging
from django.conf import settings
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# Your bot token – best stored in settings
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or getattr(settings, 'TELEGRAM_BOT_TOKEN', None)

def get_bot():
    """Return a Telegram Bot instance."""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None
    return Bot(token=BOT_TOKEN)

def send_verified_talent_post(seeker_profile):
    """
    Send a message to a Telegram channel/group announcing a newly verified job seeker.
    """
    bot = get_bot()
    if not bot:
        return False

    # The target chat ID – set this in your settings or environment
    # For a public channel, use @channelusername; for a group or private chat, use the numeric ID.
    chat_id = getattr(settings, 'TELEGRAM_VERIFIED_CHAT_ID', '@your_channel_username')

    user = seeker_profile.user
    full_name = user.get_full_name() or user.username
    title = seeker_profile.title or 'Professional'
    location = seeker_profile.city or seeker_profile.country or 'Unknown location'
    rate = seeker_profile.hourly_rate or 'Negotiable'
    skills = seeker_profile.skills if isinstance(seeker_profile.skills, list) else []
    skills_str = ', '.join(skills[:5]) if skills else 'Various skills'
    profile_url = f"https://yourdomain.com/profile/{seeker_profile.id}/"  # change to your actual URL

    # Build the message
    message = (
        f"✅ **New Verified Talent!**\n\n"
        f"👤 **{full_name}**\n"
        f"💼 {title}\n"
        f"📍 {location}\n"
        f"💰 Rate: {rate} ETB/hour\n"
        f"🛠️ Skills: {skills_str}\n\n"
        f"🔗 [View Profile]({profile_url})"
    )

    # Optionally send a photo if they have a profile picture
    photo_path = seeker_profile.profile_picture.path if seeker_profile.profile_picture else None

    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                bot.send_photo(chat_id=chat_id, photo=photo, caption=message, parse_mode='Markdown')
        else:
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        logger.info(f"Verified talent post sent for user {user.username}")
        return True
    except TelegramError as e:
        logger.error(f"Failed to send verified talent post: {e}")
        return False