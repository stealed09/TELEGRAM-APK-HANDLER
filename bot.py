import io
import os
import json
import logging
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.error import TelegramError

import time
import asyncio

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN     = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATA_FILE     = "data.json"

AGE_CHECK, GENDER_CHECK = range(2)


# ═══════════════════════════════════════
#               DATA
# ═══════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "users": {},
        "admins": [],
        "settings": {
            "apk_file_id": None,
            "apk_name": "My App",
            "apk_caption": "Download our app!",
            "apk_channel": None,
            "demo_id": None,
            "demo_type": None,
            "demo_text": None,
            "demo_channel": None,
            "welcome_text": "Welcome! You have been verified. Enjoy!",
            "welcome_media_id": None,
            "welcome_media_type": None,
            "how_to_use_text": "Contact admin for instructions.",
            "how_to_use_media_id": None,
            "how_to_use_media_type": None,
            "how_to_use_channel": None,
            "app_name": "My App",
            # ── Force Join ──
            "force_join_channel": None,
            "force_join_channel_id": None,
        },
        "join_dates": {}
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_main_admin(uid: int) -> bool:
    return uid == MAIN_ADMIN_ID

def is_admin(uid: int, data: dict) -> bool:
    return uid == MAIN_ADMIN_ID or str(uid) in data.get("admins", [])




# ═══════════════════════════════════════
#         FORCE JOIN HELPER
# ═══════════════════════════════════════

async def check_force_join(user_id: int, context: ContextTypes.DEFAULT_TYPE, data: dict) -> bool:
    """True = member or not configured. False = must join."""
    channel_id = data["settings"].get("force_join_channel_id")
    if not channel_id:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except TelegramError as e:
        logger.warning(f"Force join check failed for {user_id}: {e}")
        return True


def force_join_markup(channel_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Join Karo", url=channel_link)],
        [InlineKeyboardButton("✅ Join Ho Gaya – Check Karo", callback_data="fj_check")],
    ])


async def send_force_join_message(target, channel_link: str):
    await target.reply_text(
        "🔒 *Access Blocked!*\n\n"
        "Bot use karne ke liye pehle hamara channel join karo.\n\n"
        "👇 Neeche button dabao, join karo, phir ✅ *Join Ho Gaya* button dabao.",
        reply_markup=force_join_markup(channel_link),
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════
#              HELPERS
# ═══════════════════════════════════════

def user_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Download APK", callback_data="dl_apk")],
        [InlineKeyboardButton("🌸 See Demo",     callback_data="see_demo")],
        [InlineKeyboardButton("❓ How to Use",   callback_data="how_use")],
    ])

async def send_welcome(target, settings, edit=False):
    text  = settings.get("welcome_text", "Welcome!")
    mk    = user_menu_markup()
    mid   = settings.get("welcome_media_id")
    mtype = settings.get("welcome_media_type")
    try:
        if mid and mtype == "photo":
            await target.reply_photo(photo=mid, caption=text, reply_markup=mk)
            return
        if mid and mtype == "video":
            await target.reply_video(video=mid, caption=text, reply_markup=mk)
            return
        if edit:
            await target.edit_text(text, reply_markup=mk)
        else:
            await target.reply_text(text, reply_markup=mk)
    except Exception:
        await target.reply_text(text, reply_markup=mk)

async def notify_admins(context, data, text):
    targets = [MAIN_ADMIN_ID] + [int(a) for a in data.get("admins", [])]
    async def _send(tid):
        try:
            await context.bot.send_message(chat_id=tid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Notify {tid} failed: {e}")
    await asyncio.gather(*[_send(t) for t in targets])


# ═══════════════════════════════════════
#             USER FLOW
# ═══════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    uid   = str(user.id)
    today = str(date.today())
    data  = load_data()

    # ── Force Join Check ──────────────────────────────────────────────────
    settings     = data["settings"]
    channel_link = settings.get("force_join_channel")
    if channel_link:
        joined = await check_force_join(user.id, context, data)
        if not joined:
            await send_force_join_message(update.message, channel_link)
            return ConversationHandler.END
    # ─────────────────────────────────────────────────────────────────────

    # Already verified → direct menu, no re-verification
    if uid in data["users"] and data["users"][uid].get("verified"):
        await send_welcome(update.message, data["settings"])
        return ConversationHandler.END

    # New user → register once
    if uid not in data["users"]:
        data["users"][uid] = {
            "name": user.first_name,
            "username": user.username or "",
            "joined": today,
            "verified": False,
            "gender": None,
            "notified_denied": False,
        }
        data["join_dates"][today] = data["join_dates"].get(today, 0) + 1
        save_data(data)

        uname = f"@{user.username}" if user.username else "No username"
        await notify_admins(context, data,
            f"🔔 *New User Joined!*\n\n"
            f"👤 [{user.first_name}](tg://user?id={user.id})\n"
            f"🆔 `{user.id}` | {uname}\n"
            f"📅 {today} | 👥 Total: *{len(data['users'])}*"
        )

    kb = [[
        InlineKeyboardButton("✅ Yes, I'm 18+", callback_data="age_yes"),
        InlineKeyboardButton("❌ No",            callback_data="age_no"),
    ]]
    await update.message.reply_text(
        "🔞 *Age Verification*\n\nThis bot contains adult content.\nAre you 18 or older?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return AGE_CHECK


async def age_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = query.from_user
    uid   = str(user.id)
    data  = load_data()
    uname = f"@{user.username}" if user.username else "No username"

    if query.data == "age_no":
        if uid in data["users"] and not data["users"][uid].get("notified_denied"):
            data["users"][uid]["notified_denied"] = True
            save_data(data)
            await notify_admins(context, data,
                f"❌ *Denied — Under 18*\n"
                f"👤 [{user.first_name}](tg://user?id={user.id}) | `{user.id}` | {uname}"
            )
        await query.edit_message_text(
            "🚫 *Access Denied*\n\nYou must be 18+ to use this bot. 👋",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    kb = [[
        InlineKeyboardButton("👨 Male",   callback_data="gender_male"),
        InlineKeyboardButton("👩 Female", callback_data="gender_female"),
    ]]
    await query.edit_message_text(
        "✅ *Age Verified!*\n\nSelect your gender:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return GENDER_CHECK


async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = query.from_user
    uid   = str(user.id)
    data  = load_data()
    uname = f"@{user.username}" if user.username else "No username"

    if query.data == "gender_female":
        if uid in data["users"] and not data["users"][uid].get("notified_denied"):
            data["users"][uid]["notified_denied"] = True
            save_data(data)
            await notify_admins(context, data,
                f"🚫 *Denied — Female*\n"
                f"👤 [{user.first_name}](tg://user?id={user.id}) | `{user.id}` | {uname}"
            )
        await query.edit_message_text(
            "🚫 *Access Denied*\n\nThis bot is for males only. 👋",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Male verified
    if uid in data["users"]:
        data["users"][uid]["verified"] = True
        data["users"][uid]["gender"]   = "male"
        save_data(data)

    vc = len([u for u in data["users"].values() if u.get("verified")])
    await notify_admins(context, data,
        f"✅ *User Verified*\n\n"
        f"👤 [{user.first_name}](tg://user?id={user.id})\n"
        f"🆔 `{user.id}` | {uname}\n"
        f"♂️ Male ✅ | 🔞 18+ ✅\n"
        f"✅ Total Verified: *{vc}*"
    )
    await query.edit_message_text("✅ *Verified!* Loading...", parse_mode="Markdown")
    await send_welcome(query.message, data["settings"], edit=True)
    return ConversationHandler.END




# ═══════════════════════════════════════
#     FORCE JOIN CHECK CALLBACK (fj_check)
# ═══════════════════════════════════════

async def force_join_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = load_data()
    settings     = data["settings"]
    channel_link = settings.get("force_join_channel")

    joined = await check_force_join(user.id, context, data)
    if not joined:
        await query.message.reply_text(
            "❌ Abhi bhi join nahi kiya! Pehle join karo.",
            reply_markup=force_join_markup(channel_link),
        )
        return

    uid   = str(user.id)
    today = str(date.today())

    if uid in data["users"] and data["users"][uid].get("verified"):
        await query.edit_message_text("✅ Join confirm ho gaya!")
        await send_welcome(query.message, settings)
        return

    if uid not in data["users"]:
        data["users"][uid] = {
            "name": user.first_name,
            "username": user.username or "",
            "joined": today,
            "verified": False,
            "gender": None,
            "notified_denied": False,
        }
        data["join_dates"][today] = data["join_dates"].get(today, 0) + 1
        save_data(data)
        uname = f"@{user.username}" if user.username else "No username"
        await notify_admins(context, data,
            f"🔔 *New User Joined!*\n\n"
            f"👤 [{user.first_name}](tg://user?id={user.id})\n"
            f"🆔 `{user.id}` | {uname}\n"
            f"📅 {today} | 👥 Total: *{len(data['users'])}*"
        )

    kb = [[
        InlineKeyboardButton("✅ Yes, I'm 18+", callback_data="age_yes"),
        InlineKeyboardButton("❌ No",            callback_data="age_no"),
    ]]
    await query.edit_message_text(
        "✅ *Channel Join Ho Gaya!*\n\n"
        "🔞 *Age Verification*\n\nThis bot contains adult content.\nAre you 18 or older?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════
#          USER MENU CALLBACKS
# ═══════════════════════════════════════

async def user_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    user     = query.from_user
    uid      = str(user.id)
    data     = load_data()
    settings = data["settings"]

    if not data["users"].get(uid, {}).get("verified"):
        await query.answer("Please /start first!", show_alert=True)
        return

    # ── Force Join Check on every menu action ─────────────────────────────
    channel_link = settings.get("force_join_channel")
    if channel_link:
        joined = await check_force_join(user.id, context, data)
        if not joined:
            await query.message.reply_text(
                "🔒 *Access Blocked!*\n\n"
                "Tumne channel chod diya! Dobara join karo bot use karne ke liye.\n\n"
                "👇 Join karo phir ✅ *Join Ho Gaya* dabao.",
                reply_markup=force_join_markup(channel_link),
                parse_mode="Markdown"
            )
            return
    # ─────────────────────────────────────────────────────────────────────

    if query.data == "dl_apk":
        apk_id  = settings.get("apk_file_id")
        caption = settings.get("apk_caption", "Download!")
        channel = settings.get("apk_channel")
        buttons = [[InlineKeyboardButton("📢 Join Channel", url=channel)]] if channel else []
        markup  = InlineKeyboardMarkup(buttons) if buttons else None

        if apk_id:
            try:
                await query.message.reply_document(document=apk_id, caption=caption, reply_markup=markup)
            except Exception:
                await query.message.reply_text("Couldn't send APK. Try again later.")
        elif channel:
            await query.message.reply_text(
                f"📱 Download APK\n\n{caption}",
                reply_markup=markup
            )
        else:
            await query.message.reply_text("APK not available yet. Check back soon!")

    elif query.data == "see_demo":
        demo_id      = settings.get("demo_id")
        demo_type    = settings.get("demo_type")
        demo_text    = settings.get("demo_text", "Demo coming soon!")
        demo_channel = settings.get("demo_channel")
        buttons      = [[InlineKeyboardButton("📢 Join Channel", url=demo_channel)]] if demo_channel else []
        markup       = InlineKeyboardMarkup(buttons) if buttons else None
        try:
            if demo_type == "video" and demo_id:
                await query.message.reply_video(video=demo_id, caption="Demo Video", reply_markup=markup)
            elif demo_type == "photo" and demo_id:
                await query.message.reply_photo(photo=demo_id, caption="Demo", reply_markup=markup)
            elif demo_text:
                await query.message.reply_text(f"Demo\n\n{demo_text}", reply_markup=markup)
            else:
                await query.message.reply_text("Demo not available yet!")
        except Exception:
            await query.message.reply_text("Couldn't load demo. Try again later.")

    elif query.data == "how_use":
        how_id      = settings.get("how_to_use_media_id")
        how_type    = settings.get("how_to_use_media_type")
        how_text    = settings.get("how_to_use_text", "Contact admin for instructions.")
        how_channel = settings.get("how_to_use_channel")
        buttons     = [[InlineKeyboardButton("📢 Join Channel / Group", url=how_channel)]] if how_channel else []
        markup      = InlineKeyboardMarkup(buttons) if buttons else None
        try:
            if how_type == "video" and how_id:
                await query.message.reply_video(video=how_id, caption=how_text, reply_markup=markup)
            elif how_type == "photo" and how_id:
                await query.message.reply_photo(photo=how_id, caption=how_text, reply_markup=markup)
            else:
                await query.message.reply_text(f"How to Use\n\n{how_text}", reply_markup=markup)
        except Exception:
            await query.message.reply_text(f"How to Use\n\n{how_text}")


# ═══════════════════════════════════════
#           ADMIN PANEL
# ═══════════════════════════════════════

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        await update.message.reply_text("Access denied.")
        return
    await show_admin_panel(update.message, data)

async def show_admin_panel(target, data):
    s        = data["settings"]
    total    = len(data["users"])
    verified = len([u for u in data["users"].values() if u.get("verified")])
    n_admins = len(data.get("admins", []))

    apk_st  = "Set" if s.get("apk_file_id") or s.get("apk_channel") else "Not Set"
    fj_st   = s.get("force_join_channel") or "Not Set"
    demo_st = "Set" if s.get("demo_id") or s.get("demo_text") or s.get("demo_channel") else "Not Set"
    how_st  = "Set" if s.get("how_to_use_text") or s.get("how_to_use_media_id") else "Not Set"

    text = (
        f"💎 *ADMIN PREMIUM PANEL* 💎\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Welcome, Master! ✨\n\n"
        f"👥 Total Users: *{total}*\n"
        f"✅ Verified: *{verified}*\n"
        f"🛡 Sub-Admins: *{n_admins}*\n\n"
        f"📱 APK: *{apk_st}*\n"
        f"🌸 Demo: *{demo_st}*\n"
        f"❓ How to Use: *{how_st}*\n"
        f"🎪 App: *{s.get('app_name', 'N/A')}*\n"
        f"🔒 Force Join: *{fj_st}*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Use buttons below:"
    )

    kb = [
        # Row 1 — Broadcast
        [InlineKeyboardButton("📢 Broadcast to All",       callback_data="adm_broadcast")],

        # Row 2 — Force Join
        [InlineKeyboardButton("🔒 Set Force Join Channel", callback_data="adm_set_fj"),
         InlineKeyboardButton("❌ Remove Force Join",      callback_data="adm_remove_fj")],

        # Row 3 — APK actions
        [InlineKeyboardButton("📱 Set APK",                callback_data="adm_set_apk"),
         InlineKeyboardButton("🗑 Remove APK",             callback_data="adm_remove_apk")],

        # Row 3 — APK details
        [InlineKeyboardButton("🎪 APK Name",               callback_data="adm_apk_name"),
         InlineKeyboardButton("💬 APK Caption",            callback_data="adm_apk_caption")],

        # Row 4 — APK send + channel
        [InlineKeyboardButton("📤 Send APK To All",        callback_data="adm_send_apk_all"),
         InlineKeyboardButton("🔗 APK Channel",            callback_data="adm_apk_channel")],

        # Row 5 — Demo
        [InlineKeyboardButton("🌸 Set Demo",               callback_data="adm_set_demo"),
         InlineKeyboardButton("🔗 Demo Channel",           callback_data="adm_demo_channel")],

        # Row 6 — How to Use
        [InlineKeyboardButton("❓ Set How to Use",         callback_data="adm_how_to_use"),
         InlineKeyboardButton("🔗 How to Use Channel",     callback_data="adm_how_channel")],

        # Row 7 — Welcome
        [InlineKeyboardButton("✏️ Set Welcome Message",   callback_data="adm_welcome")],

        # Row 8 — Stats + Backup
        [InlineKeyboardButton("📊 Report",                 callback_data="adm_report"),
         InlineKeyboardButton("🗃 Backup",                 callback_data="adm_backup")],

        # Row 9 — Sub-admins
        [InlineKeyboardButton("🛡 Manage Sub-Admins",      callback_data="adm_manage_admins")],

        # Row 10 — Guide
        [InlineKeyboardButton("📖 Admin Guide",            callback_data="adm_guide")],
    ]
    await target.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    data  = load_data()

    if not is_admin(uid, data):
        await query.answer("Access denied!", show_alert=True)
        return

    action   = query.data
    settings = data["settings"]

    # Prompt-based actions
    prompts = {
        "adm_broadcast":     ("broadcast",     "📢 Send any message (text/photo/video/doc).\nIt will go to ALL verified users:"),
        "adm_set_apk":       ("set_apk",       "📱 Send the APK file now:"),
        "adm_apk_name":      ("apk_name",      "🎪 Send the new App Name:"),
        "adm_apk_caption":   ("apk_caption",   "💬 Send the new APK caption text:"),
        "adm_apk_channel":   ("apk_channel",   "🔗 Send channel/group link for APK button.\nExample: https://t.me/yourchannel\n\nSend 'remove' to delete."),
        "adm_set_demo":      ("set_demo",       "🌸 Send demo content:\n• Video\n• Photo\n• Text message"),
        "adm_demo_channel":  ("demo_channel",  "🔗 Send channel/group link for Demo button.\n\nSend 'remove' to delete."),
        "adm_how_to_use":    ("how_to_use",    "❓ Send How to Use content:\n• Text\n• Photo with caption\n• Video with caption"),
        "adm_how_channel":   ("how_channel",   "🔗 Send channel/group link for How to Use button.\n\nSend 'remove' to delete."),
        "adm_welcome":       ("welcome",       "✏️ Send new Welcome message:\n• Text\n• Photo with caption\n• Video with caption"),
        "adm_manage_admins": ("manage_admins", "🛡 Sub-Admin Manager:\n\n• Send a User ID to ADD as sub-admin\n• Send 'list' to see all sub-admins\n• Send 'remove 123456' to remove one"),
        "adm_set_fj":        ("set_fj",
            "🔒 *Force Join Channel Setup*\n\n"
            "2 cheezein bhejo ek message mein, format:\n\n"
            "`LINK|CHANNEL_ID`\n\n"
            "Example:\n"
            "`https://t.me/mychannel|-1001234567890`\n\n"
            "📌 *CHANNEL_ID kaise milega?*\n"
            "1. Bot ko channel mein admin banao\n"
            "2. Channel par koi bhi message forward karo @userinfobot ko\n"
            "3. Woh ID dega (usually -100 se shuru hota hai)\n\n"
            "Bot ko channel mein *admin* banana ZAROORI hai!"
        ),
    }

    if action in prompts:
        key, prompt = prompts[action]
        context.user_data["admin_action"] = key
        await query.message.reply_text(prompt)
        return

    # Remove Force Join
    if action == "adm_remove_fj":
        data["settings"]["force_join_channel"]    = None
        data["settings"]["force_join_channel_id"] = None
        save_data(data)
        await query.message.reply_text("✅ Force Join hata diya gaya! Ab sabko free access hai.")
        return

    # Remove APK
    if action == "adm_remove_apk":
        data["settings"]["apk_file_id"] = None
        save_data(data)
        await query.message.reply_text("APK file removed!")
        return

    # Send APK to all
    if action == "adm_send_apk_all":
        apk_id  = settings.get("apk_file_id")
        caption = settings.get("apk_caption", "Download!")
        if not apk_id:
            await query.message.reply_text("No APK set! Upload one first.")
            return
        verified = [u for u, d in data["users"].items() if d.get("verified")]
        await query.message.reply_text(f"Sending APK to {len(verified)} users...")
        sent = failed = 0
        sem = asyncio.Semaphore(25)

        async def send_apk_one(u):
            nonlocal sent, failed
            async with sem:
                try:
                    await context.bot.send_document(chat_id=int(u), document=apk_id, caption=caption)
                    sent += 1
                except:
                    failed += 1

        await asyncio.gather(*[send_apk_one(u) for u in verified])
        await query.message.reply_text(f"Done!\nSent: {sent}\nFailed: {failed}")
        return

    # Report
    if action == "adm_report":
        today   = str(date.today())
        t_count = data["join_dates"].get(today, 0)
        total   = len(data["users"])
        ver     = len([u for u in data["users"].values() if u.get("verified")])
        week = month = 0
        for d, cnt in data["join_dates"].items():
            try:
                diff = (date.today() - datetime.strptime(d, "%Y-%m-%d").date()).days
                if diff <= 7:  week  += cnt
                if diff <= 30: month += cnt
            except: pass
        await query.message.reply_text(
            f"📊 *Growth Report*\n\n"
            f"📅 Today: *{t_count}*\n"
            f"📅 This Week: *{week}*\n"
            f"📅 This Month: *{month}*\n\n"
            f"👥 Total Users: *{total}*\n"
            f"✅ Verified Males: *{ver}*\n"
            f"🛡 Sub-Admins: *{len(data.get('admins', []))}*",
            parse_mode="Markdown"
        )
        return

    # Backup — inline format picker
    if action == "adm_backup":
        total   = len(data["users"])
        ver     = len([u for u in data["users"].values() if u.get("verified")])
        kb = [
            [InlineKeyboardButton("📄 JSON",        callback_data="backup_json"),
             InlineKeyboardButton("📝 TXT",          callback_data="backup_txt"),
             InlineKeyboardButton("📊 CSV",          callback_data="backup_csv")],
            [InlineKeyboardButton("🗂 Full DB Backup", callback_data="backup_full")],
        ]
        await query.message.reply_text(
            f"🗃 Backup Panel\n\nTotal Users: {total}\nVerified: {ver}\n\nChoose format:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Guide
    if action == "adm_guide":
        await query.message.reply_text(
            "📖 Admin Guide\n\n"
            "/admin — Open panel\n"
            "/report — Quick stats\n"
            "/backup — Export user data\n\n"
            "BROADCAST\n"
            "Send text/photo/video/doc to all verified users.\n\n"
            "APK\n"
            "Set APK — Upload file\n"
            "Remove APK — Delete file\n"
            "APK Name — App display name\n"
            "APK Caption — Download message\n"
            "APK Channel — Add Join button\n"
            "Send APK to All — Blast to everyone\n\n"
            "DEMO\n"
            "Set Demo — Video/Photo/Text\n"
            "Demo Channel — Add Join button\n\n"
            "HOW TO USE\n"
            "Set content — Text/Photo/Video\n"
            "Channel — Add Join button\n\n"
            "WELCOME\n"
            "Text/Photo/Video shown after verification\n\n"
            "SUB-ADMINS\n"
            "Add/Remove sub-admins by user ID\n"
            "Sub-admins get full panel access\n"
            "Only main admin can manage them"
        )
        return


# ═══════════════════════════════════════
#         ADMIN INPUT HANDLER
# ═══════════════════════════════════════

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        return

    action = context.user_data.get("admin_action")
    if not action:
        return

    msg = update.message
    txt = (msg.text or "").strip()

    if action == "broadcast":
        verified = [u for u, d in data["users"].items() if d.get("verified")]
        await msg.reply_text(f"Broadcasting to {len(verified)} users...")
        sent = failed = 0
        sem = asyncio.Semaphore(25)  # 25 parallel sends

        async def send_one(u):
            nonlocal sent, failed
            async with sem:
                try:
                    await msg.copy(chat_id=int(u))
                    sent += 1
                except:
                    failed += 1

        await asyncio.gather(*[send_one(u) for u in verified])
        await msg.reply_text(f"Done!\nSent: {sent}\nFailed: {failed}")

    elif action == "set_fj":
        if "|" not in txt:
            await msg.reply_text(
                "❌ Format galat hai!\n\n"
                "Sahi format: `LINK|CHANNEL_ID`\n"
                "Example: `https://t.me/mychannel|-1001234567890`",
                parse_mode="Markdown"
            )
            return
        parts = txt.split("|", 1)
        link  = parts[0].strip()
        cid_s = parts[1].strip()
        try:
            cid = int(cid_s)
        except ValueError:
            await msg.reply_text("❌ Channel ID number hona chahiye! Example: -1001234567890")
            return
        try:
            await context.bot.get_chat(chat_id=cid)
        except TelegramError as e:
            await msg.reply_text(
                f"❌ Channel access nahi hua!\n\nError: {e}\n\n"
                "Bot ko channel mein admin banao pehle."
            )
            return
        data["settings"]["force_join_channel"]    = link
        data["settings"]["force_join_channel_id"] = cid
        save_data(data)
        await msg.reply_text(
            f"✅ *Force Join Set!*\n\n"
            f"🔗 Link: {link}\n"
            f"🆔 Channel ID: `{cid}`\n\n"
            f"Ab koi bhi user pehle channel join kiye bina bot use nahi kar sakta!",
            parse_mode="Markdown"
        )

    elif action == "set_apk":
        if msg.document:
            data["settings"]["apk_file_id"] = msg.document.file_id
            save_data(data)
            await msg.reply_text("APK uploaded and set!")
        else:
            await msg.reply_text("Please send a document/APK file.")
            return

    elif action == "apk_name":
        data["settings"]["apk_name"] = txt
        data["settings"]["app_name"] = txt
        save_data(data)
        await msg.reply_text(f"App name set to: {txt}")

    elif action == "apk_caption":
        data["settings"]["apk_caption"] = txt
        save_data(data)
        await msg.reply_text("APK caption updated!")

    elif action == "apk_channel":
        if txt.lower() == "remove":
            data["settings"]["apk_channel"] = None
            await msg.reply_text("APK channel link removed.")
        else:
            data["settings"]["apk_channel"] = txt
            await msg.reply_text(f"APK channel set:\n{txt}")
        save_data(data)

    elif action == "demo_channel":
        if txt.lower() == "remove":
            data["settings"]["demo_channel"] = None
            await msg.reply_text("Demo channel link removed.")
        else:
            data["settings"]["demo_channel"] = txt
            await msg.reply_text(f"Demo channel set:\n{txt}")
        save_data(data)

    elif action == "how_channel":
        if txt.lower() == "remove":
            data["settings"]["how_to_use_channel"] = None
            await msg.reply_text("How to Use channel link removed.")
        else:
            data["settings"]["how_to_use_channel"] = txt
            await msg.reply_text(f"How to Use channel set:\n{txt}")
        save_data(data)

    elif action == "welcome":
        if msg.photo:
            data["settings"]["welcome_media_id"]   = msg.photo[-1].file_id
            data["settings"]["welcome_media_type"] = "photo"
            data["settings"]["welcome_text"]       = msg.caption or "Welcome!"
        elif msg.video:
            data["settings"]["welcome_media_id"]   = msg.video.file_id
            data["settings"]["welcome_media_type"] = "video"
            data["settings"]["welcome_text"]       = msg.caption or "Welcome!"
        elif txt:
            data["settings"]["welcome_text"]       = txt
            data["settings"]["welcome_media_id"]   = None
            data["settings"]["welcome_media_type"] = None
        save_data(data)
        await msg.reply_text("Welcome message updated!")

    elif action == "set_demo":
        if msg.video:
            data["settings"]["demo_id"]   = msg.video.file_id
            data["settings"]["demo_type"] = "video"
            data["settings"]["demo_text"] = msg.caption or ""
        elif msg.photo:
            data["settings"]["demo_id"]   = msg.photo[-1].file_id
            data["settings"]["demo_type"] = "photo"
            data["settings"]["demo_text"] = msg.caption or ""
        elif txt:
            data["settings"]["demo_id"]   = None
            data["settings"]["demo_type"] = "text"
            data["settings"]["demo_text"] = txt
        save_data(data)
        await msg.reply_text("Demo updated!")

    elif action == "how_to_use":
        if msg.video:
            data["settings"]["how_to_use_media_id"]   = msg.video.file_id
            data["settings"]["how_to_use_media_type"] = "video"
            data["settings"]["how_to_use_text"]       = msg.caption or ""
        elif msg.photo:
            data["settings"]["how_to_use_media_id"]   = msg.photo[-1].file_id
            data["settings"]["how_to_use_media_type"] = "photo"
            data["settings"]["how_to_use_text"]       = msg.caption or ""
        elif txt:
            data["settings"]["how_to_use_media_id"]   = None
            data["settings"]["how_to_use_media_type"] = None
            data["settings"]["how_to_use_text"]       = txt
        save_data(data)
        await msg.reply_text("How to Use updated!")

    elif action == "manage_admins":
        if not is_main_admin(uid):
            await msg.reply_text("Only the main admin can manage sub-admins.")
            context.user_data.pop("admin_action", None)
            return

        admins = data.get("admins", [])

        if txt.lower() == "list":
            if not admins:
                await msg.reply_text("No sub-admins added yet.")
            else:
                lines = ["Sub-Admins:\n"] + [f"{i}. {aid}" for i, aid in enumerate(admins, 1)]
                await msg.reply_text("\n".join(lines))
            return  # keep action open

        elif txt.lower().startswith("remove "):
            rid = txt.split(" ", 1)[1].strip()
            if rid in admins:
                admins.remove(rid)
                data["admins"] = admins
                save_data(data)
                await msg.reply_text(f"Sub-admin {rid} removed.")
            else:
                await msg.reply_text(f"ID {rid} not found in sub-admins.")
            return

        elif txt.isdigit():
            if txt == str(MAIN_ADMIN_ID):
                await msg.reply_text("That's the main admin ID.")
                return
            if txt in admins:
                await msg.reply_text(f"{txt} is already a sub-admin.")
            else:
                admins.append(txt)
                data["admins"] = admins
                save_data(data)
                await msg.reply_text(f"Sub-admin added!\nID: {txt}\n\nThey can now use /admin.")
            return

        else:
            await msg.reply_text(
                "Invalid input.\n"
                "• Send a User ID to add\n"
                "• 'list' to view all\n"
                "• 'remove ID' to remove"
            )
            return

    context.user_data.pop("admin_action", None)


# ═══════════════════════════════════════
#           /backup COMMAND
# ═══════════════════════════════════════

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        await update.message.reply_text("Access denied.")
        return
    total   = len(data["users"])
    ver     = len([u for u in data["users"].values() if u.get("verified")])
    kb = [
        [InlineKeyboardButton("📄 JSON",           callback_data="backup_json"),
         InlineKeyboardButton("📝 TXT",             callback_data="backup_txt"),
         InlineKeyboardButton("📊 CSV",             callback_data="backup_csv")],
        [InlineKeyboardButton("🗂 Full DB Backup",  callback_data="backup_full")],
    ]
    await update.message.reply_text(
        f"Backup Panel\n\nTotal Users: {total}\nVerified: {ver}\n\nChoose export format:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    data  = load_data()

    if not is_admin(uid, data):
        await query.answer("Access denied!", show_alert=True)
        return

    fmt     = query.data
    users   = data["users"]
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")

    await query.message.reply_text("Generating file...")

    if fmt == "backup_json":
        export = [
            {
                "id":       k,
                "name":     u.get("name", ""),
                "username": f"@{u['username']}" if u.get("username") else "",
                "gender":   u.get("gender", ""),
                "verified": u.get("verified", False),
                "joined":   u.get("joined", ""),
            }
            for k, u in users.items()
        ]
        content  = json.dumps(export, indent=2, ensure_ascii=False)
        filename = f"users_{now_str}.json"
        caption  = f"JSON Export | {len(export)} users | {now_str}"

    elif fmt == "backup_txt":
        ver_count = len([u for u in users.values() if u.get("verified")])
        lines = [
            f"USER BACKUP — {now_str}",
            f"Total : {len(users)} | Verified: {ver_count}",
            "=" * 40,
            ""
        ]
        for i, (k, u) in enumerate(users.items(), 1):
            uname  = f"@{u['username']}" if u.get("username") else "—"
            status = "Verified" if u.get("verified") else "Not Verified"
            lines += [
                f"[{i}]",
                f"  ID       : {k}",
                f"  Name     : {u.get('name', '')}",
                f"  Username : {uname}",
                f"  Gender   : {u.get('gender') or '—'}",
                f"  Status   : {status}",
                f"  Joined   : {u.get('joined', '')}",
                ""
            ]
        content  = "\n".join(lines)
        filename = f"users_{now_str}.txt"
        caption  = f"TXT Export | {len(users)} users | {now_str}"

    elif fmt == "backup_csv":
        rows = ["ID,Name,Username,Gender,Verified,Joined"]
        for k, u in users.items():
            name  = u.get("name", "").replace('"', "'")
            uname = f"@{u['username']}" if u.get("username") else ""
            rows.append(f'{k},"{name}",{uname},{u.get("gender","")},{u.get("verified",False)},{u.get("joined","")}')
        content  = "\n".join(rows)
        filename = f"users_{now_str}.csv"
        caption  = f"CSV Export | {len(users)} users | {now_str} | Open in Excel or Google Sheets"

    elif fmt == "backup_full":
        content  = json.dumps(data, indent=2, ensure_ascii=False)
        filename = f"full_backup_{now_str}.json"
        caption  = f"Full DB Backup | {now_str} | Users: {len(users)} | Sub-Admins: {len(data.get('admins',[]))}"
    else:
        return

    # Use BytesIO — no file system write needed
    buf = io.BytesIO(content.encode("utf-8"))
    buf.name = filename
    await query.message.reply_document(document=buf, filename=filename, caption=caption)


# ═══════════════════════════════════════
#           /report COMMAND
# ═══════════════════════════════════════

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        await update.message.reply_text("Access denied.")
        return
    today   = str(date.today())
    t_count = data["join_dates"].get(today, 0)
    total   = len(data["users"])
    ver     = len([u for u in data["users"].values() if u.get("verified")])
    await update.message.reply_text(
        f"📊 *Quick Report*\n\n"
        f"📅 Today: *{t_count}* new users\n"
        f"👥 Total: *{total}*\n"
        f"✅ Verified: *{ver}*\n"
        f"🛡 Sub-Admins: *{len(data.get('admins', []))}*",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════
#         /help COMMAND
# ═══════════════════════════════════════

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid      = str(update.effective_user.id)
    data     = load_data()
    settings = data["settings"]
    is_ver   = data["users"].get(uid, {}).get("verified", False)

    if is_ver:
        how_text    = settings.get("how_to_use_text", "")
        how_id      = settings.get("how_to_use_media_id")
        how_type    = settings.get("how_to_use_media_type")
        how_channel = settings.get("how_to_use_channel")
        buttons = []
        if how_channel:
            buttons.append([InlineKeyboardButton("📢 Join Channel / Group", url=how_channel)])
        buttons.append([InlineKeyboardButton("📱 Download APK", callback_data="dl_apk")])
        buttons.append([InlineKeyboardButton("🌸 See Demo",     callback_data="see_demo")])
        markup = InlineKeyboardMarkup(buttons)
        try:
            if how_type == "video" and how_id:
                await update.message.reply_video(video=how_id, caption=how_text or "How to Use Guide", reply_markup=markup)
            elif how_type == "photo" and how_id:
                await update.message.reply_photo(photo=how_id, caption=how_text or "How to Use Guide", reply_markup=markup)
            else:
                text = (
                    "How to Use Guide\n\n"
                    + (how_text if how_text else "Contact admin for instructions.")
                    + "\n\nCommands:\n/start — Main menu\n/help — This guide\n/ping — Bot status"
                )
                await update.message.reply_text(text, reply_markup=markup)
        except Exception:
            await update.message.reply_text("Contact admin for help.")
    else:
        kb = [[InlineKeyboardButton("Start Verification", callback_data="go_start")]]
        await update.message.reply_text(
            "How to Use\n\n"
            "1. Use /start to begin\n"
            "2. Confirm you are 18+\n"
            "3. Select your gender (Males only)\n"
            "4. Get access to APK and Demo!\n\n"
            "Commands:\n"
            "/start — Begin verification\n"
            "/help — This guide\n"
            "/ping — Bot status",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ═══════════════════════════════════════
#         /ping COMMAND
# ═══════════════════════════════════════

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_t = time.time()
    msg     = await update.message.reply_text("Pinging...")
    ms      = round((time.time() - start_t) * 1000)
    data    = load_data()
    total   = len(data["users"])
    ver     = len([u for u in data["users"].values() if u.get("verified")])
    fj  = data["settings"].get("force_join_channel") or "Off"
    await msg.edit_text(
        f"Pong!\n\n"
        f"Latency: {ms}ms\n"
        f"Bot Status: Online\n"
        f"Total Users: {total}\n"
        f"Verified: {ver}\n"
        f"Force Join: {fj}"
    )


async def go_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Re-trigger start flow
    uid  = str(query.from_user.id)
    data = load_data()
    if data["users"].get(uid, {}).get("verified"):
        await send_welcome(query.message, data["settings"])
    else:
        kb = [[
            InlineKeyboardButton("Yes, I'm 18+", callback_data="age_yes"),
            InlineKeyboardButton("No",            callback_data="age_no"),
        ]]
        await query.message.reply_text(
            "Age Verification\n\nAre you 18 or older?",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ═══════════════════════════════════════
#                MAIN
# ═══════════════════════════════════════

async def post_init(app):
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start", "Start checking"),
        BotCommand("help",  "How to use guide"),
        BotCommand("ping",  "Bot Status and Latency"),
        BotCommand("admin", "Admin Panel"),
    ])


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .connection_pool_size(16)
        .connect_timeout(10)
        .read_timeout(10)
        .write_timeout(10)
        .pool_timeout(5)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGE_CHECK:    [CallbackQueryHandler(age_callback,    pattern="^age_")],
            GENDER_CHECK: [CallbackQueryHandler(gender_callback, pattern="^gender_")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("admin",  admin_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("ping",   ping_command))
    app.add_handler(CallbackQueryHandler(force_join_check_callback, pattern="^fj_check$"))
    app.add_handler(CallbackQueryHandler(backup_callback,    pattern="^backup_"))
    app.add_handler(CallbackQueryHandler(admin_callback,     pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(user_menu_callback, pattern="^(dl_apk|see_demo|how_use)$"))
    app.add_handler(CallbackQueryHandler(go_start_callback,  pattern="^go_start$"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_admin_input))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True, poll_interval=0.0, timeout=10, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
