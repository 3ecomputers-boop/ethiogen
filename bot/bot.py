"""
Ethiogen Advanced Job Portal Telegram Bot — unified.

Combines:
  * The full job portal (profiles, jobs, applications, ratings, nearby, favorites)
  * Invitation / referral utilities
  * Channel subscription gate (force-join)
  * Inline buttons for @ethiogenjob and ethiogen.com

Requires: python-telegram-bot v20+, Django configured, asgiref.
Run from the Django project root:
    TELEGRAM_BOT_TOKEN="..." python telegram_bot.py
"""
from __future__ import annotations

import asyncio
import html
import logging
import math
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import django
from asgiref.sync import sync_to_async
from telegram import (
    ChatMember,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------
# Django initialization
# ---------------------------------------------------------------------
# This file lives in <project>/bot/, so the project root (which holds the
# manage.py and the job_portal package) is the PARENT directory. Using
# .parent here instead of the old .parent-only-dir value means
# `import job_portal` resolves correctly no matter where the bot is started
# from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "job_portal.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.db.models import Avg, Q
from django.utils import timezone

from jobs.models import (
    ClientProfile,
    JobSeekerProfile,
    Profession,
    Category,
    SubCategory,
    WorkerRating,
    UserPreference,
    TelegramProfile,
    JobPost,
    JobApplication,
    FavoriteWorker,
)

User = get_user_model()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("ethiogen.telegram")

# ---------------------------------------------------------------------
# Configuration
#
# Resolution order for the bot token and channel/group ids is:
#   1. Billing -> Integration settings (edited in the Django admin)
#   2. environment variable
#   3. hardcoded default
# so an administrator can rotate the token without editing .env or
# restarting the bot.
# ---------------------------------------------------------------------
def _cfg(name, default=None):
    """Read a billing config value, tolerating a missing app/table."""
    try:
        from billing import config

        return getattr(config, name)()
    except Exception as exc:  # Django app not ready, table missing, etc.
        logger.debug("billing.config.%s() unavailable: %s", name, exc)
        return default


TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    or os.getenv("ETHIOGEN_BOT_TOKEN", "").strip()
    or _cfg("telegram_token", "")
)
if not TOKEN:
    raise RuntimeError(
        "No Telegram bot token. Set it in Django admin under "
        "Billing -> Integration settings, or export TELEGRAM_BOT_TOKEN."
    )

CHANNEL_USERNAME = (
    os.getenv("ETHIOGEN_CHANNEL_USERNAME")
    or _cfg("telegram_bot_username", "")
    or "ethiogenjob"
).lstrip("@")
BOT_USERNAME = (
    os.getenv("ETHIOGEN_BOT_USERNAME")
    or _cfg("telegram_bot_username", "")
    or "ethiogenjob_bot"
).lstrip("@")
WEBSITE_URL = _cfg("website_url", "https://ethiogen.com")
CHANNEL_URL = f"https://t.me/{CHANNEL_USERNAME}"

EXCHANGE_RATE = Decimal(os.getenv("ETHIOGEN_USD_ETB_RATE", "55.0"))
DEFAULT_PER_PAGE = 5
MAX_BIO = 500
MAX_SEARCH = 100
MEDIA_ROOT = Path(os.getenv("ETHIOGEN_BOT_MEDIA_ROOT", "media/telegram"))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

ADMIN_IDS = set(_cfg("telegram_admin_ids", set())) or {
    int(v)
    for v in os.getenv("ETHIOGEN_ADMIN_IDS", "").split(",")
    if v.strip().isdigit()
}
SCRAPER_GROUP_ID = (
    os.getenv("ETHIOGEN_UPDATE_GROUP_ID") or _cfg("telegram_channel_id", "")
)
SCRAPER_URL = os.getenv("ETHIOGEN_SCRAPER_URL", "https://ethiojobs.net/jobs/")
SCRAPER_SELECTOR = os.getenv("ETHIOGEN_SCRAPER_SELECTOR", ".job-detail-header-title")

SUBSCRIBED_STATUSES = {
    ChatMember.MEMBER,
    ChatMember.ADMINISTRATOR,
    ChatMember.OWNER,
}

# ---------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------
(
    CREATE_PROFILE,
    CLIENT_LOCATION,
    SEEKER_CATEGORY,
    SEEKER_SUBCAT,
    SEEKER_PROF,
    SEEKER_EXP,
    SEEKER_LOC,
    SEEKER_PRICE,
    SEEKER_UNIT,
    SEEKER_BIO,
    SEEKER_IMAGE,
    SEEKER_VOICE,
    SEEKER_VIDEO,
    SEARCH_QUERY,
    RATING_VALUE,
    RATING_COMMENT,
    JOB_POST_TITLE,
    JOB_POST_DESC,
    JOB_POST_CATEGORY,
    JOB_POST_SUBCAT,
    JOB_POST_BUDGET,
    JOB_POST_LOCATION,
    JOB_POST_DEADLINE,
    JOB_APPLY_COVER,
    JOB_APPLY_BID,
    NEARBY_LOCATION,
    NEARBY_WORKERS_RADIUS,
) = range(27)

# ---------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------
TEXTS = {
    "en": {
        "welcome": "Welcome to Ethiogen 🚀, {username}!",
        "main_menu": "🏠 *Main Menu*\nChoose an option:",
        "create_profile": "🧑‍💼 Create Profile",
        "my_profile": "👤 My Profile",
        "browse_talent": "📄 Browse Talent",
        "settings": "⚙️ Settings",
        "help": "❓ Help",
        "search": "🔍 Search Workers",
        "post_job": "📢 Post a Job",
        "my_jobs": "📋 My Jobs",
        "favorites": "❤️ Favorites",
        "nearby": "📍 Nearby Workers",
        "invite": "👥 Invite Friends",
        "role_select": "What type of profile do you want to create?",
        "client_role": "👔 Client — I want to hire",
        "jobseeker_role": "🛠️ Job Seeker — I want to work",
        "back": "🔙 Back",
        "cancel": "🚫 Cancelled. Returning to the main menu.",
        "client_location_prompt": "📍 Enter your city/area:",
        "client_success": "✅ Client profile created successfully!",
        "jobseeker_category": "📂 Select your work category:",
        "jobseeker_subcategory": "📁 Select a subcategory:",
        "jobseeker_profession": "🔧 Select your profession:",
        "profession_other": "✏️ Enter your profession:",
        "jobseeker_experience": "⏳ Years of experience (0–60):",
        "jobseeker_location": "📍 Enter your city/area:",
        "jobseeker_price": "💰 Price per unit (e.g. 25.50):",
        "jobseeker_unit": "⏱️ Select pricing unit:",
        "jobseeker_bio": "📝 Short bio, or /skip:",
        "jobseeker_image": "📸 Send a profile photo, or /skip:",
        "jobseeker_voice": "🎤 Send a voice introduction, or /skip:",
        "jobseeker_video": "📹 Send a video introduction, or /skip:",
        "jobseeker_success": "✅ Job Seeker profile created successfully!",
        "my_profile_client": "👤 *Client Profile*\n📍 Location: {location}",
        "my_profile_seeker": (
            "🛠️ *Job Seeker Profile*\n"
            "• Profession: {prof}\n"
            "• Category: {cat} / {subcat}\n"
            "• Experience: {exp} yrs\n"
            "• Location: {loc}\n"
            "• Rate: {price} {unit}\n"
            "• ⭐ Rating: {rating:.1f}/5\n"
            "• Bio: {bio}\n"
            "• Verified: {verified}\n"
            "• Status: {status}"
        ),
        "no_profile": "You don't have a profile yet. Tap Create Profile.",
        "no_talent": "📭 No active workers match your search.",
        "talent_list": "📄 *Available Talent* — Page {page}/{total_pages}\n",
        "search_prompt": "🔎 Enter a name, profession, location, or keyword:",
        "search_results": "🔎 *Search Results*\n",
        "rating_select": "⭐ Select a rating from 1 to 5:",
        "rating_comment": "Add a comment, or /skip:",
        "rating_thanks": "Thank you for your feedback! ⭐",
        "favorite_added": "✅ Worker added to favorites!",
        "favorite_removed": "❌ Worker removed from favorites.",
        "favorites_empty": "You have no favorite workers yet.",
        "favorites_list": "❤️ *Your Favorite Workers*\n",
        "nearby_prompt": "📍 Share your location to find workers nearby.",
        "nearby_radius": "Select search radius:",
        "nearby_results": "📍 *Workers within {radius} km*\n",
        "no_nearby": "No workers found in that radius.",
        "post_job_title": "📌 Job title:",
        "post_job_desc": "📝 Job description:",
        "post_job_category": "📂 Job category:",
        "post_job_subcategory": "📁 Job subcategory:",
        "post_job_budget": "💰 Budget (ETB):",
        "post_job_location": "📍 Job location:",
        "post_job_deadline": "📅 Deadline (YYYY-MM-DD):",
        "post_job_success": "✅ Job posted! Job ID: {job_id}",
        "my_jobs_list": "📋 *Your Job Postings*\n",
        "apply_cover": "📝 Cover letter, or /skip:",
        "apply_bid": "💰 Your bid amount (ETB):",
        "apply_success": "✅ Application submitted!",
        "already_applied": "You have already applied to this job.",
        "application_list": "📋 *Applications for {title}*\n",
        "hire_success": "🎉 {username} has been hired.",
        "settings_menu": "⚙️ *Settings*\n🌐 Language: {lang}\n💱 Currency: {curr}",
        "change_lang": "🌐 Change Language",
        "change_curr": "💱 Change Currency",
        "lang_selected": "🌐 Language changed to English 🇬🇧",
        "currency_selected": "💱 Currency changed to {currency}",
        "help_text": (
            "❓ *Ethiogen Help*\n\n"
            "1. Create a Client or Job Seeker profile.\n"
            "2. Browse or search workers.\n"
            "3. Save workers to Favorites.\n"
            "4. Post jobs and receive applications.\n"
            "5. Apply to jobs as a Job Seeker.\n"
            "6. Rate workers after working together.\n"
            "7. Use Nearby to search by GPS.\n"
            "8. Use Invite Friends to share your referral link."
        ),
        "invalid_number": "❌ Please enter a valid number.",
        "invalid_price": "❌ Please enter a valid positive price.",
        "invalid_date": "❌ Use YYYY-MM-DD and choose today or a future date.",
        "photo_or_skip": "Please send a photo or /skip.",
        "file_or_skip": "Please send the requested file or /skip.",
        # ---- Subscription gate ----
        "gate_text": (
            "🔒 *Hello {username}!*\n\n"
            "To use Ethiogen you need to join our Telegram channel first.\n\n"
            "📢 @{channel}\n\n"
            "1️⃣ Tap *Join Channel* below.\n"
            "2️⃣ Come back and tap *✅ Check Subscription*."
        ),
        "gate_join": "📢 Join @{channel}",
        "gate_check": "✅ Check Subscription",
        "gate_visit": "🌐 Visit Ethiogen.com",
        "gate_ok": "✅ Subscription confirmed. Thank you!",
        "gate_fail": "❌ You are not subscribed yet. Please join @{channel} and try again.",
        # ---- Invitation / referral ----
        "invite_text": (
            "👥 *Invite friends to Ethiogen, {username}!*\n\n"
            "Share your personal referral link:\n"
            "`{link}`\n\n"
            "Help your friends discover jobs, tenders and workforce opportunities."
        ),
        "invite_share": "📤 Share My Referral Link",
        "invite_back": "🔙 Back",
        "share_text": (
            "🇪🇹 Join Ethiogen for jobs, tenders and workforce opportunities in Ethiopia!"
        ),
    },
    "am": {
        "welcome": "እንኳን ወደ ኢትዮጂን በደህና መጡ 🚀, {username}!",
        "main_menu": "🏠 *ዋና ምናሌ*\nአንድ አማራጭ ይምረጡ፦",
        "create_profile": "🧑‍💼 መገለጫ ፍጠር",
        "my_profile": "👤 መገለጫዬ",
        "browse_talent": "📄 ሰራተኞችን ያስሱ",
        "settings": "⚙️ ቅንብሮች",
        "help": "❓ እርዳታ",
        "search": "🔍 ሰራተኛ ፈልግ",
        "post_job": "📢 ስራ አስቀምጥ",
        "my_jobs": "📋 ስራዎቼ",
        "favorites": "❤️ የተወደዱ",
        "nearby": "📍 በአቅራቢያ ያሉ",
        "invite": "👥 ጓደኞችን ጋብዝ",
        "role_select": "ምን አይነት መገለጫ መፍጠር ይፈልጋሉ?",
        "client_role": "👔 ተቀጣሪ — መቅጠር እፈልጋለሁ",
        "jobseeker_role": "🛠️ ስራ ፈላጊ — መስራት እፈልጋለሁ",
        "back": "🔙 ተመለስ",
        "cancel": "🚫 ተሰርዟል። ወደ ዋና ምናሌ ተመለስ።",
        "client_location_prompt": "📍 ከተማዎን/አካባቢዎን ያስገቡ፦",
        "client_success": "✅ የተቀጣሪ መገለጫ ተፈጥሯል!",
        "jobseeker_category": "📂 የስራ ምድብ ይምረጡ፦",
        "jobseeker_subcategory": "📁 ንዑስ ምድብ ይምረጡ፦",
        "jobseeker_profession": "🔧 ሙያ ይምረጡ፦",
        "profession_other": "✏️ የሙያዎን ስም ያስገቡ፦",
        "jobseeker_experience": "⏳ የልምድ ዓመት (0–60)፦",
        "jobseeker_location": "📍 ከተማዎን/አካባቢዎን ያስገቡ፦",
        "jobseeker_price": "💰 በአሃድ ዋጋ (ለምሳሌ 25.50)፦",
        "jobseeker_unit": "⏱️ የዋጋ አሃድ ይምረጡ፦",
        "jobseeker_bio": "📝 አጭር መግለጫ፣ ወይም /skip፦",
        "jobseeker_image": "📸 የመገለጫ ፎቶ ይላኩ፣ ወይም /skip፦",
        "jobseeker_voice": "🎤 የድምፅ መግቢያ ይላኩ፣ ወይም /skip፦",
        "jobseeker_video": "📹 የቪዲዮ መግቢያ ይላኩ፣ ወይም /skip፦",
        "jobseeker_success": "✅ የስራ ፈላጊ መገለጫ ተፈጥሯል!",
        "my_profile_client": "👤 *የተቀጣሪ መገለጫ*\n📍 አካባቢ፦ {location}",
        "my_profile_seeker": (
            "🛠️ *የስራ ፈላጊ መገለጫ*\n"
            "• ሙያ፦ {prof}\n• ምድብ፦ {cat} / {subcat}\n"
            "• ልምድ፦ {exp} ዓመት\n• አካባቢ፦ {loc}\n"
            "• ዋጋ፦ {price} {unit}\n• ⭐ ደረጃ፦ {rating:.1f}/5\n"
            "• መግለጫ፦ {bio}\n• የተረጋገጠ፦ {verified}\n• ሁኔታ፦ {status}"
        ),
        "no_profile": "እስካሁን መገለጫ የለዎትም። መገለጫ ፍጠር የሚለውን ይጫኑ።",
        "no_talent": "📭 ከፍለጋዎ ጋር የሚዛመድ ንቁ ሰራተኛ አልተገኘም።",
        "talent_list": "📄 *የሚገኙ ሰራተኞች* — ገጽ {page}/{total_pages}\n",
        "search_prompt": "🔎 ስም፣ ሙያ፣ አካባቢ ወይም ቁልፍ ቃል ያስገቡ፦",
        "search_results": "🔎 *የፍለጋ ውጤቶች*\n",
        "rating_select": "⭐ ከ1 እስከ 5 ደረጃ ይምረጡ፦",
        "rating_comment": "አስተያየት ይጻፉ፣ ወይም /skip፦",
        "rating_thanks": "ለአስተያየትዎ እናመሰግናለን! ⭐",
        "favorite_added": "✅ ሰራተኛው ወደ የተወደዱ ተጨምሯል!",
        "favorite_removed": "❌ ሰራተኛው ከየተወደዱ ተወግዷል።",
        "favorites_empty": "እስካሁን የተወደዱ ሰራተኞች የሉዎትም።",
        "favorites_list": "❤️ *የተወደዱ ሰራተኞች*\n",
        "nearby_prompt": "📍 በአቅራቢያዎ ያሉ ሰራተኞችን ለማግኘት አካባቢዎን ያጋሩ።",
        "nearby_radius": "የፍለጋ ርቀት ይምረጡ፦",
        "nearby_results": "📍 *በ{radius} ኪ.ሜ ውስጥ ያሉ ሰራተኞች*\n",
        "no_nearby": "በዚህ ርቀት ውስጥ ሰራተኛ አልተገኘም።",
        "post_job_title": "📌 የስራ ርዕስ፦",
        "post_job_desc": "📝 የስራ መግለጫ፦",
        "post_job_category": "📂 የስራ ምድብ፦",
        "post_job_subcategory": "📁 የስራ ንዑስ ምድብ፦",
        "post_job_budget": "💰 በጀት (ETB)፦",
        "post_job_location": "📍 የስራ አካባቢ፦",
        "post_job_deadline": "📅 የማመልከቻ ገደብ (YYYY-MM-DD)፦",
        "post_job_success": "✅ ስራ በተሳካ ሁኔታ ተለጥፏል! ID፦ {job_id}",
        "my_jobs_list": "📋 *የስራ ማስታወቂያዎችዎ*\n",
        "apply_cover": "📝 የሽፋን ደብዳቤ፣ ወይም /skip፦",
        "apply_bid": "💰 የጨረታ መጠን (ETB)፦",
        "apply_success": "✅ ማመልከቻ ቀርቧል!",
        "already_applied": "ቀድሞውኑ ለዚህ ስራ አመልክተዋል።",
        "application_list": "📋 *ለ{title} የቀረቡ ማመልከቻዎች*\n",
        "hire_success": "🎉 {username} ተቀጥሯል።",
        "settings_menu": "⚙️ *ቅንብሮች*\n🌐 ቋንቋ፦ {lang}\n💱 ገንዘብ፦ {curr}",
        "change_lang": "🌐 ቋንቋ ቀይር",
        "change_curr": "💱 ገንዘብ ቀይር",
        "lang_selected": "🌐 ቋንቋ ወደ አማርኛ 🇪🇹 ተቀይሯል",
        "currency_selected": "💱 ገንዘብ ወደ {currency} ተቀይሯል",
        "help_text": (
            "❓ *የኢትዮጂን እርዳታ*\n\n"
            "1. የተቀጣሪ ወይም የስራ ፈላጊ መገለጫ ይፍጠሩ።\n"
            "2. ሰራተኞችን ያስሱ ወይም ይፈልጉ።\n"
            "3. የሚፈልጓቸውን ሰራተኞች ወደ የተወደዱ ያስቀምጡ።\n"
            "4. ስራ ይለጥፉ እና ማመልከቻዎችን ይቀበሉ።\n"
            "5. እንደ ስራ ፈላጊ ለስራዎች ያመልክቱ።\n"
            "6. ከስራ በኋላ ደረጃ ይስጡ።\n"
            "7. Nearby በመጠቀም በGPS ይፈልጉ።\n"
            "8. Invite Friends በመጠቀም ያጋሩ።"
        ),
        "invalid_number": "❌ ትክክለኛ ቁጥር ያስገቡ።",
        "invalid_price": "❌ ትክክለኛ አዎንታዊ ዋጋ ያስገቡ።",
        "invalid_date": "❌ YYYY-MM-DD ቅርጸት ይጠቀሙ እና ዛሬ ወይም የወደፊት ቀን ይምረጡ።",
        "photo_or_skip": "እባክዎ ፎቶ ይላኩ ወይም /skip ይጻፉ።",
        "file_or_skip": "እባክዎ የተጠየቀውን ፋይል ይላኩ ወይም /skip ይጻፉ።",
        # ---- Subscription gate ----
        "gate_text": (
            "🔒 *ሰላም {username}!*\n\n"
            "ኢትዮጂንን ለመጠቀም መጀመሪያ የቴሌግራም ቻናላችንን መቀላቀል ይኖርብዎታል።\n\n"
            "📢 @{channel}\n\n"
            "1️⃣ *Join Channel* የሚለውን ይጫኑ።\n"
            "2️⃣ ተመልሰው *✅ Check Subscription* ይጫኑ።"
        ),
        "gate_join": "📢 @{channel} ተቀላቀል",
        "gate_check": "✅ ምዝገባን አረጋግጥ",
        "gate_visit": "🌐 Ethiogen.com ጎብኝ",
        "gate_ok": "✅ ምዝገባዎ ተረጋግጧል። እናመሰግናለን!",
        "gate_fail": "❌ እስካሁን አልተቀላቀሉም። @{channel} ተቀላቅለው እንደገና ይሞክሩ።",
        # ---- Invitation / referral ----
        "invite_text": (
            "👥 *ጓደኞችን ወደ ኢትዮጂን ይጋብዙ፣ {username}!*\n\n"
            "የግል ማጣቀሻ አገናኝዎን ያጋሩ፦\n"
            "`{link}`\n\n"
            "ጓደኞችዎ ስራዎችን፣ ጨረታዎችን እና የሰው ኃይል ዕድሎችን እንዲያገኙ ይርዷቸው።"
        ),
        "invite_share": "📤 የማጣቀሻ አገናኜን አጋራ",
        "invite_back": "🔙 ተመለስ",
        "share_text": "🇪🇹 ለስራ፣ ለጨረታ እና ለሰው ኃይል ዕድሎች ኢትዮጂንን ይቀላቀሉ!",
    },
}

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def esc(value: object) -> str:
    """Escape text for parse_mode=HTML."""
    return html.escape(str(value), quote=False)


_MARKDOWN_ESCAPE_RE = re.compile(r"([_*`\[\]])")


def safe_username(user) -> str:
    """Return a Markdown-safe display name for the given Telegram user or model user."""
    raw = (
        getattr(user, "username", None)
        or getattr(user, "first_name", None)
        or "User"
    )
    return _MARKDOWN_ESCAPE_RE.sub(r"\\\1", str(raw))


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    earth_radius = 6371.0088
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return earth_radius * 2 * math.asin(math.sqrt(a))


def get_referral_link(user_id: int) -> str:
    if not BOT_USERNAME:
        raise ValueError("ETHIOGEN_BOT_USERNAME is not configured")
    return f"https://t.me/{BOT_USERNAME}?start=ref_{int(user_id)}"


def get_share_url(user_id: Optional[int] = None, language: str = "en") -> str:
    language = language if language in TEXTS else "en"
    target = get_referral_link(user_id) if user_id else CHANNEL_URL
    text = TEXTS[language]["share_text"]
    return (
        "https://t.me/share/url"
        f"?url={quote(target, safe='')}"
        f"&text={quote(text, safe='')}"
    )


def get_referrer_from_start_argument(start_argument: Optional[str]) -> Optional[int]:
    if not start_argument:
        return None
    match = re.fullmatch(r"ref_(\d+)", start_argument.strip())
    return int(match.group(1)) if match else None


def clear_flow_data(context: ContextTypes.DEFAULT_TYPE):
    for key in list(context.user_data):
        if key.startswith(("seeker_", "job_", "apply_", "rating_", "nearby_")):
            context.user_data.pop(key, None)


async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
    except Exception as exc:
        logger.warning("get_chat_member failed for %s: %s", user_id, exc)
        return False
    if member.status in SUBSCRIBED_STATUSES:
        return True
    return bool(getattr(member, "is_member", False))


# ---------------------------------------------------------------------
# Async ORM helpers
# ---------------------------------------------------------------------
@sync_to_async
def get_user_pref(user_id: int):
    pref, _ = UserPreference.objects.get_or_create(user_id=user_id)
    return pref


@sync_to_async
def get_text(user_id: int, key: str, **kwargs) -> str:
    try:
        pref = UserPreference.objects.filter(user_id=user_id).first()
        language = pref.language if pref and pref.language in TEXTS else "en"
    except Exception:
        language = "en"
    text = TEXTS[language].get(key, TEXTS["en"].get(key, key))
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError):
        return text


@sync_to_async
def set_user_language(user_id: int, language: str):
    pref, _ = UserPreference.objects.get_or_create(user_id=user_id)
    pref.language = language
    pref.save(update_fields=["language"])


@sync_to_async
def set_user_currency(user_id: int, currency: str):
    pref, _ = UserPreference.objects.get_or_create(user_id=user_id)
    pref.currency = currency
    pref.save(update_fields=["currency"])


@sync_to_async
def format_currency(amount: Decimal, user_id: int) -> str:
    pref = UserPreference.objects.filter(user_id=user_id).first()
    currency = getattr(pref, "currency", "ETB") or "ETB"
    if currency == "USD":
        return f"${amount / EXCHANGE_RATE:.2f}"
    return f"ETB {amount:.2f}"


@sync_to_async
def get_or_create_user(chat_id: int, username: Optional[str] = None):
    tg = TelegramProfile.objects.filter(chat_id=str(chat_id)).select_related("user").first()
    if tg:
        return tg.user

    base = (username or f"tg_{chat_id}").strip()[:120]
    base = re.sub(r"[^A-Za-z0-9_.@+-]", "_", base) or f"tg_{chat_id}"
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base[:110]}_{suffix}"
        suffix += 1

    user = User.objects.create_user(username=candidate)
    TelegramProfile.objects.create(user=user, chat_id=str(chat_id))
    UserPreference.objects.get_or_create(user=user)
    return user


@sync_to_async
def update_user_activity(user_id: int):
    try:
        tg = TelegramProfile.objects.get(user_id=user_id)
        changed = []
        if hasattr(tg, "last_seen"):
            tg.last_seen = timezone.now()
            changed.append("last_seen")
        if hasattr(tg, "is_online"):
            tg.is_online = True
            changed.append("is_online")
        if changed:
            tg.save(update_fields=changed)
    except TelegramProfile.DoesNotExist:
        logger.warning("TelegramProfile missing for user %s", user_id)


@sync_to_async
def get_user_by_id(user_id: int):
    return User.objects.get(id=user_id)


@sync_to_async
def create_client_profile(user_id: int, location: str):
    return ClientProfile.objects.update_or_create(
        user_id=user_id, defaults={"location": location.strip()}
    )


@sync_to_async
def get_categories():
    return list(Category.objects.all().order_by("name"))


@sync_to_async
def get_subcategories(category_id: int):
    return list(SubCategory.objects.filter(category_id=category_id).order_by("name"))


@sync_to_async
def get_professions():
    return list(Profession.objects.all().order_by("name"))


@sync_to_async
def get_or_create_profession(name: str):
    return Profession.objects.get_or_create(name=name.strip())


@sync_to_async
def create_jobseeker_profile(user_id: int, **kwargs):
    JobSeekerProfile.objects.filter(user_id=user_id, is_active=True).update(is_active=False)
    return JobSeekerProfile.objects.create(user_id=user_id, **kwargs)


@sync_to_async
def get_filtered_jobseekers(
    category_id=None,
    subcategory_id=None,
    search=None,
    page=1,
    per_page=DEFAULT_PER_PAGE,
):
    qs = (
        JobSeekerProfile.objects.filter(is_active=True)
        .select_related("user", "profession", "category", "subcategory")
        .annotate(avg_rating=Avg("ratings__rating"))
    )
    if category_id:
        qs = qs.filter(category_id=category_id)
    if subcategory_id:
        qs = qs.filter(subcategory_id=subcategory_id)
    if search:
        search = search[:MAX_SEARCH]
        qs = qs.filter(
            Q(user__username__icontains=search)
            | Q(profession__name__icontains=search)
            | Q(location__icontains=search)
            | Q(bio__icontains=search)
        )
    total = qs.count()
    page = max(1, int(page))
    start = (page - 1) * per_page
    return list(qs.order_by("-avg_rating", "-id")[start:start + per_page]), total


@sync_to_async
def get_jobseeker_details(seeker_id: int):
    return (
        JobSeekerProfile.objects.select_related(
            "user", "profession", "category", "subcategory"
        )
        .annotate(avg_rating=Avg("ratings__rating"))
        .get(id=seeker_id)
    )


@sync_to_async
def add_rating(seeker_id: int, client_user_id: int, rating: int, comment: str):
    seeker = JobSeekerProfile.objects.get(id=seeker_id)
    client = ClientProfile.objects.get(user_id=client_user_id)
    WorkerRating.objects.update_or_create(
        job_seeker=seeker,
        client=client,
        defaults={"rating": rating, "comment": comment or ""},
    )
    avg = WorkerRating.objects.filter(job_seeker=seeker).aggregate(avg=Avg("rating"))["avg"] or 0
    if hasattr(seeker, "average_rating"):
        seeker.average_rating = avg
        seeker.save(update_fields=["average_rating"])


@sync_to_async
def toggle_favorite(client_user_id: int, seeker_id: int) -> bool:
    client = ClientProfile.objects.get(user_id=client_user_id)
    seeker = JobSeekerProfile.objects.get(id=seeker_id)
    favorite, created = FavoriteWorker.objects.get_or_create(
        client=client, job_seeker=seeker
    )
    if not created:
        favorite.delete()
        return False
    return True


@sync_to_async
def is_favorite(client_user_id: int, seeker_id: int) -> bool:
    return FavoriteWorker.objects.filter(
        client__user_id=client_user_id, job_seeker_id=seeker_id
    ).exists()


@sync_to_async
def get_favorite_workers(user_id: int):
    favorites = (
        FavoriteWorker.objects.filter(client__user_id=user_id)
        .select_related("job_seeker", "job_seeker__user", "job_seeker__profession")
    )
    return [fav.job_seeker for fav in favorites if fav.job_seeker.is_active]


@sync_to_async
def get_job_posts(user_id: int):
    return list(JobPost.objects.filter(client__user_id=user_id).order_by("-created_at"))


@sync_to_async
def create_job_post(
    user_id: int,
    title: str,
    description: str,
    category_id: Optional[int],
    subcategory_id: Optional[int],
    budget: Decimal,
    location: str,
    deadline,
):
    client = ClientProfile.objects.get(user_id=user_id)
    category = Category.objects.filter(id=category_id).first() if category_id else None
    subcategory = SubCategory.objects.filter(id=subcategory_id).first() if subcategory_id else None
    return JobPost.objects.create(
        client=client,
        title=title,
        description=description,
        category=category,
        subcategory=subcategory,
        budget=budget,
        location=location,
        deadline=deadline,
        is_active=True,
    )


@sync_to_async
def apply_to_job(job_id: int, seeker_user_id: int, cover: str, bid: Decimal):
    job = JobPost.objects.get(id=job_id)
    if hasattr(job, "is_active") and not job.is_active:
        return None, "closed"
    seeker = JobSeekerProfile.objects.get(user_id=seeker_user_id, is_active=True)
    application, created = JobApplication.objects.get_or_create(
        job=job,
        job_seeker=seeker,
        defaults={"cover_letter": cover, "bid_amount": bid},
    )
    return application, ("created" if created else "exists")


@sync_to_async
def get_job_applications(job_id: int):
    return list(
        JobApplication.objects.filter(job_id=job_id).select_related(
            "job", "job_seeker", "job_seeker__user"
        )
    )


@sync_to_async
def hire_worker(job_id: int, seeker_id: int, client_user_id: int):
    application = (
        JobApplication.objects.select_related("job", "job_seeker", "job_seeker__user").get(
            job_id=job_id, job_seeker_id=seeker_id, job__client__user_id=client_user_id
        )
    )
    application.status = "hired"
    application.save(update_fields=["status"])
    return application


@sync_to_async
def get_nearby_seekers(latitude: float, longitude: float, radius_km: float, limit=20):
    qs = JobSeekerProfile.objects.filter(
        is_active=True, latitude__isnull=False, longitude__isnull=False
    ).select_related("user", "profession", "category", "subcategory")
    results = []
    for seeker in qs.iterator():
        distance = haversine_km(latitude, longitude, seeker.latitude, seeker.longitude)
        if distance <= radius_km:
            seeker.distance_km = distance
            results.append(seeker)
    results.sort(key=lambda x: x.distance_km)
    return results[:limit]


# ---------------------------------------------------------------------
# Profile text
# ---------------------------------------------------------------------
async def user_profile_text(user_id: int) -> tuple[str, Optional[str]]:
    user = await get_user_by_id(user_id)
    if hasattr(user, "client_profile"):
        profile = user.client_profile
        return await get_text(user_id, "my_profile_client", location=profile.location or "-"), None

    if hasattr(user, "job_seeker_profile"):
        p = user.job_seeker_profile
        rating = float(getattr(p, "average_rating", 0) or 0)
        verified = "✔️" if getattr(p, "is_verified", False) else "❌"
        pref = await get_user_pref(user_id)
        status = "🟢 Online" if getattr(pref, "is_online", False) else "⚫ Offline"
        price = await format_currency(
            getattr(p, "price_per_unit", Decimal("0")) or Decimal("0"), user_id
        )
        txt = await get_text(
            user_id,
            "my_profile_seeker",
            prof=p.profession.name if p.profession else "-",
            cat=p.category.name if p.category else "-",
            subcat=p.subcategory.name if p.subcategory else "-",
            exp=getattr(p, "experience", 0) or 0,
            loc=getattr(p, "location", "-") or "-",
            price=price,
            unit=getattr(p, "price_unit", "-") or "-",
            rating=rating,
            bio=getattr(p, "bio", "-") or "-",
            verified=verified,
            status=status,
        )
        image_path = None
        field = getattr(p, "profile_image", None)
        if field:
            try:
                candidate = Path(field.path)
                if candidate.exists():
                    image_path = str(candidate)
            except Exception:
                pass
        return txt, image_path

    return await get_text(user_id, "no_profile"), None


# ---------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------
async def main_menu_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(await get_text(user_id, "create_profile"), callback_data="create_profile")],
        [
            InlineKeyboardButton(await get_text(user_id, "my_profile"), callback_data="my_profile"),
            InlineKeyboardButton(await get_text(user_id, "browse_talent"), callback_data="browse_talent"),
        ],
        [
            InlineKeyboardButton(await get_text(user_id, "search"), callback_data="search"),
            InlineKeyboardButton(await get_text(user_id, "post_job"), callback_data="post_job"),
        ],
        [
            InlineKeyboardButton(await get_text(user_id, "my_jobs"), callback_data="my_jobs"),
            InlineKeyboardButton(await get_text(user_id, "favorites"), callback_data="favorites"),
        ],
        [
            InlineKeyboardButton(await get_text(user_id, "nearby"), callback_data="nearby"),
            InlineKeyboardButton(await get_text(user_id, "invite"), callback_data="invite"),
        ],
        [
            InlineKeyboardButton(await get_text(user_id, "settings"), callback_data="settings"),
            InlineKeyboardButton(await get_text(user_id, "help"), callback_data="help"),
        ],
    ])


async def gate_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            (await get_text(user_id, "gate_join", channel=CHANNEL_USERNAME)),
            url=CHANNEL_URL,
        )],
        [InlineKeyboardButton(
            await get_text(user_id, "gate_visit"),
            url=WEBSITE_URL,
        )],
        [InlineKeyboardButton(
            await get_text(user_id, "gate_check"),
            callback_data="check_sub",
        )],
    ])


async def invite_keyboard(user_id: int):
    language_pref = await get_user_pref(user_id)
    lang = language_pref.language if language_pref.language in TEXTS else "en"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            await get_text(user_id, "invite_share"),
            url=get_share_url(user_id=user_id, language=lang),
        )],
        [InlineKeyboardButton(
            f"📢 @{CHANNEL_USERNAME}", url=CHANNEL_URL
        )],
        [InlineKeyboardButton("🌐 Ethiogen.com", url=WEBSITE_URL)],
        [InlineKeyboardButton(await get_text(user_id, "invite_back"), callback_data="back_to_main")],
    ])


async def back_button(user_id: int, callback_data="back_to_main"):
    return InlineKeyboardButton(await get_text(user_id, "back"), callback_data=callback_data)


async def settings_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(await get_text(user_id, "change_lang"), callback_data="change_lang")],
        [InlineKeyboardButton(await get_text(user_id, "change_curr"), callback_data="change_curr")],
        [await back_button(user_id)],
    ])


async def language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
        [InlineKeyboardButton("አማርኛ 🇪🇹", callback_data="lang_am")],
    ])


async def currency_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇪🇹 ETB (Birr)", callback_data="curr_ETB")],
        [InlineKeyboardButton("🇺🇸 USD", callback_data="curr_USD")],
        [await back_button(user_id, "settings")],
    ])


async def unit_keyboard(user_id: int):
    result = []
    for value in ["Hour", "Day", "Week", "Month"]:
        label_key = f"jobseeker_unit_{value.lower()}"
        label = await get_text(user_id, label_key)
        if label == label_key:
            label = value
        result.append([InlineKeyboardButton(label, callback_data=f"unit_{value}")])
    result.append([await back_button(user_id, "back_to_main")])
    return InlineKeyboardMarkup(result)


def rating_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐" * i, callback_data=f"rating_val_{i}") for i in range(1, 6)]
    ])


async def worker_action_keyboard(user_id: int, seeker_id: int):
    kb = []
    user = await get_user_by_id(user_id)
    if hasattr(user, "client_profile"):
        kb.append([
            InlineKeyboardButton("✅ Hire", callback_data=f"hire_{seeker_id}"),
            InlineKeyboardButton("💬 Chat", callback_data=f"chat_{seeker_id}"),
        ])
        kb.append([
            InlineKeyboardButton("📞 Call", callback_data=f"call_{seeker_id}"),
            InlineKeyboardButton("💳 Escrow", callback_data=f"pay_{seeker_id}"),
        ])
        favorite = await is_favorite(user_id, seeker_id)
        kb.append([InlineKeyboardButton(
            await get_text(user_id, "favorite_removed" if favorite else "favorite_added"),
            callback_data=f"fav_remove_{seeker_id}" if favorite else f"fav_add_{seeker_id}",
        )])
        kb.append([InlineKeyboardButton("⭐ Rate Worker", callback_data=f"rate_{seeker_id}")])
    kb.append([InlineKeyboardButton("📤 Share Profile", callback_data=f"share_{seeker_id}")])
    kb.append([await back_button(user_id, "browse_talent")])
    return InlineKeyboardMarkup(kb)


# ---------------------------------------------------------------------
# Core handlers
# ---------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tg_user = update.effective_user
        message = update.effective_message
        if tg_user is None or message is None:
            return

        user = await get_or_create_user(update.effective_chat.id, tg_user.username)
        context.user_data["user_id"] = user.id
        await update_user_activity(user.id)

        # Referral tracking
        referrer = get_referrer_from_start_argument(
            context.args[0] if context.args else None
        )
        if referrer and referrer != tg_user.id:
            context.user_data["referrer_telegram_id"] = referrer
            logger.info("Referral: telegram_user=%s referred_by=%s", tg_user.id, referrer)
            # TODO: persist this to your DB.

        username = tg_user.username or tg_user.first_name or "User"

        # Subscription gate
        if not await is_subscribed(context.bot, tg_user.id):
            await message.reply_text(
                await get_text(user.id, "gate_text", username=username, channel=CHANNEL_USERNAME),
                parse_mode=ParseMode.HTML,
                reply_markup=await gate_keyboard(user.id),
                disable_web_page_preview=True,
            )
            return

        await message.reply_text(
            await get_text(user.id, "welcome", username=username),
            reply_markup=await main_menu_keyboard(user.id),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Start handler failed")
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try /start again."
            )
        except Exception:
            pass


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return ConversationHandler.END
    await query.answer()

    user_id = context.user_data.get("user_id")
    if not user_id:
        u = await get_or_create_user(update.effective_chat.id, user.username)
        user_id = u.id
        context.user_data["user_id"] = user_id

    if await is_subscribed(context.bot, user.id):
        await query.edit_message_text(
            await get_text(user_id, "welcome", username=safe_username(user)),
            reply_markup=await main_menu_keyboard(user_id),
            disable_web_page_preview=True,
        )
    else:
        await query.answer(
            await get_text(user_id, "gate_fail", channel=CHANNEL_USERNAME),
            show_alert=True,
        )
    return ConversationHandler.END


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    user_id = context.user_data.get("user_id")
    if not user_id:
        u = await get_or_create_user(update.effective_chat.id, user.username)
        user_id = u.id
        context.user_data["user_id"] = user_id

    link = get_referral_link(user.id)
    await message.reply_text(
        await get_text(user_id, "invite_text", username=safe_username(user), link=link),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await invite_keyboard(user_id),
        disable_web_page_preview=True,
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = context.user_data.get("user_id")
    if not user_id:
        user = await get_or_create_user(update.effective_chat.id, update.effective_user.username)
        user_id = user.id
        context.user_data["user_id"] = user_id

    if data == "create_profile":
        return await profile_start(update, context)
    if data == "my_profile":
        return await handle_my_profile(query, user_id)
    if data == "browse_talent":
        context.user_data["browse_page"] = 1
        context.user_data["browse_filter_cat"] = None
        context.user_data["browse_filter_sub"] = None
        return await show_talent_page(update, context)
    if data == "show_filters":
        await show_filter_menu(query, user_id)
        return ConversationHandler.END
    if data == "search":
        return await search_start(update, context)
    if data == "post_job":
        return await start_job_post(update, context)
    if data == "my_jobs":
        return await handle_my_jobs(query, user_id)
    if data == "favorites":
        return await handle_favorites(query, user_id)
    if data == "nearby":
        return await start_nearby(update, context)
    if data == "invite":
        link = get_referral_link(update.effective_user.id)
        await query.edit_message_text(
            await get_text(user_id, "invite_text",
                           username=safe_username(update.effective_user), link=link),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=await invite_keyboard(user_id),
            disable_web_page_preview=True,
        )
        return ConversationHandler.END
    if data == "settings":
        return await handle_settings(query, user_id)
    if data == "help":
        await query.edit_message_text(
            await get_text(user_id, "help_text"),
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    if data == "back_to_main":
        await query.edit_message_text(
            await get_text(user_id, "main_menu"),
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END

    if data.startswith("view_seeker_"):
        await handle_view_seeker(query, user_id, int(data.rsplit("_", 1)[1]))
        return ConversationHandler.END

    if data.startswith("filter_cat_"):
        cat_id = int(data.rsplit("_", 1)[1])
        context.user_data["browse_filter_cat"] = cat_id
        context.user_data["browse_filter_sub"] = None
        context.user_data["browse_page"] = 1
        subs = await get_subcategories(cat_id)
        if subs:
            kb = [[InlineKeyboardButton(s.name, callback_data=f"filter_sub_{s.id}")] for s in subs]
            kb.append([InlineKeyboardButton("👥 All in this category", callback_data="filter_category_only")])
            kb.append([await back_button(user_id, "browse_talent")])
            await query.edit_message_text("📁 Select a subcategory:", reply_markup=InlineKeyboardMarkup(kb))
            return ConversationHandler.END
        return await show_talent_page(update, context)
    if data == "filter_category_only":
        return await show_talent_page(update, context)
    if data.startswith("filter_sub_"):
        context.user_data["browse_filter_sub"] = int(data.rsplit("_", 1)[1])
        context.user_data["browse_page"] = 1
        return await show_talent_page(update, context)
    if data == "clear_filters":
        context.user_data["browse_filter_cat"] = None
        context.user_data["browse_filter_sub"] = None
        context.user_data["browse_page"] = 1
        return await show_talent_page(update, context)
    if data == "next_page":
        context.user_data["browse_page"] = context.user_data.get("browse_page", 1) + 1
        return await show_talent_page(update, context)
    if data == "prev_page":
        context.user_data["browse_page"] = max(1, context.user_data.get("browse_page", 1) - 1)
        return await show_talent_page(update, context)
    if data == "change_lang":
        await query.edit_message_text(
            "🌐 Select language / ቋንቋ ይምረጡ:",
            reply_markup=await language_keyboard(),
        )
        return ConversationHandler.END
    if data == "change_curr":
        await query.edit_message_text(
            "💱 Select currency:", reply_markup=await currency_keyboard(user_id)
        )
        return ConversationHandler.END
    if data.startswith("lang_"):
        language = data.split("_", 1)[1]
        await set_user_language(user_id, language)
        await query.edit_message_text(
            await get_text(user_id, "lang_selected"),
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    if data.startswith("curr_"):
        currency = data.split("_", 1)[1]
        await set_user_currency(user_id, currency)
        await query.edit_message_text(
            await get_text(user_id, "currency_selected", currency=currency),
            reply_markup=await settings_keyboard(user_id),
        )
        return ConversationHandler.END
    if data.startswith("fav_add_") or data.startswith("fav_remove_"):
        seeker_id = int(data.rsplit("_", 1)[1])
        added = await toggle_favorite(user_id, seeker_id)
        await query.edit_message_text(
            await get_text(user_id, "favorite_added" if added else "favorite_removed"),
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    if data.startswith("view_apps_"):
        await handle_view_applications(query, user_id, int(data.rsplit("_", 1)[1]))
        return ConversationHandler.END
    if data.startswith("apply_job_"):
        context.user_data["apply_job_id"] = int(data.rsplit("_", 1)[1])
        await query.edit_message_text(await get_text(user_id, "apply_cover"))
        return JOB_APPLY_COVER
    if data.startswith("hire_app_"):
        parts = data.rsplit("_", 2)
        await handle_hire_application(query, user_id, int(parts[1]), int(parts[2]))
        return ConversationHandler.END
    if data.startswith("hire_"):
        await handle_hire_worker(query, user_id, int(data.rsplit("_", 1)[1]))
        return ConversationHandler.END
    if data.startswith("rate_"):
        context.user_data["rating_seeker_id"] = int(data.rsplit("_", 1)[1])
        await query.edit_message_text(
            await get_text(user_id, "rating_select"),
            reply_markup=rating_keyboard(),
        )
        return RATING_VALUE
    if data.startswith(("chat_", "call_", "pay_")):
        await query.edit_message_text(
            "ℹ️ This request/payment feature needs a dedicated messaging/payment backend.",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    if data.startswith("share_"):
        await handle_share_profile(query, user_id, int(data.rsplit("_", 1)[1]))
        return ConversationHandler.END
    if data.startswith("radius_"):
        return await nearby_radius(update, context)

    return ConversationHandler.END


# ---------------------------------------------------------------------
# Profile / browse
# ---------------------------------------------------------------------
async def handle_my_profile(query, user_id: int):
    text, image_path = await user_profile_text(user_id)
    kb = InlineKeyboardMarkup([[await back_button(user_id)]])
    if image_path:
        with open(image_path, "rb") as photo:
            await query.message.reply_photo(photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb)
        await query.delete_message()
    else:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def handle_view_seeker(query, user_id: int, seeker_id: int):
    try:
        seeker = await get_jobseeker_details(seeker_id)
    except JobSeekerProfile.DoesNotExist:
        await query.edit_message_text(await get_text(user_id, "no_talent"))
        return

    rating = float(getattr(seeker, "avg_rating", 0) or getattr(seeker, "average_rating", 0) or 0)
    verified = "✔️" if getattr(seeker, "is_verified", False) else "❌"
    price = await format_currency(
        getattr(seeker, "price_per_unit", Decimal("0")) or Decimal("0"), user_id
    )
    text = await get_text(
        user_id,
        "my_profile_seeker",
        prof=seeker.profession.name if seeker.profession else "-",
        cat=seeker.category.name if seeker.category else "-",
        subcat=seeker.subcategory.name if seeker.subcategory else "-",
        exp=getattr(seeker, "experience", 0) or 0,
        loc=getattr(seeker, "location", "-") or "-",
        price=price,
        unit=getattr(seeker, "price_unit", "-") or "-",
        rating=rating,
        bio=getattr(seeker, "bio", "-") or "-",
        verified=verified,
        status="⚫ Offline",
    )
    kb = await worker_action_keyboard(user_id, seeker_id)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def show_filter_menu(query, user_id: int):
    categories = await get_categories()
    kb = [[InlineKeyboardButton(c.name, callback_data=f"filter_cat_{c.id}")] for c in categories]
    kb.append([InlineKeyboardButton("❌ Clear Filters", callback_data="clear_filters")])
    kb.append([await back_button(user_id, "browse_talent")])
    await query.edit_message_text(
        await get_text(user_id, "jobseeker_category"),
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def show_talent_page(update, context):
    query = update.callback_query
    user_id = context.user_data["user_id"]
    page = max(1, context.user_data.get("browse_page", 1))
    cat_id = context.user_data.get("browse_filter_cat")
    sub_id = context.user_data.get("browse_filter_sub")
    seekers, total = await get_filtered_jobseekers(cat_id, sub_id, page=page)
    total_pages = max(1, math.ceil(total / DEFAULT_PER_PAGE))
    page = min(page, total_pages)
    context.user_data["browse_page"] = page

    if not seekers:
        await query.edit_message_text(
            await get_text(user_id, "no_talent"),
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END

    text = await get_text(user_id, "talent_list", page=page, total_pages=total_pages)
    kb = []
    for seeker in seekers:
        rating = float(getattr(seeker, "avg_rating", 0) or 0)
        text += f"\n👤 *{safe_username(seeker.user)}* — {seeker.profession.name if seeker.profession else 'General'} ⭐ {rating:.1f}"
        kb.append([InlineKeyboardButton(
            f"👁️ {seeker.user.username or 'Worker'}",
            callback_data=f"view_seeker_{seeker.id}",
        )])

    cats = await get_categories()
    if cats:
        kb.append([InlineKeyboardButton(
            await get_text(user_id, "jobseeker_category"),
            callback_data="show_filters",
        )])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data="prev_page"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data="next_page"))
    if nav:
        kb.append(nav)
    kb.append([await back_button(user_id)])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ---------------------------------------------------------------------
# Favorites / nearby
# ---------------------------------------------------------------------
async def handle_favorites(query, user_id: int):
    try:
        favs = await get_favorite_workers(user_id)
    except Exception:
        favs = []
    if not favs:
        await query.edit_message_text(
            await get_text(user_id, "favorites_empty"),
            reply_markup=await main_menu_keyboard(user_id),
        )
        return

    text = await get_text(user_id, "favorites_list")
    kb = []
    for seeker in favs:
        rating = float(getattr(seeker, "average_rating", 0) or 0)
        text += f"\n👤 *{safe_username(seeker.user)}* — {seeker.profession.name if seeker.profession else 'General'} ⭐ {rating:.1f}"
        kb.append([InlineKeyboardButton(
            f"👁️ {seeker.user.username or 'Worker'}",
            callback_data=f"view_seeker_{seeker.id}",
        )])
    kb.append([await back_button(user_id)])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def start_nearby(update, context):
    user_id = context.user_data["user_id"]
    query = update.callback_query
    await query.edit_message_text(
        await get_text(user_id, "nearby_prompt"),
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📍 Share Location", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return NEARBY_LOCATION


async def nearby_location(update, context):
    user_id = context.user_data["user_id"]
    location = update.effective_message.location
    if not location:
        await update.effective_message.reply_text("📍 Please use Share Location.")
        return NEARBY_LOCATION
    context.user_data["nearby_lat"] = location.latitude
    context.user_data["nearby_lon"] = location.longitude
    await update.effective_message.reply_text(
        await get_text(user_id, "nearby_radius"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("5 km", callback_data="radius_5"), InlineKeyboardButton("10 km", callback_data="radius_10")],
            [InlineKeyboardButton("20 km", callback_data="radius_20"), InlineKeyboardButton("50 km", callback_data="radius_50")],
        ]),
    )
    return NEARBY_WORKERS_RADIUS


async def nearby_radius(update, context):
    query = update.callback_query
    await query.answer()
    user_id = context.user_data["user_id"]
    radius = float(query.data.rsplit("_", 1)[1])
    lat = context.user_data.get("nearby_lat")
    lon = context.user_data.get("nearby_lon")
    if lat is None or lon is None:
        await query.edit_message_text("📍 Location not found. Please try again.")
        return ConversationHandler.END

    seekers = await get_nearby_seekers(lat, lon, radius)
    if not seekers:
        await query.edit_message_text(
            await get_text(user_id, "no_nearby"),
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END

    text = await get_text(user_id, "nearby_results", radius=int(radius))
    kb = []
    for seeker in seekers[:10]:
        rating = float(getattr(seeker, "average_rating", 0) or 0)
        text += f"\n👤 *{safe_username(seeker.user)}* — {seeker.profession.name if seeker.profession else 'General'} • {seeker.distance_km:.1f} km ⭐ {rating:.1f}"
        kb.append([InlineKeyboardButton(
            f"👁️ {seeker.user.username or 'Worker'}",
            callback_data=f"view_seeker_{seeker.id}",
        )])
    kb.append([await back_button(user_id)])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ---------------------------------------------------------------------
# Job posting
# ---------------------------------------------------------------------
async def start_job_post(update, context):
    user_id = context.user_data["user_id"]
    user = await get_user_by_id(user_id)
    if not hasattr(user, "client_profile"):
        await update.callback_query.edit_message_text(
            "👔 Create a Client profile before posting a job.",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    await update.callback_query.edit_message_text(await get_text(user_id, "post_job_title"))
    return JOB_POST_TITLE


async def job_post_title(update, context):
    text = (update.effective_message.text or "").strip()
    if len(text) < 3 or len(text) > 150:
        await update.effective_message.reply_text("Title must be 3–150 characters.")
        return JOB_POST_TITLE
    context.user_data["job_title"] = text
    await update.effective_message.reply_text(await get_text(context.user_data["user_id"], "post_job_desc"))
    return JOB_POST_DESC


async def job_post_desc(update, context):
    text = (update.effective_message.text or "").strip()
    if len(text) < 10 or len(text) > 5000:
        await update.effective_message.reply_text("Description must be 10–5000 characters.")
        return JOB_POST_DESC
    context.user_data["job_desc"] = text
    cats = await get_categories()
    if not cats:
        await update.effective_message.reply_text("No job categories are configured.")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(c.name, callback_data=f"jcat_{c.id}")] for c in cats]
    await update.effective_message.reply_text(
        await get_text(context.user_data["user_id"], "post_job_category"),
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return JOB_POST_CATEGORY


async def job_post_category(update, context):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.rsplit("_", 1)[1])
    context.user_data["job_cat_id"] = cat_id
    subs = await get_subcategories(cat_id)
    if not subs:
        context.user_data["job_subcat_id"] = None
        await query.edit_message_text(await get_text(context.user_data["user_id"], "post_job_budget"))
        return JOB_POST_BUDGET
    kb = [[InlineKeyboardButton(s.name, callback_data=f"jsub_{s.id}")] for s in subs]
    kb.append([InlineKeyboardButton("⏭️ Skip", callback_data="jsub_skip")])
    await query.edit_message_text(
        await get_text(context.user_data["user_id"], "post_job_subcategory"),
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return JOB_POST_SUBCAT


async def job_post_subcategory(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data["job_subcat_id"] = None if data == "jsub_skip" else int(data.rsplit("_", 1)[1])
    await query.edit_message_text(await get_text(context.user_data["user_id"], "post_job_budget"))
    return JOB_POST_BUDGET


async def job_post_budget(update, context):
    try:
        budget = Decimal((update.effective_message.text or "").strip())
        if budget <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await update.effective_message.reply_text(await get_text(context.user_data["user_id"], "invalid_price"))
        return JOB_POST_BUDGET
    context.user_data["job_budget"] = budget
    await update.effective_message.reply_text(await get_text(context.user_data["user_id"], "post_job_location"))
    return JOB_POST_LOCATION


async def job_post_location(update, context):
    location = (update.effective_message.text or "").strip()
    if len(location) < 2 or len(location) > 200:
        await update.effective_message.reply_text("Please enter a valid location.")
        return JOB_POST_LOCATION
    context.user_data["job_location"] = location
    await update.effective_message.reply_text(await get_text(context.user_data["user_id"], "post_job_deadline"))
    return JOB_POST_DEADLINE


async def job_post_deadline(update, context):
    user_id = context.user_data["user_id"]
    value = (update.effective_message.text or "").strip()
    try:
        deadline = datetime.strptime(value, "%Y-%m-%d").date()
        if deadline < timezone.localdate():
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(await get_text(user_id, "invalid_date"))
        return JOB_POST_DEADLINE

    job = await create_job_post(
        user_id=user_id,
        title=context.user_data["job_title"],
        description=context.user_data["job_desc"],
        category_id=context.user_data.get("job_cat_id"),
        subcategory_id=context.user_data.get("job_subcat_id"),
        budget=context.user_data["job_budget"],
        location=context.user_data["job_location"],
        deadline=deadline,
    )
    await update.effective_message.reply_text(
        await get_text(user_id, "post_job_success", job_id=job.id),
        reply_markup=await main_menu_keyboard(user_id),
    )
    clear_flow_data(context)
    return ConversationHandler.END


async def handle_my_jobs(query, user_id):
    jobs = await get_job_posts(user_id)
    if not jobs:
        await query.edit_message_text(
            "📭 No jobs posted yet.",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return
    text = await get_text(user_id, "my_jobs_list")
    kb = []
    for job in jobs:
        status = getattr(job, "status", "active")
        text += f"\n• *{job.title}* — {job.budget} ETB — {status}"
        kb.append([InlineKeyboardButton(
            f"📋 {job.title[:45]}",
            callback_data=f"view_apps_{job.id}",
        )])
    kb.append([await back_button(user_id)])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def handle_view_applications(query, user_id, job_id):
    apps = await get_job_applications(job_id)
    if not apps:
        await query.edit_message_text(
            "📭 No applications yet.",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return
    if apps[0].job.client.user_id != user_id:
        await query.edit_message_text("⛔ You are not authorized to view these applications.")
        return

    text = await get_text(user_id, "application_list", title=apps[0].job.title)
    kb = []
    for app in apps:
        seeker = app.job_seeker
        text += f"\n• *{safe_username(seeker.user)}* — {app.bid_amount} ETB — {app.status}"
        if getattr(app, "status", "") == "pending":
            kb.append([InlineKeyboardButton(
                f"✅ Hire {seeker.user.username or 'Worker'}",
                callback_data=f"hire_app_{job_id}_{seeker.id}",
            )])
    kb.append([await back_button(user_id)])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def handle_hire_worker(query, user_id, seeker_id):
    await query.edit_message_text(
        "ℹ️ To hire a worker, post a job and hire from its application list.",
        reply_markup=await main_menu_keyboard(user_id),
    )


async def handle_hire_application(query, user_id, job_id, seeker_id):
    try:
        application = await hire_worker(job_id, seeker_id, user_id)
    except JobApplication.DoesNotExist:
        await query.edit_message_text("⛔ Application not found or you are not authorized.")
        return
    await query.edit_message_text(
        await get_text(user_id, "hire_success", username=safe_username(application.job_seeker.user)),
        reply_markup=await main_menu_keyboard(user_id),
    )


# ---------------------------------------------------------------------
# Job application
# ---------------------------------------------------------------------
async def apply_cover(update, context):
    value = (update.effective_message.text or "").strip()
    context.user_data["apply_cover"] = "" if value == "/skip" else value[:5000]
    await update.effective_message.reply_text(await get_text(context.user_data["user_id"], "apply_bid"))
    return JOB_APPLY_BID


async def apply_bid(update, context):
    user_id = context.user_data["user_id"]
    try:
        bid = Decimal((update.effective_message.text or "").strip())
        if bid <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await update.effective_message.reply_text(await get_text(user_id, "invalid_price"))
        return JOB_APPLY_BID

    app, status = await apply_to_job(
        context.user_data["apply_job_id"],
        user_id,
        context.user_data.get("apply_cover", ""),
        bid,
    )
    if status == "exists":
        message = await get_text(user_id, "already_applied")
    elif status == "closed":
        message = "⛔ This job is no longer accepting applications."
    else:
        message = await get_text(user_id, "apply_success")

    await update.effective_message.reply_text(message, reply_markup=await main_menu_keyboard(user_id))
    clear_flow_data(context)
    return ConversationHandler.END


# ---------------------------------------------------------------------
# Share / rating / search
# ---------------------------------------------------------------------
async def handle_share_profile(query, user_id, seeker_id):
    seeker = await get_jobseeker_details(seeker_id)
    text = (
        f"👤 *{safe_username(seeker.user)}*\n"
        f"🔧 {seeker.profession.name if seeker.profession else 'General'}\n"
        f"⭐ {float(getattr(seeker, 'average_rating', 0) or 0):.1f}/5\n"
        f"📍 {getattr(seeker, 'location', '-') or '-'}"
    )
    share_url = "https://t.me/share/url?url=" + quote(
        f"https://t.me/{BOT_USERNAME}", safe=""
    ) + "&text=" + quote(text.replace("*", ""), safe="")
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Share", url=share_url)],
            [await back_button(user_id, "browse_talent")],
        ]),
    )


async def rating_value_handler(update, context):
    query = update.callback_query
    await query.answer()
    rating = int(query.data.rsplit("_", 1)[1])
    if not 1 <= rating <= 5:
        return ConversationHandler.END
    context.user_data["rating_value"] = rating
    await query.edit_message_text(await get_text(context.user_data["user_id"], "rating_comment"))
    return RATING_COMMENT


async def rating_comment_handler(update, context):
    user_id = context.user_data["user_id"]
    comment = (update.effective_message.text or "").strip()
    if comment == "/skip":
        comment = ""
    try:
        await add_rating(
            context.user_data["rating_seeker_id"],
            user_id,
            context.user_data["rating_value"],
            comment[:2000],
        )
    except ClientProfile.DoesNotExist:
        await update.effective_message.reply_text(
            "👔 Create a Client profile before rating a worker.",
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    await update.effective_message.reply_text(
        await get_text(user_id, "rating_thanks"),
        reply_markup=await main_menu_keyboard(user_id),
    )
    clear_flow_data(context)
    return ConversationHandler.END


async def search_start(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(await get_text(context.user_data["user_id"], "search_prompt"))
    return SEARCH_QUERY


async def search_handler(update, context):
    user_id = context.user_data["user_id"]
    query_text = (update.effective_message.text or "").strip()
    if len(query_text) < 2:
        await update.effective_message.reply_text("Search term is too short.")
        return SEARCH_QUERY
    seekers, _ = await get_filtered_jobseekers(search=query_text)
    if not seekers:
        await update.effective_message.reply_text(
            await get_text(user_id, "no_talent"),
            reply_markup=await main_menu_keyboard(user_id),
        )
        return ConversationHandler.END
    text = await get_text(user_id, "search_results")
    kb = []
    for seeker in seekers:
        rating = float(getattr(seeker, "avg_rating", 0) or 0)
        text += f"\n👤 *{safe_username(seeker.user)}* — {seeker.profession.name if seeker.profession else 'General'} ⭐ {rating:.1f}"
        kb.append([InlineKeyboardButton(
            f"👁️ {seeker.user.username or 'Worker'}",
            callback_data=f"view_seeker_{seeker.id}",
        )])
    kb.append([await back_button(user_id)])
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ---------------------------------------------------------------------
# Profile creation
# ---------------------------------------------------------------------
async def profile_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = context.user_data["user_id"]
    await query.edit_message_text(
        await get_text(user_id, "role_select"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(await get_text(user_id, "client_role"), callback_data="role_client")],
            [InlineKeyboardButton(await get_text(user_id, "jobseeker_role"), callback_data="role_seeker")],
        ]),
    )
    return CREATE_PROFILE


async def select_role(update, context):
    query = update.callback_query
    await query.answer()
    user_id = context.user_data["user_id"]
    role = query.data
    if role == "role_client":
        await query.edit_message_text(await get_text(user_id, "client_location_prompt"))
        return CLIENT_LOCATION
    if role == "role_seeker":
        categories = await get_categories()
        if not categories:
            await query.edit_message_text("No categories are configured.")
            return ConversationHandler.END
        kb = [[InlineKeyboardButton(c.name, callback_data=f"cat_{c.id}")] for c in categories]
        await query.edit_message_text(await get_text(user_id, "jobseeker_category"), reply_markup=InlineKeyboardMarkup(kb))
        return SEEKER_CATEGORY
    return CREATE_PROFILE


async def client_location_handler(update, context):
    user_id = context.user_data["user_id"]
    location = (update.effective_message.text or "").strip()
    if len(location) < 2:
        await update.effective_message.reply_text("Please enter a valid location.")
        return CLIENT_LOCATION
    await create_client_profile(user_id, location)
    await update.effective_message.reply_text(
        await get_text(user_id, "client_success"),
        reply_markup=await main_menu_keyboard(user_id),
    )
    clear_flow_data(context)
    return ConversationHandler.END


async def seeker_category(update, context):
    query = update.callback_query
    await query.answer()
    user_id = context.user_data["user_id"]
    cat_id = int(query.data.rsplit("_", 1)[1])
    context.user_data["seeker_category_id"] = cat_id
    subs = await get_subcategories(cat_id)
    if not subs:
        context.user_data["seeker_subcategory_id"] = None
        return await seeker_profession_start(update, context)
    kb = [[InlineKeyboardButton(s.name, callback_data=f"sub_{s.id}")] for s in subs]
    await query.edit_message_text(await get_text(user_id, "jobseeker_subcategory"), reply_markup=InlineKeyboardMarkup(kb))
    return SEEKER_SUBCAT


async def seeker_subcategory(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["seeker_subcategory_id"] = int(query.data.rsplit("_", 1)[1])
    return await seeker_profession_start(update, context)


async def seeker_profession_start(update, context):
    user_id = context.user_data["user_id"]
    professions = await get_professions()
    kb = [[InlineKeyboardButton(p.name, callback_data=f"prof_{p.id}")] for p in professions[:80]]
    kb.append([InlineKeyboardButton(await get_text(user_id, "profession_other"), callback_data="prof_other")])
    if update.callback_query:
        await update.callback_query.edit_message_text(await get_text(user_id, "jobseeker_profession"), reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.effective_message.reply_text(await get_text(user_id, "jobseeker_profession"), reply_markup=InlineKeyboardMarkup(kb))
    return SEEKER_PROF


async def seeker_profession(update, context):
    user_id = context.user_data["user_id"]
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        data = query.data
        if data == "prof_other":
            await query.edit_message_text(await get_text(user_id, "profession_other"))
            context.user_data["custom_profession"] = True
            return SEEKER_PROF
        profession = await sync_to_async(Profession.objects.get)(id=int(data.rsplit("_", 1)[1]))
    else:
        profession, _ = await get_or_create_profession((update.effective_message.text or "").strip())

    if not profession or not getattr(profession, "name", "").strip():
        await update.effective_message.reply_text(await get_text(user_id, "profession_other"))
        return SEEKER_PROF

    context.user_data["seeker_profession"] = profession
    await (update.callback_query.edit_message_text if update.callback_query else update.effective_message.reply_text)(
        await get_text(user_id, "jobseeker_experience")
    )
    return SEEKER_EXP


async def seeker_experience(update, context):
    user_id = context.user_data["user_id"]
    try:
        experience = int((update.effective_message.text or "").strip())
        if not 0 <= experience <= 60:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(await get_text(user_id, "invalid_number"))
        return SEEKER_EXP
    context.user_data["seeker_exp"] = experience
    await update.effective_message.reply_text(await get_text(user_id, "jobseeker_location"))
    return SEEKER_LOC


async def seeker_location(update, context):
    user_id = context.user_data["user_id"]
    location = (update.effective_message.text or "").strip()
    if len(location) < 2:
        await update.effective_message.reply_text("Please enter a valid location.")
        return SEEKER_LOC
    context.user_data["seeker_loc"] = location
    await update.effective_message.reply_text(await get_text(user_id, "jobseeker_price"))
    return SEEKER_PRICE


async def seeker_price(update, context):
    user_id = context.user_data["user_id"]
    try:
        price = Decimal((update.effective_message.text or "").strip())
        if price < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await update.effective_message.reply_text(await get_text(user_id, "invalid_price"))
        return SEEKER_PRICE
    context.user_data["seeker_price"] = price
    await update.effective_message.reply_text(
        await get_text(user_id, "jobseeker_unit"),
        reply_markup=await unit_keyboard(user_id),
    )
    return SEEKER_UNIT


async def seeker_unit(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["seeker_unit"] = query.data.split("_", 1)[1]
    await query.edit_message_text(await get_text(context.user_data["user_id"], "jobseeker_bio"))
    return SEEKER_BIO


async def seeker_bio(update, context):
    user_id = context.user_data["user_id"]
    value = (update.effective_message.text or "").strip()
    bio = "" if value == "/skip" else value
    if len(bio) > MAX_BIO:
        await update.effective_message.reply_text(f"Bio must be {MAX_BIO} characters or less.")
        return SEEKER_BIO
    context.user_data["seeker_bio"] = bio
    await update.effective_message.reply_text(await get_text(user_id, "jobseeker_image"))
    return SEEKER_IMAGE


async def _download_document(message, directory: Path, filename: str) -> Optional[str]:
    directory.mkdir(parents=True, exist_ok=True)
    telegram_file = None
    if message.photo:
        telegram_file = await message.photo[-1].get_file()
    elif message.voice:
        telegram_file = await message.voice.get_file()
    elif message.video:
        telegram_file = await message.video.get_file()
    if not telegram_file:
        return None
    path = directory / filename
    await telegram_file.download_to_drive(custom_path=str(path))
    return str(path)


async def seeker_image(update, context):
    user_id = context.user_data["user_id"]
    if update.effective_message.photo:
        path = await _download_document(
            update.effective_message, MEDIA_ROOT / "worker_photos", f"user_{user_id}.jpg"
        )
        context.user_data["seeker_image"] = path
        await update.effective_message.reply_text(await get_text(user_id, "jobseeker_voice"))
        return SEEKER_VOICE
    if (update.effective_message.text or "").strip() == "/skip":
        context.user_data["seeker_image"] = None
        await update.effective_message.reply_text(await get_text(user_id, "jobseeker_voice"))
        return SEEKER_VOICE
    await update.effective_message.reply_text(await get_text(user_id, "photo_or_skip"))
    return SEEKER_IMAGE


async def seeker_voice(update, context):
    user_id = context.user_data["user_id"]
    if update.effective_message.voice:
        path = await _download_document(
            update.effective_message, MEDIA_ROOT / "worker_voices", f"user_{user_id}.ogg"
        )
        context.user_data["seeker_voice"] = path
        await update.effective_message.reply_text(await get_text(user_id, "jobseeker_video"))
        return SEEKER_VIDEO
    if (update.effective_message.text or "").strip() == "/skip":
        context.user_data["seeker_voice"] = None
        await update.effective_message.reply_text(await get_text(user_id, "jobseeker_video"))
        return SEEKER_VIDEO
    await update.effective_message.reply_text(await get_text(user_id, "file_or_skip"))
    return SEEKER_VOICE


async def seeker_video(update, context):
    user_id = context.user_data["user_id"]
    if update.effective_message.video:
        path = await _download_document(
            update.effective_message, MEDIA_ROOT / "worker_videos", f"user_{user_id}.mp4"
        )
        context.user_data["seeker_video"] = path
    elif (update.effective_message.text or "").strip() == "/skip":
        context.user_data["seeker_video"] = None
    else:
        await update.effective_message.reply_text(await get_text(user_id, "file_or_skip"))
        return SEEKER_VIDEO

    cat = await sync_to_async(Category.objects.get)(id=context.user_data["seeker_category_id"])
    sub = None
    if context.user_data.get("seeker_subcategory_id"):
        sub = await sync_to_async(SubCategory.objects.get)(id=context.user_data["seeker_subcategory_id"])

    kwargs = {
        "profession": context.user_data["seeker_profession"],
        "category": cat,
        "subcategory": sub,
        "experience": context.user_data["seeker_exp"],
        "location": context.user_data["seeker_loc"],
        "price_per_unit": context.user_data["seeker_price"],
        "price_unit": context.user_data["seeker_unit"],
        "bio": context.user_data.get("seeker_bio", ""),
        "is_active": True,
    }
    model_fields = {f.name for f in JobSeekerProfile._meta.get_fields()}
    for field_name, key in (
        ("profile_image", "seeker_image"),
        ("voice_intro", "seeker_voice"),
        ("video_intro", "seeker_video"),
    ):
        if field_name in model_fields and context.user_data.get(key):
            kwargs[field_name] = context.user_data[key]

    try:
        await create_jobseeker_profile(user_id, **kwargs)
    except TypeError as exc:
        logger.exception("JobSeekerProfile fields do not match bot configuration")
        await update.effective_message.reply_text(
            f"⚠️ Profile could not be created: {exc}"
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        await get_text(user_id, "jobseeker_success"),
        reply_markup=await main_menu_keyboard(user_id),
    )
    clear_flow_data(context)
    return ConversationHandler.END


# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
async def handle_settings(query, user_id):
    pref = await get_user_pref(user_id)
    lang = "English" if pref.language == "en" else "አማርኛ"
    text = await get_text(user_id, "settings_menu", lang=lang, curr=pref.currency or "ETB")
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=await settings_keyboard(user_id))


# ---------------------------------------------------------------------
# Admin / misc
# ---------------------------------------------------------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def run_manage_command(update, command: list[str], timeout: int, label: str):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Not authorized.")
        return
    await update.effective_message.reply_text(f"🔄 {label}...")
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "manage.py", *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode == 0:
            await update.effective_message.reply_text(f"✅ Done.\n\n{(out or 'No output')[:3800]}")
        else:
            await update.effective_message.reply_text(f"❌ Failed.\n\n{(err or out or 'Unknown')[:3800]}")
    except asyncio.TimeoutError:
        if process:
            process.kill()
            await process.communicate()
        await update.effective_message.reply_text(f"⏱️ {label} timed out.")
    except Exception as exc:
        logger.exception("%s failed", label)
        await update.effective_message.reply_text(f"⚠️ {type(exc).__name__}: {exc}")


async def scrape_command(update, context):
    await run_manage_command(
        update,
        ["post_website_update", "--url", SCRAPER_URL, "--groups", SCRAPER_GROUP_ID,
         "--selector", SCRAPER_SELECTOR, "--force"],
        120, "Scraping website updates",
    )


async def tenders_command(update, context):
    await run_manage_command(
        update, ["scrape_tenders", "--groups", SCRAPER_GROUP_ID],
        120, "Scraping tenders",
    )


async def test_command(update, context):
    await update.effective_message.reply_text("✅ Ethiogen bot is running.")


async def cancel(update, context):
    user_id = context.user_data.get("user_id")
    if user_id:
        clear_flow_data(context)
        await update.effective_message.reply_text(
            await get_text(user_id, "cancel"),
            reply_markup=await main_menu_keyboard(user_id),
        )
    else:
        await update.effective_message.reply_text("🚫 Cancelled.")
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update caused an exception: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again.")
        except Exception:
            pass


async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "Start the bot"),
        ("invite", "Get your referral link"),
        ("test", "Check the bot is running"),
        ("scrape", "Admin: scrape website updates"),
        ("tenders", "Admin: scrape tenders"),
    ])
    me = await application.bot.get_me()
    logger.info("Bot started as @%s", me.username)


# ---------------------------------------------------------------------
# Build application
# ---------------------------------------------------------------------
def build_application() -> Application:
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    profile_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(profile_start, pattern=r"^create_profile$")],
        states={
            CREATE_PROFILE: [CallbackQueryHandler(select_role, pattern=r"^role_(client|seeker)$")],
            CLIENT_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_location_handler)],
            SEEKER_CATEGORY: [CallbackQueryHandler(seeker_category, pattern=r"^cat_\d+$")],
            SEEKER_SUBCAT: [CallbackQueryHandler(seeker_subcategory, pattern=r"^sub_\d+$")],
            SEEKER_PROF: [
                CallbackQueryHandler(seeker_profession, pattern=r"^prof_\d+$|^prof_other$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_profession),
            ],
            SEEKER_EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_experience)],
            SEEKER_LOC: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_location)],
            SEEKER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_price)],
            SEEKER_UNIT: [CallbackQueryHandler(seeker_unit, pattern=r"^unit_")],
            SEEKER_BIO: [
                CommandHandler("skip", seeker_bio),
                MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_bio),
            ],
            SEEKER_IMAGE: [
                MessageHandler(filters.PHOTO, seeker_image),
                CommandHandler("skip", seeker_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_image),
            ],
            SEEKER_VOICE: [
                MessageHandler(filters.VOICE, seeker_voice),
                CommandHandler("skip", seeker_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_voice),
            ],
            SEEKER_VIDEO: [
                MessageHandler(filters.VIDEO, seeker_video),
                CommandHandler("skip", seeker_video),
                MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_video),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_start, pattern=r"^search$")],
        states={SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    rating_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern=r"^rate_\d+$")],
        states={
            RATING_VALUE: [CallbackQueryHandler(rating_value_handler, pattern=r"^rating_val_[1-5]$")],
            RATING_COMMENT: [
                CommandHandler("skip", rating_comment_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rating_comment_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    job_post_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_job_post, pattern=r"^post_job$")],
        states={
            JOB_POST_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_post_title)],
            JOB_POST_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_post_desc)],
            JOB_POST_CATEGORY: [CallbackQueryHandler(job_post_category, pattern=r"^jcat_\d+$")],
            JOB_POST_SUBCAT: [CallbackQueryHandler(job_post_subcategory, pattern=r"^jsub_\d+$|^jsub_skip$")],
            JOB_POST_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_post_budget)],
            JOB_POST_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_post_location)],
            JOB_POST_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_post_deadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    job_apply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern=r"^apply_job_\d+$")],
        states={
            JOB_APPLY_COVER: [
                CommandHandler("skip", apply_cover),
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_cover),
            ],
            JOB_APPLY_BID: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_bid)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    nearby_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_nearby, pattern=r"^nearby$")],
        states={
            NEARBY_LOCATION: [MessageHandler(filters.LOCATION, nearby_location)],
            NEARBY_WORKERS_RADIUS: [CallbackQueryHandler(nearby_radius, pattern=r"^radius_(5|10|20|50)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Commands first
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("scrape", scrape_command))
    application.add_handler(CommandHandler("tenders", tenders_command))

    # Subscription check callback (must be BEFORE the catch-all menu_handler)
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_sub$"))

    # Conversations
    application.add_handler(profile_conv)
    application.add_handler(search_conv)
    application.add_handler(rating_conv)
    application.add_handler(job_post_conv)
    application.add_handler(job_apply_conv)
    application.add_handler(nearby_conv)

    # Channel distribution + subscription billing (inline Apply / Subscribe
    # buttons on published posts, payment, receipt upload).
    # Must be registered BEFORE the catch-all menu_handler below.
    try:
        from telegram_bridge import register_bridge

        register_bridge(application)
    except Exception as exc:
        logger.exception("Could not register the billing bridge: %s", exc)

    # Catch-all menu
    application.add_handler(CallbackQueryHandler(menu_handler))

    application.add_error_handler(error_handler)
    return application


def main():
    logger.info("Starting Ethiogen Telegram bot (unified)...")
    application = build_application()
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()