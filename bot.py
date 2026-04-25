import os
import json
import logging
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Super admin — only one
DATA_FILE = "data.json"

# ConversationHandler states
AGE_CHECK, GENDER_CHECK = range(2)


# ═══════════════════════════════════════════════════
#                      DATA
# ═══════════════════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "users": {},
        "admins": [],          # sub-admins list (IDs as strings)
        "settings": {
            # APK
            "apk_file_id": None,
            "apk_name": "My App",
            "apk_caption": "📱 Download our app!",
            "apk_channel": None,
            # Demo
            "demo_id": None,
            "demo_type": None,         # "video" / "photo" / "text"
            "demo_text": None,
            "demo_channel": None,
            # Welcome
            "welcome_text": "🎉 *Welcome!*\n\nYou have been verified. Enjoy! 😊",
            "welcome_media_id": None,
            "welcome_media_type": None,
            # How to Use
            "how_to_use_text": "ℹ️ Contact admin for instructions.",
            "how_to_use_media_id": None,
            "how_to_use_media_type": None,
            "how_to_use_channel": None,
            # App
            "app_name": "My App",
        },
        "join_dates": {}
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_main_admin(user_id: int) -> bool:
    return user_id == MAIN_ADMIN_ID

def is_admin(user_id: int, data: dict) -> bool:
    return user_id == MAIN_ADMIN_ID or str(user_id) in data.get("admins", [])


# ═══════════════════════════════════════════════════
#                    HELPERS
# ═══════════════════════════════════════════════════

def main_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Download APK", callback_data="dl_apk")],
        [InlineKeyboardButton("🌸 See Demo",      callback_data="see_demo")],
        [InlineKeyboardButton("❓ How to Use",    callback_data="how_use")],
    ])

async def send_welcome(target, settings, edit=False):
    text  = settings.get("welcome_text", "🎉 Welcome!")
    mk    = main_menu_markup()
    mid   = settings.get("welcome_media_id")
    mtype = settings.get("welcome_media_type")
    try:
        if mid and mtype == "photo":
            await target.reply_photo(photo=mid, caption=text, reply_markup=mk, parse_mode="Markdown")
            return
        if mid and mtype == "video":
            await target.reply_video(video=mid, caption=text, reply_markup=mk, parse_mode="Markdown")
            return
        if edit:
            await target.edit_text(text, reply_markup=mk, parse_mode="Markdown")
        else:
            await target.reply_text(text, reply_markup=mk, parse_mode="Markdown")
    except Exception:
        await target.reply_text(text, reply_markup=mk, parse_mode="Markdown")

async def notify_admins(context, data, text):
    """Send notification to main admin + all sub-admins."""
    targets = [MAIN_ADMIN_ID] + [int(a) for a in data.get("admins", [])]
    for tid in targets:
        try:
            await context.bot.send_message(chat_id=tid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Notify {tid} failed: {e}")


# ═══════════════════════════════════════════════════
#                  USER FLOW
# ═══════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    uid     = str(user.id)
    today   = str(date.today())
    data    = load_data()

    # ── Already verified → show menu directly, no re-verification ──
    if uid in data["users"] and data["users"][uid].get("verified"):
        await send_welcome(update.message, data["settings"])
        return ConversationHandler.END

    # ── New user → register & notify once ──
    if uid not in data["users"]:
        data["users"][uid] = {
            "name": user.first_name,
            "username": user.username or "",
            "joined": today,
            "verified": False,
            "gender": None,
            "notified_join":   False,
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

    # ── Age verification ──
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
        # Notify only once
        if uid in data["users"] and not data["users"][uid].get("notified_denied"):
            data["users"][uid]["notified_denied"] = True
            save_data(data)
            await notify_admins(context, data,
                f"❌ *Denied — Under 18*\n"
                f"👤 [{user.first_name}](tg://user?id={user.id}) | `{user.id}` | {uname}"
            )
        await query.edit_message_text("🚫 *Access Denied*\n\nYou must be 18+ to use this bot. 👋", parse_mode="Markdown")
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
        await query.edit_message_text("🚫 *Access Denied*\n\nThis bot is for males only. 👋", parse_mode="Markdown")
        return ConversationHandler.END

    # ── Male verified ──
    if uid in data["users"]:
        data["users"][uid]["verified"] = True
        data["users"][uid]["gender"]   = "male"
        save_data(data)

    verified_count = len([u for u in data["users"].values() if u.get("verified")])
    await notify_admins(context, data,
        f"✅ *User Verified*\n\n"
        f"👤 [{user.first_name}](tg://user?id={user.id})\n"
        f"🆔 `{user.id}` | {uname}\n"
        f"♂️ Male ✅ | 🔞 18+ ✅\n"
        f"✅ Total Verified: *{verified_count}*"
    )
    await query.edit_message_text("✅ *Verified!* Loading...", parse_mode="Markdown")
    await send_welcome(query.message, data["settings"], edit=True)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#               USER MENU CALLBACKS
# ═══════════════════════════════════════════════════

async def user_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    uid      = str(query.from_user.id)
    data     = load_data()
    settings = data["settings"]

    # Security: only verified users
    if not (data["users"].get(uid, {}).get("verified")):
        await query.answer("🚫 Please /start first!", show_alert=True)
        return

    if query.data == "dl_apk":
        apk_id  = settings.get("apk_file_id")
        caption = settings.get("apk_caption", "📱 Download!")
        channel = settings.get("apk_channel")

        buttons = []
        if channel:
            buttons.append([InlineKeyboardButton("📢 Join Channel", url=channel)])

        if apk_id:
            try:
                await query.message.reply_document(document=apk_id, caption=caption,
                                                   reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
            except Exception:
                await query.message.reply_text("❌ Couldn't send APK. Try again later 🌸")
        elif channel:
            await query.message.reply_text(
                f"📱 *Download APK*\n\n{caption}",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("📱 APK not available yet. Check back soon!")

    elif query.data == "see_demo":
        demo_id      = settings.get("demo_id")
        demo_type    = settings.get("demo_type")
        demo_text    = settings.get("demo_text", "Demo coming soon!")
        demo_channel = settings.get("demo_channel")

        buttons = []
        if demo_channel:
            buttons.append([InlineKeyboardButton("📢 Join Channel", url=demo_channel)])

        markup = InlineKeyboardMarkup(buttons) if buttons else None

        try:
            if demo_type == "video" and demo_id:
                await query.message.reply_video(video=demo_id, caption="🌸 Demo Video", reply_markup=markup)
            elif demo_type == "photo" and demo_id:
                await query.message.reply_photo(photo=demo_id, caption="🌸 Demo", reply_markup=markup)
            elif demo_text:
                await query.message.reply_text(f"🌸 *Demo*\n\n{demo_text}", reply_markup=markup, parse_mode="Markdown")
            else:
                await query.message.reply_text("🌸 Demo not available yet!")
        except Exception:
            await query.message.reply_text("❌ Couldn't load demo. Try again later 🌸")

    elif query.data == "how_use":
        how_id      = settings.get("how_to_use_media_id")
        how_type    = settings.get("how_to_use_media_type")
        how_text    = settings.get("how_to_use_text", "ℹ️ Contact admin for instructions.")
        how_channel = settings.get("how_to_use_channel")

        buttons = []
        if how_channel:
            buttons.append([InlineKeyboardButton("📢 Join Channel / Group", url=how_channel)])

        markup = InlineKeyboardMarkup(buttons) if buttons else None

        try:
            if how_type == "video" and how_id:
                await query.message.reply_video(video=how_id, caption=how_text, reply_markup=markup)
            elif how_type == "photo" and how_id:
                await query.message.reply_photo(photo=how_id, caption=how_text, reply_markup=markup)
            else:
                await query.message.reply_text(f"❓ *How to Use*\n\n{how_text}", reply_markup=markup, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(f"❓ *How to Use*\n\n{how_text}", parse_mode="Markdown")


# ═══════════════════════════════════════════════════
#               ADMIN PANEL
# ═══════════════════════════════════════════════════

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        await update.message.reply_text("🚫 Access denied.")
        return
    await show_admin_panel(update.message, data, uid)

async def show_admin_panel(target, data, uid):
    s = data["settings"]
    total    = len(data["users"])
    verified = len([u for u in data["users"].values() if u.get("verified")])
    sub_admins = len(data.get("admins", []))

    apk_st  = "✅ Set" if s.get("apk_file_id") or s.get("apk_channel") else "❌ Not Set"
    demo_st = "✅ Set" if s.get("demo_id") or s.get("demo_text") or s.get("demo_channel") else "❌ Not Set"
    how_st  = "✅ Set" if s.get("how_to_use_text") or s.get("how_to_use_media_id") else "❌ Not Set"

    text = (
        f"💎 *ADMIN PREMIUM PANEL* 💎\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👤 Welcome, Master! ✨\n\n"
        f"👥 Total Users: *{total}*\n"
        f"✅ Verified Males: *{verified}*\n"
        f"🛡 Sub-Admins: *{sub_admins}*\n"
        f"📱 APK: {apk_st}\n"
        f"🌸 Demo: {demo_st}\n"
        f"❓ How to Use: {how_st}\n"
        f"🎪 App Name: *{s.get('app_name', 'N/A')}*\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Manage your empire:"
    )

    kb = [
        [InlineKeyboardButton("📢 Broadcast",        callback_data="adm_broadcast")],
        [InlineKeyboardButton("📱 Send APK To All",  callback_data="adm_send_apk_all")],
        [InlineKeyboardButton("📱 Set APK",          callback_data="adm_set_apk"),
         InlineKeyboardButton("🗑 Remove APK",       callback_data="adm_remove_apk")],
        [InlineKeyboardButton("🔗 APK Channel",      callback_data="adm_apk_channel"),
         InlineKeyboardButton("💬 APK Caption",      callback_data="adm_apk_caption")],
        [InlineKeyboardButton("🎪 APK Name",         callback_data="adm_apk_name")],
        [InlineKeyboardButton("🌸 Set Demo",         callback_data="adm_set_demo"),
         InlineKeyboardButton("🔗 Demo Channel",     callback_data="adm_demo_channel")],
        [InlineKeyboardButton("❓ How to Use",       callback_data="adm_how_to_use"),
         InlineKeyboardButton("🔗 How Channel",      callback_data="adm_how_channel")],
        [InlineKeyboardButton("✏️ Welcome Msg",      callback_data="adm_welcome")],
        [InlineKeyboardButton("📊 Get Report",       callback_data="adm_report")],
        [InlineKeyboardButton("🛡 Manage Sub-Admins", callback_data="adm_manage_admins")],
        [InlineKeyboardButton("📖 Admin Guide",      callback_data="adm_guide")],
    ]
    await target.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    data  = load_data()

    if not is_admin(uid, data):
        await query.answer("🚫 Access denied!", show_alert=True)
        return

    action   = query.data
    settings = data["settings"]

    # ── Simple setters ──
    action_map = {
        "adm_broadcast":    ("broadcast",    "📢 Send any message (text/photo/video/doc). It will go to all verified users:"),
        "adm_set_apk":      ("set_apk",      "📱 Send the APK file now:"),
        "adm_apk_name":     ("apk_name",     "🎪 Send the new App Name:"),
        "adm_apk_caption":  ("apk_caption",  "💬 Send the new APK caption:"),
        "adm_apk_channel":  ("apk_channel",  "🔗 Send the channel/group invite link for APK section:\n(e.g. https://t.me/yourchannel)\n\nSend `remove` to clear."),
        "adm_demo_channel": ("demo_channel", "🔗 Send the channel/group invite link for Demo section:\nSend `remove` to clear."),
        "adm_how_channel":  ("how_channel",  "🔗 Send the channel/group invite link for How to Use section:\nSend `remove` to clear."),
        "adm_welcome":      ("welcome",      "✏️ Send new welcome message (text / photo with caption / video with caption):"),
        "adm_set_demo":     ("set_demo",     "🌸 Send demo (video / photo / text):"),
        "adm_how_to_use":   ("how_to_use",   "❓ Send How to Use content (text / photo with caption / video with caption):"),
        "adm_manage_admins":("manage_admins","🛡 Send Telegram user ID to ADD as sub-admin.\nSend `list` to see all sub-admins.\nSend `remove <ID>` to remove a sub-admin."),
    }

    if action in action_map:
        key, prompt = action_map[action]
        context.user_data["admin_action"] = key
        await query.message.reply_text(prompt, parse_mode="Markdown")
        return

    # ── Remove APK ──
    if action == "adm_remove_apk":
        data["settings"]["apk_file_id"] = None
        save_data(data)
        await query.message.reply_text("🗑 APK file removed!")
        return

    # ── Send APK to all ──
    if action == "adm_send_apk_all":
        apk_id  = settings.get("apk_file_id")
        caption = settings.get("apk_caption", "📱 Download!")
        if not apk_id:
            await query.message.reply_text("❌ No APK set! Upload one first with Set APK.")
            return
        verified = [u for u, d in data["users"].items() if d.get("verified")]
        await query.message.reply_text(f"📱 Sending to {len(verified)} users...")
        sent = failed = 0
        for u in verified:
            try:
                await context.bot.send_document(chat_id=int(u), document=apk_id, caption=caption)
                sent += 1
            except:
                failed += 1
        await query.message.reply_text(f"✅ Done!\n✅ Sent: {sent}\n❌ Failed: {failed}")
        return

    # ── Report ──
    if action == "adm_report":
        today   = str(date.today())
        t_count = data["join_dates"].get(today, 0)
        total   = len(data["users"])
        verified= len([u for u in data["users"].values() if u.get("verified")])
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
            f"✅ Verified Males: *{verified}*\n"
            f"🛡 Sub-Admins: *{len(data.get('admins', []))}*",
            parse_mode="Markdown"
        )
        return

    # ── Guide ──
    if action == "adm_guide":
        await query.message.reply_text(
            "📖 *Admin Guide*\n\n"
            "*/admin* — Open panel\n"
            "*/report* — Quick report\n\n"
            "━━━━ 📢 Broadcast ━━━━\n"
            "Text, photo, video, doc (caption ok) → goes to all verified users.\n\n"
            "━━━━ 📱 APK ━━━━\n"
            "• Set APK — Upload APK file\n"
            "• Remove APK — Delete stored file\n"
            "• APK Name — Display name\n"
            "• APK Caption — Download message\n"
            "• APK Channel — Add channel/group join link\n"
            "• Send APK to All — Blast to all users\n\n"
            "━━━━ 🌸 Demo ━━━━\n"
            "• Set Demo — Video / Photo / Text\n"
            "• Demo Channel — Add channel/group join link\n\n"
            "━━━━ ❓ How to Use ━━━━\n"
            "• How to Use — Text / Photo / Video (with caption)\n"
            "• How Channel — Add channel/group join link\n\n"
            "━━━━ 🛡 Sub-Admins ━━━━\n"
            "• Manage Sub-Admins → Add/Remove/List\n"
            "• Sub-admins get full panel access\n"
            "• Only main admin can manage sub-admins\n\n"
            "━━━━ ✏️ Welcome ━━━━\n"
            "• Welcome Msg — Text / Photo / Video",
            parse_mode="Markdown"
        )
        return


# ═══════════════════════════════════════════════════
#           ADMIN INPUT HANDLER
# ═══════════════════════════════════════════════════

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        return

    action = context.user_data.get("admin_action")
    if not action:
        return

    msg = update.message
    txt = msg.text or ""

    # ── BROADCAST ──
    if action == "broadcast":
        verified = [u for u, d in data["users"].items() if d.get("verified")]
        await msg.reply_text(f"📢 Broadcasting to {len(verified)} users...")
        sent = failed = 0
        for u in verified:
            try:
                await msg.copy(chat_id=int(u))
                sent += 1
            except:
                failed += 1
        await msg.reply_text(f"✅ Broadcast done!\n✅ Sent: {sent}\n❌ Failed: {failed}")

    # ── SET APK ──
    elif action == "set_apk":
        if msg.document:
            data["settings"]["apk_file_id"] = msg.document.file_id
            save_data(data)
            await msg.reply_text("✅ APK uploaded and set!")
        else:
            await msg.reply_text("❌ Please send a document/APK file.")
            return

    # ── APK NAME ──
    elif action == "apk_name":
        data["settings"]["apk_name"] = txt
        data["settings"]["app_name"] = txt
        save_data(data)
        await msg.reply_text(f"✅ App name set to: *{txt}*", parse_mode="Markdown")

    # ── APK CAPTION ──
    elif action == "apk_caption":
        data["settings"]["apk_caption"] = txt
        save_data(data)
        await msg.reply_text("✅ APK caption updated!")

    # ── APK CHANNEL ──
    elif action == "apk_channel":
        if txt.strip().lower() == "remove":
            data["settings"]["apk_channel"] = None
            save_data(data)
            await msg.reply_text("✅ APK channel link removed.")
        else:
            data["settings"]["apk_channel"] = txt.strip()
            save_data(data)
            await msg.reply_text(f"✅ APK channel set to:\n{txt.strip()}")

    # ── DEMO CHANNEL ──
    elif action == "demo_channel":
        if txt.strip().lower() == "remove":
            data["settings"]["demo_channel"] = None
            save_data(data)
            await msg.reply_text("✅ Demo channel link removed.")
        else:
            data["settings"]["demo_channel"] = txt.strip()
            save_data(data)
            await msg.reply_text(f"✅ Demo channel set to:\n{txt.strip()}")

    # ── HOW CHANNEL ──
    elif action == "how_channel":
        if txt.strip().lower() == "remove":
            data["settings"]["how_to_use_channel"] = None
            save_data(data)
            await msg.reply_text("✅ How to Use channel link removed.")
        else:
            data["settings"]["how_to_use_channel"] = txt.strip()
            save_data(data)
            await msg.reply_text(f"✅ How to Use channel set to:\n{txt.strip()}")

    # ── WELCOME ──
    elif action == "welcome":
        if msg.photo:
            data["settings"]["welcome_media_id"]   = msg.photo[-1].file_id
            data["settings"]["welcome_media_type"]  = "photo"
            data["settings"]["welcome_text"]        = msg.caption or "🎉 Welcome!"
        elif msg.video:
            data["settings"]["welcome_media_id"]   = msg.video.file_id
            data["settings"]["welcome_media_type"]  = "video"
            data["settings"]["welcome_text"]        = msg.caption or "🎉 Welcome!"
        elif txt:
            data["settings"]["welcome_text"]        = txt
            data["settings"]["welcome_media_id"]    = None
            data["settings"]["welcome_media_type"]  = None
        save_data(data)
        await msg.reply_text("✅ Welcome message updated!")

    # ── SET DEMO ──
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
        await msg.reply_text("✅ Demo updated!")

    # ── HOW TO USE ──
    elif action == "how_to_use":
        if msg.video:
            data["settings"]["how_to_use_media_id"]   = msg.video.file_id
            data["settings"]["how_to_use_media_type"]  = "video"
            data["settings"]["how_to_use_text"]        = msg.caption or ""
        elif msg.photo:
            data["settings"]["how_to_use_media_id"]   = msg.photo[-1].file_id
            data["settings"]["how_to_use_media_type"]  = "photo"
            data["settings"]["how_to_use_text"]        = msg.caption or ""
        elif txt:
            data["settings"]["how_to_use_media_id"]   = None
            data["settings"]["how_to_use_media_type"]  = None
            data["settings"]["how_to_use_text"]        = txt
        save_data(data)
        await msg.reply_text("✅ How to Use section updated!")

    # ── MANAGE SUB-ADMINS (main admin only) ──
    elif action == "manage_admins":
        if not is_main_admin(uid):
            await msg.reply_text("🚫 Only the main admin can manage sub-admins.")
            context.user_data.pop("admin_action", None)
            return

        admins = data.get("admins", [])

        if txt.strip().lower() == "list":
            if not admins:
                await msg.reply_text("🛡 No sub-admins added yet.")
            else:
                lines = ["🛡 *Current Sub-Admins:*\n"]
                for i, aid in enumerate(admins, 1):
                    lines.append(f"{i}. `{aid}`")
                await msg.reply_text("\n".join(lines), parse_mode="Markdown")
            return  # Don't clear action so admin can send more commands

        elif txt.strip().lower().startswith("remove "):
            remove_id = txt.strip().split(" ", 1)[1].strip()
            if remove_id in admins:
                admins.remove(remove_id)
                data["admins"] = admins
                save_data(data)
                await msg.reply_text(f"✅ Sub-admin `{remove_id}` removed.", parse_mode="Markdown")
            else:
                await msg.reply_text(f"❌ ID `{remove_id}` not found in sub-admins.", parse_mode="Markdown")
            return

        elif txt.strip().isdigit():
            new_id = txt.strip()
            if new_id == str(MAIN_ADMIN_ID):
                await msg.reply_text("⚠️ That's the main admin ID, no need to add.")
                return
            if new_id in admins:
                await msg.reply_text(f"⚠️ `{new_id}` is already a sub-admin.", parse_mode="Markdown")
            else:
                admins.append(new_id)
                data["admins"] = admins
                save_data(data)
                await msg.reply_text(
                    f"✅ Sub-admin added!\n🆔 `{new_id}`\n\n"
                    f"They can now use /admin command.",
                    parse_mode="Markdown"
                )
            return
        else:
            await msg.reply_text(
                "⚠️ Invalid input. Use:\n"
                "• Send a *user ID* to add\n"
                "• `list` to view all\n"
                "• `remove <ID>` to remove",
                parse_mode="Markdown"
            )
            return

    context.user_data.pop("admin_action", None)


# ═══════════════════════════════════════════════════
#               OTHER COMMANDS
# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
#                  /backup COMMAND
# ═══════════════════════════════════════════════════

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        await update.message.reply_text("🚫 Access denied.")
        return

    kb = [
        [
            InlineKeyboardButton("📄 JSON",  callback_data="backup_json"),
            InlineKeyboardButton("📝 TXT",   callback_data="backup_txt"),
            InlineKeyboardButton("📊 CSV",   callback_data="backup_csv"),
        ],
        [
            InlineKeyboardButton("🗂 Full DB Backup", callback_data="backup_full"),
        ]
    ]
    total    = len(data["users"])
    verified = len([u for u in data["users"].values() if u.get("verified")])

    await update.message.reply_text(
        f"🗃 *Backup Panel*\n\n"
        f"👥 Total Users: *{total}*\n"
        f"✅ Verified Males: *{verified}*\n\n"
        f"Choose export format:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


async def backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = query.from_user.id
    data = load_data()

    if not is_admin(uid, data):
        await query.answer("🚫 Access denied!", show_alert=True)
        return

    fmt      = query.data  # backup_json / backup_txt / backup_csv / backup_full
    users    = data["users"]
    now_str  = datetime.now().strftime("%Y-%m-%d_%H-%M")

    await query.message.reply_text("⏳ Generating file...")

    # ── JSON — only user info ──
    if fmt == "backup_json":
        export = []
        for uid_str, u in users.items():
            export.append({
                "id":       uid_str,
                "name":     u.get("name", ""),
                "username": u.get("username", ""),
                "gender":   u.get("gender", ""),
                "verified": u.get("verified", False),
                "joined":   u.get("joined", ""),
            })
        content  = json.dumps(export, indent=2, ensure_ascii=False)
        filename = f"users_{now_str}.json"
        caption  = f"📄 *JSON Export*\n👥 {len(export)} users\n🕐 {now_str}"

    # ── TXT — human readable ──
    elif fmt == "backup_txt":
        lines = [
            f"╔══ USER BACKUP — {now_str} ══╗",
            f"  Total : {len(users)}",
            f"  Verified: {len([u for u in users.values() if u.get('verified')])}",
            "╚══════════════════════════════╝\n",
        ]
        for i, (uid_str, u) in enumerate(users.items(), 1):
            uname   = f"@{u['username']}" if u.get("username") else "—"
            gender  = u.get("gender") or "—"
            status  = "✅ Verified" if u.get("verified") else "❌ Not Verified"
            lines.append(
                f"[{i}]\n"
                f"  ID       : {uid_str}\n"
                f"  Name     : {u.get('name','')}\n"
                f"  Username : {uname}\n"
                f"  Gender   : {gender}\n"
                f"  Status   : {status}\n"
                f"  Joined   : {u.get('joined','')}\n"
            )
        content  = "\n".join(lines)
        filename = f"users_{now_str}.txt"
        caption  = f"📝 *TXT Export*\n👥 {len(users)} users\n🕐 {now_str}"

    # ── CSV — spreadsheet compatible ──
    elif fmt == "backup_csv":
        rows = ["ID,Name,Username,Gender,Verified,Joined"]
        for uid_str, u in users.items():
            uname = f"@{u['username']}" if u.get("username") else ""
            rows.append(
                f"{uid_str},"
                f"\"{u.get('name','')}\" ,"
                f"{uname},"
                f"{u.get('gender','')},"
                f"{u.get('verified', False)},"
                f"{u.get('joined','')}"
            )
        content  = "\n".join(rows)
        filename = f"users_{now_str}.csv"
        caption  = f"📊 *CSV Export*\n👥 {len(users)} users\n🕐 {now_str}\n_(Open in Excel / Google Sheets)_"

    # ── FULL DB — complete data.json ──
    elif fmt == "backup_full":
        content  = json.dumps(data, indent=2, ensure_ascii=False)
        filename = f"full_backup_{now_str}.json"
        caption  = (
            f"🗂 *Full DB Backup*\n"
            f"👥 Users: {len(users)}\n"
            f"🛡 Sub-Admins: {len(data.get('admins',[]))}\n"
            f"🕐 {now_str}\n\n"
            f"⚠️ Contains all settings + user data."
        )
    else:
        return

    # Write temp file and send
    tmp_path = f"/tmp/{filename}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)

    with open(tmp_path, "rb") as f:
        await query.message.reply_document(
            document=f,
            filename=filename,
            caption=caption,
            parse_mode="Markdown"
        )

    os.remove(tmp_path)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = load_data()
    if not is_admin(uid, data):
        await update.message.reply_text("🚫 Access denied.")
        return
    today    = str(date.today())
    t_count  = data["join_dates"].get(today, 0)
    total    = len(data["users"])
    verified = len([u for u in data["users"].values() if u.get("verified")])
    await update.message.reply_text(
        f"📊 *Quick Report*\n\n"
        f"📅 Today: *{t_count}* new users\n"
        f"👥 Total: *{total}*\n"
        f"✅ Verified: *{verified}*\n"
        f"🛡 Sub-Admins: *{len(data.get('admins', []))}*",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════
#                     MAIN
# ═══════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

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
    app.add_handler(CallbackQueryHandler(backup_callback,    pattern="^backup_"))
    app.add_handler(CallbackQueryHandler(admin_callback,     pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(user_menu_callback, pattern="^(dl_apk|see_demo|how_use)$"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_admin_input))

    print("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
