"""
🤖 Ethiogen Advanced Job Portal Bot
Features: Language switch (EN/AM), Currency, Category/SubCategory filter,
Search, Worker image display, Rating system.
"""

import os
import sys
import django
import logging
from decimal import Decimal
from asgiref.sync import sync_to_async
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)

# =========================
# 🔧 DJANGO INIT
# =========================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
django.setup()

# =========================
# 📦 IMPORTS
# =========================
from django.contrib.auth import get_user_model

User = get_user_model()
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Avg
from jobs.models import (
    ClientProfile, JobSeekerProfile, Profession, Category, SubCategory,
    WorkerRating, UserPreference, TelegramProfile
)

# =========================
# 🔐 CONFIG
# =========================
TOKEN = "8794385823:AAEWFdATh1j1S7DfG-GZi5DNtOE5WcLV2WU"  # Replace with your actual token
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Exchange rate (1 USD = 55 ETB)
EXCHANGE_RATE = Decimal('55.0')

# Conversation states
(
    MAIN_MENU, LANG_SETTINGS, CURRENCY_SETTINGS,
    CREATE_PROFILE, CLIENT_LOCATION,
    SEEKER_CATEGORY, SEEKER_SUBCAT, SEEKER_PROF, SEEKER_EXP,
    SEEKER_LOC, SEEKER_PRICE, SEEKER_UNIT, SEEKER_BIO, SEEKER_IMAGE,
    FILTER_CATEGORY, FILTER_SUBCAT, SEARCH_QUERY,
    RATING_VALUE, RATING_COMMENT
) = range(19)

# =========================
# 🌍 TRANSLATIONS (English + Amharic) – all placeholders are named
# =========================
TEXTS = {
    'en': {
        'welcome': "Welcome to Ethiogen 🚀, {username}!",
        'main_menu': "Main Menu",
        'create_profile': "🧑‍💼 Create Profile",
        'my_profile': "👤 My Profile",
        'browse_talent': "📄 Browse Talent",
        'settings': "⚙️ Settings",
        'help': "❓ Help",
        'search': "🔍 Search",
        'role_select': "What type of profile do you want?",
        'client_role': "👔 Client (Hire)",
        'jobseeker_role': "🛠️ Job Seeker (Offer)",
        'back': "🔙 Back",
        'client_location_prompt': "Send your location (city/area):",
        'client_success': "✅ Client profile created!",
        'jobseeker_category': "Select your work category:",
        'jobseeker_subcategory': "Select subcategory:",
        'jobseeker_profession': "Select your profession:",
        'jobseeker_experience': "Now send years of experience (number):",
        'jobseeker_location': "Send your location:",
        'jobseeker_price': "What is your price per unit? (e.g., 25.50):",
        'jobseeker_unit': "Select unit:",
        'jobseeker_bio': "Send a short bio (or /skip):",
        'jobseeker_image': "Send a profile photo (or /skip):",
        'jobseeker_success': "✅ Job Seeker profile created!",
        'cancel': "🚫 Cancelled.",
        'my_profile_client': "👤 *Client Profile*\n📍 Location: {location}",
        'my_profile_seeker': (
            "🛠️ *Job Seeker Profile*\n"
            "Profession: {prof}\n"
            "Category: {cat}\n"
            "Experience: {exp} yrs\n"
            "Location: {loc}\n"
            "Rate: {price} {unit}\n"
            "⭐ Rating: {rating}/5\n"
            "Bio: {bio}"
        ),
        'no_profile': "You don't have a profile yet. Use 'Create Profile'.",
        'no_talent': "📭 No active job seekers found.",
        'talent_list': "📄 *Available Talent* (Page {page}/{total_pages}):\n",
        'view_talent': "View details",
        'next_page': "➡️ Next",
        'prev_page': "⬅️ Previous",
        'rating_label': "⭐ Rating: {rating}/5",
        'rate_worker': "⭐ Rate this worker",
        'select_rating': "Select rating (1-5):",
        'rating_comment': "Add a comment (or /skip):",
        'rating_thanks': "Thanks for rating!",
        'search_prompt': "🔎 Enter search keyword (name, profession, location, bio):",
        'search_results': "Search results:\n",
        'filter_category': "Select category:",
        'filter_subcategory': "Select subcategory:",
        'lang_selected': "Language set to English 🇬🇧",
        'currency_selected': "Currency set to {currency}",
        'settings_menu': "⚙️ *Settings*\nLanguage: {lang}\nCurrency: {curr}",
        'change_lang': "🌐 Change Language",
        'change_curr': "💱 Change Currency",
        'help_text': "❓ *Help*\n- Create profile (Client/Job Seeker)\n- Browse & rate talent\n- Search workers\n- Change language/currency\nSupport: @support"
    },
    'am': {
        'welcome': "እንኳን ወደ ኢትዮጅን በደህና መጡ 🚀, {username}!",
        'main_menu': "ዋና ምናሌ",
        'create_profile': "🧑‍💼 መገለጫ ፍጠር",
        'my_profile': "👤 መገለጫዬ",
        'browse_talent': "📄 ተሰጥኦ አስስ",
        'settings': "⚙️ ቅንብሮች",
        'help': "❓ እገዛ",
        'search': "🔍 ፈልግ",
        'role_select': "ምን አይነት መገለጫ መፍጠር ትፈልጋለህ?",
        'client_role': "👔 ደንበኛ (ቀጥር)",
        'jobseeker_role': "🛠️ አገልግሎት ሰጪ",
        'back': "🔙 ተመለስ",
        'client_location_prompt': "አካባቢህን ላክ (ከተማ/አካባቢ):",
        'client_success': "✅ የደንበኛ መገለጫ ተፈጥሯል!",
        'jobseeker_category': "የስራ ምድብ ምረጥ:",
        'jobseeker_subcategory': "ንዑስ ምድብ ምረጥ:",
        'jobseeker_profession': "ሙያህን ምረጥ:",
        'jobseeker_experience': "የስራ ልምድህን (አመት) ላክ:",
        'jobseeker_location': "አካባቢህን ላክ:",
        'jobseeker_price': "ዋጋህን ለአንድ ክፍል ላክ (ለምሳሌ 25.50):",
        'jobseeker_unit': "ክፍሉን ምረጥ:",
        'jobseeker_bio': "አጭር መግለጫ ላክ (ወይም /skip):",
        'jobseeker_image': "የመገለጫ ፎቶ ላክ (ወይም /skip):",
        'jobseeker_success': "✅ የአገልግሎት ሰጪ መገለጫ ተፈጥሯል!",
        'cancel': "🚫 ተሰርዟል.",
        'my_profile_client': "👤 *የደንበኛ መገለጫ*\n📍 አካባቢ: {location}",
        'my_profile_seeker': (
            "🛠️ *የአገልግሎት ሰጪ መገለጫ*\n"
            "ሙያ: {prof}\n"
            "ምድብ: {cat}\n"
            "ልምድ: {exp} ዓመታት\n"
            "አካባቢ: {loc}\n"
            "ተመን: {price} {unit}\n"
            "⭐ ደረጃ: {rating}/5\n"
            "ማስታወሻ: {bio}"
        ),
        'no_profile': "እስካሁን መገለጫ አልፈጠሩም። 'መገለጫ ፍጠር' ይጠቀሙ።",
        'no_talent': "📭 ምንም ንቁ አገልግሎት ሰጪ አልተገኘም።",
        'talent_list': "📄 *የሚገኙ ተሰጥኦዎች* (ገጽ {page}/{total_pages}):\n",
        'view_talent': "ዝርዝር ይመልከቱ",
        'next_page': "➡️ ቀጣይ",
        'prev_page': "⬅️ ቀዳሚ",
        'rating_label': "⭐ ደረጃ: {rating}/5",
        'rate_worker': "⭐ ደረጃ ስጥ",
        'select_rating': "ደረጃ ምረጥ (1-5):",
        'rating_comment': "አስተያየት ጨምር (ወይም /skip):",
        'rating_thanks': "እናመሰግናለን ደረጃ ሰጥተሃል!",
        'search_prompt': "🔎 የፍለጋ ቃል አስገባ (ስም፣ ሙያ፣ አካባቢ፣ ማስታወሻ):",
        'search_results': "የፍለጋ ውጤቶች:\n",
        'filter_category': "ምድብ ምረጥ:",
        'filter_subcategory': "ንዑስ ምድብ ምረጥ:",
        'lang_selected': "ቋንቋ ወደ አማርኛ ተቀይሯል 🇪🇹",
        'currency_selected': "ገንዘብ ወደ {currency} ተቀይሯል",
        'settings_menu': "⚙️ *ቅንብሮች*\nቋንቋ: {lang}\nገንዘብ: {curr}",
        'change_lang': "🌐 ቋንቋ ቀይር",
        'change_curr': "💱 ገንዘብ ቀይር",
        'help_text': "❓ *እገዛ*\n- መገለጫ ፍጠር\n- ተሰጥኦ አስስ እና ደረጃ ስጥ\n- ሰራተኞችን ፈልግ\n- ቋንቋ/ገንዘብ ቀይር\nድጋፍ: @support"
    }
}

def get_text(user_id, key, **kwargs):
    """Fetch translated text and format with named placeholders."""
    lang = 'en'
    try:
        pref = UserPreference.objects.get(user_id=user_id)
        lang = pref.language
    except:
        pass
    text = TEXTS.get(lang, TEXTS['en']).get(key, TEXTS['en'][key])
    return text.format(**kwargs) if kwargs else text

# =========================
# 🛠️ ASYNC HELPERS
# =========================
@sync_to_async
def get_or_create_user_pref(user):
    pref, _ = UserPreference.objects.get_or_create(user=user)
    return pref

@sync_to_async
def get_user_pref(user_id):
    try:
        return UserPreference.objects.get(user_id=user_id)
    except:
        return None

@sync_to_async
def set_user_language(user_id, lang):
    pref, _ = UserPreference.objects.get_or_create(user_id=user_id)
    pref.language = lang
    pref.save()

@sync_to_async
def set_user_currency(user_id, currency):
    pref, _ = UserPreference.objects.get_or_create(user_id=user_id)
    pref.currency = currency
    pref.save()

@sync_to_async
def get_or_create_user(chat_id, username=None):
    try:
        tg = TelegramProfile.objects.get(chat_id=chat_id)
        return tg.user
    except ObjectDoesNotExist:
        base = username or f"tg_{chat_id}"
        uname = base
        cnt = 1
        while User.objects.filter(username=uname).exists():
            uname = f"{base}_{cnt}"
            cnt += 1
        user = User.objects.create_user(username=uname, password=None)
        TelegramProfile.objects.create(user=user, chat_id=chat_id)
        return user

@sync_to_async
def get_user_by_id(user_id):
    return User.objects.get(id=user_id)

@sync_to_async
def create_client_profile(user, location):
    ClientProfile.objects.update_or_create(user=user, defaults={'location': location})

@sync_to_async
def create_jobseeker_profile(user, **kwargs):
    return JobSeekerProfile.objects.create(user=user, **kwargs)

@sync_to_async
def get_categories():
    return list(Category.objects.all())

@sync_to_async
def get_subcategories(category_id):
    return list(SubCategory.objects.filter(category_id=category_id))

@sync_to_async
def get_professions():
    return list(Profession.objects.all())

@sync_to_async
def get_or_create_profession(name):
    return Profession.objects.get_or_create(name=name)

@sync_to_async
def get_filtered_jobseekers(category_id=None, subcategory_id=None, search=None, page=1, per_page=5):
    qs = JobSeekerProfile.objects.filter(is_active=True).select_related(
        'user', 'profession', 'category', 'subcategory'
    )
    if category_id:
        qs = qs.filter(category_id=category_id)
    if subcategory_id:
        qs = qs.filter(subcategory_id=subcategory_id)
    if search:
        qs = qs.filter(
            Q(user__username__icontains=search) |
            Q(profession__name__icontains=search) |
            Q(location__icontains=search) |
            Q(bio__icontains=search)
        )
    qs = qs.annotate(avg_rating=Avg('ratings__rating'))
    total = qs.count()
    start = (page-1) * per_page
    items = list(qs[start:start+per_page])
    return items, total

@sync_to_async
def get_jobseeker_details(seeker_id):
    return JobSeekerProfile.objects.select_related(
        'user', 'profession', 'category', 'subcategory'
    ).annotate(avg_rating=Avg('ratings__rating')).get(id=seeker_id)

@sync_to_async
def add_rating(seeker_id, client_user_id, rating, comment):
    seeker = JobSeekerProfile.objects.get(id=seeker_id)
    client = ClientProfile.objects.get(user_id=client_user_id)
    _, created = WorkerRating.objects.update_or_create(
        job_seeker=seeker, client=client,
        defaults={'rating': rating, 'comment': comment}
    )
    avg = WorkerRating.objects.filter(job_seeker=seeker).aggregate(Avg('rating'))['rating__avg']
    seeker.average_rating = avg or 0
    seeker.save(update_fields=['average_rating'])
    return created

# =========================
# 🎛️ KEYBOARDS
# =========================
async def main_menu_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'create_profile'), callback_data='create_profile')],
        [InlineKeyboardButton(get_text(user_id, 'my_profile'), callback_data='my_profile')],
        [InlineKeyboardButton(get_text(user_id, 'browse_talent'), callback_data='browse_talent')],
        [InlineKeyboardButton(get_text(user_id, 'search'), callback_data='search')],
        [InlineKeyboardButton(get_text(user_id, 'settings'), callback_data='settings')],
        [InlineKeyboardButton(get_text(user_id, 'help'), callback_data='help')],
    ])

async def settings_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'change_lang'), callback_data='change_lang')],
        [InlineKeyboardButton(get_text(user_id, 'change_curr'), callback_data='change_curr')],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data='back_to_main')],
    ])

async def currency_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇪🇹 ETB (Birr)", callback_data='curr_ETB')],
        [InlineKeyboardButton("🇺🇸 USD", callback_data='curr_USD')],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data='settings')],
    ])

async def language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English 🇬🇧", callback_data='lang_en')],
        [InlineKeyboardButton("አማርኛ 🇪🇹", callback_data='lang_am')],
    ])

# =========================
# 🚀 HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await get_or_create_user(chat_id, update.effective_user.username)
    context.user_data['user_id'] = user.id
    await update.message.reply_text(
        get_text(user.id, 'welcome', username=user.username),
        reply_markup=await main_menu_keyboard(user.id)
    )

async def client_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.text.strip()
    user_id = context.user_data['user_id']
    user = await get_user_by_id(user_id)
    await create_client_profile(user, location)
    await update.message.reply_text(
        get_text(user_id, 'client_success'),
        reply_markup=await main_menu_keyboard(user_id)
    )
    return ConversationHandler.END

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = context.user_data.get('user_id')
    if not user_id:
        user = await get_or_create_user(update.effective_chat.id)
        user_id = user.id
        context.user_data['user_id'] = user_id

    if data == 'my_profile':
        user = await get_user_by_id(user_id)
        if hasattr(user, 'client_profile'):
            loc = user.client_profile.location or 'Not set'
            txt = get_text(user_id, 'my_profile_client', location=loc)
        elif hasattr(user, 'job_seeker_profile'):
            p = user.job_seeker_profile
            txt = get_text(user_id, 'my_profile_seeker',
                           prof=p.profession.name if p.profession else '-',
                           cat=p.category.name if p.category else '-',
                           exp=p.experience,
                           loc=p.location,
                           price=p.price_per_unit,
                           unit=p.price_unit,
                           rating=float(p.average_rating or 0),
                           bio=p.bio or '-')
            if p.profile_image and os.path.exists(p.profile_image.path):
                await query.message.reply_photo(photo=open(p.profile_image.path, 'rb'))
        else:
            txt = get_text(user_id, 'no_profile')
            await query.edit_message_text(txt, reply_markup=await main_menu_keyboard(user_id))
            return
        await query.edit_message_text(txt, parse_mode='Markdown')

    elif data == 'browse_talent':
        context.user_data['browse_page'] = 1
        context.user_data['browse_filter_cat'] = None
        context.user_data['browse_filter_sub'] = None
        await show_talent_page(update, context)

    elif data == 'search':
        await query.edit_message_text(get_text(user_id, 'search_prompt'))
        return SEARCH_QUERY

    elif data == 'settings':
        pref = await get_user_pref(user_id)
        lang = 'English' if pref and pref.language == 'en' else 'አማርኛ' if pref else 'English'
        curr = pref.currency if pref else 'ETB'
        txt = get_text(user_id, 'settings_menu', lang=lang, curr=curr)
        await query.edit_message_text(txt, parse_mode='Markdown', reply_markup=await settings_keyboard(user_id))

    elif data == 'help':
        txt = get_text(user_id, 'help_text')
        await query.edit_message_text(txt, parse_mode='Markdown', reply_markup=await main_menu_keyboard(user_id))

    elif data == 'back_to_main':
        await query.edit_message_text(get_text(user_id, 'main_menu'), reply_markup=await main_menu_keyboard(user_id))

    elif data.startswith('view_seeker_'):
        seeker_id = int(data.split('_')[2])
        seeker = await get_jobseeker_details(seeker_id)
        rating = float(seeker.avg_rating or 0)
        txt = get_text(user_id, 'my_profile_seeker',
                       prof=seeker.profession.name if seeker.profession else '-',
                       cat=seeker.category.name if seeker.category else '-',
                       exp=seeker.experience,
                       loc=seeker.location,
                       price=seeker.price_per_unit,
                       unit=seeker.price_unit,
                       rating=rating,
                       bio=seeker.bio or '-')
        kb = [[InlineKeyboardButton(get_text(user_id, 'rate_worker'), callback_data=f"rate_{seeker_id}")],
              [InlineKeyboardButton(get_text(user_id, 'back'), callback_data='browse_talent')]]
        if seeker.profile_image and os.path.exists(seeker.profile_image.path):
            await query.message.reply_photo(photo=open(seeker.profile_image.path, 'rb'),
                                            caption=txt, parse_mode='Markdown',
                                            reply_markup=InlineKeyboardMarkup(kb))
            await query.delete_message()
        else:
            await query.edit_message_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('rate_'):
        seeker_id = int(data.split('_')[1])
        context.user_data['rating_seeker_id'] = seeker_id
        await query.edit_message_text(get_text(user_id, 'select_rating'), reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(str(i), callback_data=f"rating_val_{i}")] for i in range(1,6)]
        ))
        return RATING_VALUE

    elif data.startswith('rating_val_'):
        rating = int(data.split('_')[2])
        context.user_data['rating_value'] = rating
        await query.edit_message_text(get_text(user_id, 'rating_comment'))
        return RATING_COMMENT

    elif data == 'change_lang':
        await query.edit_message_text("Select language:", reply_markup=await language_keyboard())
        return LANG_SETTINGS

    elif data == 'change_curr':
        await query.edit_message_text("Select currency:", reply_markup=await currency_keyboard(user_id))
        return CURRENCY_SETTINGS

    elif data.startswith('lang_'):
        lang = 'en' if data == 'lang_en' else 'am'
        await set_user_language(user_id, lang)
        await query.edit_message_text(get_text(user_id, 'lang_selected'), reply_markup=await main_menu_keyboard(user_id))

    elif data.startswith('curr_'):
        curr = data.split('_')[1]
        await set_user_currency(user_id, curr)
        await query.edit_message_text(get_text(user_id, 'currency_selected', currency=curr), reply_markup=await settings_keyboard(user_id))

    elif data.startswith('filter_cat_'):
        cat_id = int(data.split('_')[2])
        context.user_data['browse_filter_cat'] = cat_id
        context.user_data['browse_page'] = 1
        await show_talent_page(update, context)

    elif data.startswith('filter_sub_'):
        sub_id = int(data.split('_')[2])
        context.user_data['browse_filter_sub'] = sub_id
        context.user_data['browse_page'] = 1
        await show_talent_page(update, context)

    elif data == 'clear_filters':
        context.user_data['browse_filter_cat'] = None
        context.user_data['browse_filter_sub'] = None
        context.user_data['browse_page'] = 1
        await show_talent_page(update, context)

    elif data == 'next_page':
        context.user_data['browse_page'] = context.user_data.get('browse_page', 1) + 1
        await show_talent_page(update, context)

    elif data == 'prev_page':
        context.user_data['browse_page'] = max(1, context.user_data.get('browse_page', 1) - 1)
        await show_talent_page(update, context)

async def show_talent_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = context.user_data['user_id']
    page = context.user_data.get('browse_page', 1)
    cat_id = context.user_data.get('browse_filter_cat')
    sub_id = context.user_data.get('browse_filter_sub')
    seekers, total = await get_filtered_jobseekers(cat_id, sub_id, page=page)
    total_pages = (total + 4) // 5
    text = get_text(user_id, 'talent_list', page=page, total_pages=total_pages)
    kb = []
    for s in seekers:
        rating = float(s.avg_rating or 0)
        text += f"\n👤 {s.user.username} - {s.profession.name if s.profession else 'Any'} ⭐ {rating:.1f}"
        kb.append([InlineKeyboardButton(f"📌 {s.user.username}", callback_data=f"view_seeker_{s.id}")])
    # Filter row
    filter_row = []
    if cat_id is None:
        cats = await get_categories()
        for cat in cats[:3]:
            filter_row.append(InlineKeyboardButton(cat.name, callback_data=f"filter_cat_{cat.id}"))
        if cats:
            filter_row.append(InlineKeyboardButton("Clear", callback_data='clear_filters'))
    else:
        filter_row.append(InlineKeyboardButton("Clear filters", callback_data='clear_filters'))
        subs = await get_subcategories(cat_id)
        for sub in subs[:3]:
            filter_row.append(InlineKeyboardButton(sub.name, callback_data=f"filter_sub_{sub.id}"))
    if filter_row:
        kb.append(filter_row)
    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(get_text(user_id, 'prev_page'), callback_data='prev_page'))
    if page < total_pages:
        nav.append(InlineKeyboardButton(get_text(user_id, 'next_page'), callback_data='next_page'))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data='back_to_main')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = context.user_data['user_id']
    query_text = update.message.text
    seekers, total = await get_filtered_jobseekers(search=query_text)
    if not seekers:
        await update.message.reply_text(get_text(user_id, 'no_talent'), reply_markup=await main_menu_keyboard(user_id))
        return ConversationHandler.END
    text = get_text(user_id, 'search_results')
    for s in seekers:
        rating = float(s.avg_rating or 0)
        text += f"\n👤 {s.user.username} - {s.profession.name if s.profession else 'Any'} ⭐ {rating:.1f}"
    kb = [[InlineKeyboardButton(f"🔍 {s.user.username}", callback_data=f"view_seeker_{s.id}")] for s in seekers[:5]]
    kb.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data='back_to_main')])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# ----------------------------
# Profile Creation (extended with category, subcategory, image)
# ----------------------------
async def profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['user_id']
    await query.edit_message_text(get_text(user_id, 'role_select'), reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'client_role'), callback_data='role_client')],
        [InlineKeyboardButton(get_text(user_id, 'jobseeker_role'), callback_data='role_jobseeker')],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data='back_to_main')]
    ]))
    return CREATE_PROFILE

async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = 'client' if query.data == 'role_client' else 'jobseeker'
    context.user_data['profile_role'] = role
    user_id = context.user_data['user_id']
    if role == 'client':
        await query.edit_message_text(get_text(user_id, 'client_location_prompt'))
        return CLIENT_LOCATION
    else:
        cats = await get_categories()
        if not cats:
            await query.edit_message_text("No categories defined. Please contact admin.")
            return ConversationHandler.END
        kb = [[InlineKeyboardButton(c.name, callback_data=f"cat_{c.id}")] for c in cats]
        await query.edit_message_text(get_text(user_id, 'jobseeker_category'), reply_markup=InlineKeyboardMarkup(kb))
        return SEEKER_CATEGORY

async def seeker_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split('_')[1])
    context.user_data['seeker_category_id'] = cat_id
    subs = await get_subcategories(cat_id)
    user_id = context.user_data['user_id']
    if not subs:
        context.user_data['seeker_subcategory_id'] = None
        return await seeker_profession_start(update, context)
    kb = [[InlineKeyboardButton(s.name, callback_data=f"sub_{s.id}")] for s in subs]
    await query.edit_message_text(get_text(user_id, 'jobseeker_subcategory'), reply_markup=InlineKeyboardMarkup(kb))
    return SEEKER_SUBCAT

async def seeker_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub_id = int(query.data.split('_')[1])
    context.user_data['seeker_subcategory_id'] = sub_id
    return await seeker_profession_start(update, context)

async def seeker_profession_start(update, context):
    user_id = context.user_data['user_id']
    profs = await get_professions()
    kb = [[InlineKeyboardButton(p.name, callback_data=f"prof_{p.id}")] for p in profs[:10]]
    kb.append([InlineKeyboardButton("Other (type)", callback_data="prof_other")])
    await update.callback_query.edit_message_text(get_text(user_id, 'jobseeker_profession'), reply_markup=InlineKeyboardMarkup(kb))
    return SEEKER_PROF

async def seeker_profession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        data = query.data
        if data == 'prof_other':
            await query.edit_message_text("Type your profession name:")
            return SEEKER_PROF
        elif data.startswith('prof_'):
            prof_id = int(data.split('_')[1])
            prof = await sync_to_async(Profession.objects.get)(id=prof_id)
            context.user_data['seeker_profession'] = prof
            await query.edit_message_text(f"Profession: {prof.name}\n" + get_text(context.user_data['user_id'], 'jobseeker_experience'))
            return SEEKER_EXP
    else:
        text = update.message.text.strip()
        prof, _ = await get_or_create_profession(text)
        context.user_data['seeker_profession'] = prof
        await update.message.reply_text(get_text(context.user_data['user_id'], 'jobseeker_experience'))
        return SEEKER_EXP

async def seeker_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        exp = int(update.message.text)
        context.user_data['seeker_exp'] = exp
        await update.message.reply_text(get_text(context.user_data['user_id'], 'jobseeker_location'))
        return SEEKER_LOC
    except ValueError:
        await update.message.reply_text("Please send a valid number.")
        return SEEKER_EXP

async def seeker_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['seeker_loc'] = update.message.text.strip()
    await update.message.reply_text(get_text(context.user_data['user_id'], 'jobseeker_price'))
    return SEEKER_PRICE

async def seeker_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = Decimal(update.message.text)
        context.user_data['seeker_price'] = price
        kb = [[InlineKeyboardButton(u, callback_data=f"unit_{u}")] for u in ['Hour', 'Day', 'Week', 'Month']]
        await update.message.reply_text(get_text(context.user_data['user_id'], 'jobseeker_unit'), reply_markup=InlineKeyboardMarkup(kb))
        return SEEKER_UNIT
    except:
        await update.message.reply_text("Invalid number. Try again.")
        return SEEKER_PRICE

async def seeker_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    unit = query.data.split('_')[1]
    context.user_data['seeker_unit'] = unit
    await query.edit_message_text(get_text(context.user_data['user_id'], 'jobseeker_bio'))
    return SEEKER_BIO

async def seeker_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bio = update.message.text if update.message.text != '/skip' else ''
    context.user_data['seeker_bio'] = bio
    await update.message.reply_text(get_text(context.user_data['user_id'], 'jobseeker_image'))
    return SEEKER_IMAGE

async def seeker_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        os.makedirs('media/worker_photos/', exist_ok=True)
        file_path = f"media/worker_photos/{context.user_data['user_id']}.jpg"
        await photo_file.download_to_drive(file_path)
        context.user_data['seeker_image'] = file_path
    else:
        if update.message.text == '/skip':
            context.user_data['seeker_image'] = None
        else:
            await update.message.reply_text("Please send a photo or /skip")
            return SEEKER_IMAGE
    # Save all data
    user = await get_user_by_id(context.user_data['user_id'])
    cat_id = context.user_data.get('seeker_category_id')
    sub_id = context.user_data.get('seeker_subcategory_id')
    category = await sync_to_async(Category.objects.get)(id=cat_id) if cat_id else None
    subcategory = await sync_to_async(SubCategory.objects.get)(id=sub_id) if sub_id else None
    await create_jobseeker_profile(
        user=user,
        profession=context.user_data['seeker_profession'],
        category=category,
        subcategory=subcategory,
        experience=context.user_data['seeker_exp'],
        location=context.user_data['seeker_loc'],
        price_per_unit=context.user_data['seeker_price'],
        price_unit=context.user_data['seeker_unit'],
        bio=context.user_data['seeker_bio'],
        profile_image=context.user_data['seeker_image'],
        is_active=True
    )
    await update.message.reply_text(get_text(context.user_data['user_id'], 'jobseeker_success'), reply_markup=await main_menu_keyboard(context.user_data['user_id']))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = context.user_data.get('user_id', 0)
    await update.message.reply_text(get_text(user_id, 'cancel'), reply_markup=await main_menu_keyboard(user_id))
    return ConversationHandler.END

async def rating_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text if update.message.text != '/skip' else ''
    user_id = context.user_data['user_id']
    seeker_id = context.user_data['rating_seeker_id']
    rating = context.user_data['rating_value']
    await add_rating(seeker_id, user_id, rating, comment)
    await update.message.reply_text(get_text(user_id, 'rating_thanks'), reply_markup=await main_menu_keyboard(user_id))
    return ConversationHandler.END

# =========================
# 🏃 MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    # Conversation: profile creation
    profile_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(profile_start, pattern='^create_profile$')],
        states={
            CREATE_PROFILE: [CallbackQueryHandler(select_role, pattern='^role_')],
            CLIENT_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_location)],
            SEEKER_CATEGORY: [CallbackQueryHandler(seeker_category, pattern='^cat_')],
            SEEKER_SUBCAT: [CallbackQueryHandler(seeker_subcategory, pattern='^sub_')],
            SEEKER_PROF: [
                CallbackQueryHandler(seeker_profession, pattern='^(prof_|prof_other)'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_profession)
            ],
            SEEKER_EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_experience)],
            SEEKER_LOC: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_location)],
            SEEKER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_price)],
            SEEKER_UNIT: [CallbackQueryHandler(seeker_unit, pattern='^unit_')],
            SEEKER_BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_bio)],
            SEEKER_IMAGE: [MessageHandler(filters.PHOTO, seeker_image), MessageHandler(filters.TEXT & ~filters.COMMAND, seeker_image)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Conversation: search
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: None, pattern='^search$')],
        states={SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    # Rating comment
    rating_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: None, pattern='^rating_val_')],
        states={RATING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rating_comment)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    # Language / currency settings
    lang_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: None, pattern='^change_lang$')],
        states={LANG_SETTINGS: [CallbackQueryHandler(menu_handler, pattern='^lang_')]},
        fallbacks=[],
    )
    curr_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: None, pattern='^change_curr$')],
        states={CURRENCY_SETTINGS: [CallbackQueryHandler(menu_handler, pattern='^curr_')]},
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern='^(my_profile|browse_talent|settings|help|back_to_main|view_seeker_.*|rate_.*|rating_val_.*|filter_cat_.*|filter_sub_.*|clear_filters|next_page|prev_page|change_lang|change_curr|lang_.*|curr_.*)$'))
    app.add_handler(profile_conv)
    app.add_handler(search_conv)
    app.add_handler(rating_conv)
    app.add_handler(lang_conv)
    app.add_handler(curr_conv)

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    app.add_error_handler(error_handler)

    print("🤖 Advanced Ethiogen Bot is polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()