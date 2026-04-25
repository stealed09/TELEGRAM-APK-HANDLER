import os
import json
import logging
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DATA_FILE = "data.json"

# States
AGE_CHECK, GENDER_CHECK, MAIN_MENU = range(3)
ADMIN_WAITING = "admin_waiting"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "users": {},
        "settings": {
            "apk_file_id": None,
            "apk_name": "App",
            "apk_caption": "Download our app!",
            "demo_video_id": None,
            "demo_video_type": None,  # "video" or "photo" or "text"
            "demo_text": None,
            "welcome_text": "Welcome! 🎉",
            "welcome_media_id": None,
            "welcome_media_type": None,
            "how_to_use_text": None,
            "how_to_use_media_id": None,
            "how_to_use_media_type": None,
            "app_name": "My App",
            "status": True
        },
        "join_dates": {}
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_admin(user_id):
    return user_id == ADMIN_ID

# ==================== USER FLOW ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    
    user_id = str(user.id)
    today = str(date.today())
    
    # Track join date
    is_new_user = user_id not in data["users"]
    if is_new_user:
        data["users"][user_id] = {
            "name": user.first_name,
            "username": user.username or "",
            "joined": today,
            "verified": False,
            "gender": None
        }
        if today not in data["join_dates"]:
            data["join_dates"][today] = 0
        data["join_dates"][today] += 1
        save_data(data)
        
        # Notify admin about new user
        total_users = len(data["users"])
        username_str = f"@{user.username}" if user.username else "No username"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🔔 *New User Joined!*\n\n"
                    f"👤 Name: [{user.first_name}](tg://user?id={user.id})\n"
                    f"🆔 ID: `{user.id}`\n"
                    f"📛 Username: {username_str}\n"
                    f"📅 Date: {today}\n\n"
                    f"👥 Total Users: *{total_users}*"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify admin: {e}")
    
    # Age verification
    keyboard = [
        [InlineKeyboardButton("✅ Yes, I'm 18+", callback_data="age_yes"),
         InlineKeyboardButton("❌ No", callback_data="age_no")]
    ]
    await update.message.reply_text(
        "🔞 *Age Verification Required*\n\n"
        "This bot contains adult content.\n"
        "Are you 18 years or older?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return AGE_CHECK

async def age_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "age_no":
        # Notify admin
        user_obj = query.from_user
        username_str = f"@{user_obj.username}" if user_obj.username else "No username"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"❌ *User Denied (Under 18)*\n\n"
                    f"👤 Name: [{user_obj.first_name}](tg://user?id={user_obj.id})\n"
                    f"🆔 ID: `{user_obj.id}`\n"
                    f"📛 Username: {username_str}\n"
                    f"🔞 Age: Under 18 ❌"
                ),
                parse_mode="Markdown"
            )
        except:
            pass
        await query.edit_message_text(
            "🚫 *Access Denied*\n\n"
            "Sorry, you must be 18+ to use this bot.\n"
            "Come back when you're older! 👋",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Ask gender
    keyboard = [
        [InlineKeyboardButton("👨 Male", callback_data="gender_male"),
         InlineKeyboardButton("👩 Female", callback_data="gender_female")]
    ]
    await query.edit_message_text(
        "✅ *Age Verified!*\n\n"
        "Please select your gender:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return GENDER_CHECK

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == "gender_female":
        # Notify admin
        user_obj = query.from_user
        username_str = f"@{user_obj.username}" if user_obj.username else "No username"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚫 *User Denied (Female)*\n\n"
                    f"👤 Name: [{user_obj.first_name}](tg://user?id={user_obj.id})\n"
                    f"🆔 ID: `{user_obj.id}`\n"
                    f"📛 Username: {username_str}\n"
                    f"♀️ Gender: Female ❌"
                ),
                parse_mode="Markdown"
            )
        except:
            pass
        await query.edit_message_text(
            "🚫 *Access Denied*\n\n"
            "Sorry, this bot is for males only.\n"
            "We apologize for the inconvenience! 👋",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Male - grant access
    data = load_data()
    user_obj = query.from_user
    if user_id in data["users"]:
        data["users"][user_id]["verified"] = True
        data["users"][user_id]["gender"] = "male"
        save_data(data)
    
    # Notify admin - verified male
    username_str = f"@{user_obj.username}" if user_obj.username else "No username"
    total_verified = len([u for u in data["users"].values() if u.get("verified")])
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"✅ *User Verified (Male)*\n\n"
                f"👤 Name: [{user_obj.first_name}](tg://user?id={user_obj.id})\n"
                f"🆔 ID: `{user_obj.id}`\n"
                f"📛 Username: {username_str}\n"
                f"♂️ Gender: Male ✅\n"
                f"🔞 Age: 18+ ✅\n\n"
                f"✅ Total Verified: *{total_verified}*"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not notify admin: {e}")
    
    await query.edit_message_text("✅ *Access Granted!*\n\nLoading...", parse_mode="Markdown")
    await show_main_menu(query.message, context, data["settings"], edit=True)
    return MAIN_MENU

async def show_main_menu(message, context, settings, edit=False):
    text = settings.get("welcome_text", "Welcome! 🎉")
    keyboard = [
        [InlineKeyboardButton("📱 Download APK", callback_data="download_apk")],
        [InlineKeyboardButton("🌸 See Demo", callback_data="see_demo")],
        [InlineKeyboardButton("❓ How to Use", callback_data="how_to_use")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    welcome_media = settings.get("welcome_media_id")
    welcome_type = settings.get("welcome_media_type")
    
    try:
        if welcome_media and welcome_type == "photo":
            await message.reply_photo(photo=welcome_media, caption=text, reply_markup=markup)
        elif welcome_media and welcome_type == "video":
            await message.reply_video(video=welcome_media, caption=text, reply_markup=markup)
        else:
            if edit:
                await message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
            else:
                await message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    except:
        await message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    settings = data["settings"]
    
    if query.data == "download_apk":
        apk_id = settings.get("apk_file_id")
        if not apk_id:
            await query.message.reply_text("📱 APK not available right now. Check back later! 🌸")
            return
        caption = settings.get("apk_caption", "Download the app!")
        try:
            await query.message.reply_document(document=apk_id, caption=caption)
        except:
            await query.message.reply_text("❌ Couldn't send the file right now. Try again 🌸")
    
    elif query.data == "see_demo":
        demo_id = settings.get("demo_video_id")
        demo_type = settings.get("demo_video_type")
        demo_text = settings.get("demo_text")
        
        if demo_type == "video" and demo_id:
            try:
                await query.message.reply_video(video=demo_id, caption="🌸 Demo Video")
            except:
                await query.message.reply_text("❌ Couldn't load demo. Try again later 🌸")
        elif demo_type == "photo" and demo_id:
            try:
                await query.message.reply_photo(photo=demo_id, caption="🌸 Demo")
            except:
                await query.message.reply_text("❌ Couldn't load demo. Try again later 🌸")
        elif demo_text:
            await query.message.reply_text(f"🌸 *Demo*\n\n{demo_text}", parse_mode="Markdown")
        else:
            await query.message.reply_text("🌸 Demo not available yet. Check back soon!")
    
    elif query.data == "how_to_use":
        how_id = settings.get("how_to_use_media_id")
        how_type = settings.get("how_to_use_media_type")
        how_text = settings.get("how_to_use_text", "Contact admin for instructions.")
        
        if how_type == "video" and how_id:
            await query.message.reply_video(video=how_id, caption=how_text)
        elif how_type == "photo" and how_id:
            await query.message.reply_photo(photo=how_id, caption=how_text)
        else:
            await query.message.reply_text(f"❓ *How to Use*\n\n{how_text}", parse_mode="Markdown")

# ==================== ADMIN PANEL ====================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Access denied.")
        return
    
    data = load_data()
    settings = data["settings"]
    total_users = len(data["users"])
    
    apk_status = "✅ Set" if settings.get("apk_file_id") else "❌ Not Set"
    demo_status = "✅ Set" if settings.get("demo_video_id") or settings.get("demo_text") else "❌ Not Set"
    
    text = (
        f"💎 *ADMIN PREMIUM PANEL* 💎\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👤 Welcome, Master! ✨\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 Total Users Joined: *{total_users}*\n"
        f"📱 App Status: {apk_status}\n"
        f"🎪 App Name: *{settings.get('app_name', 'Not Set')}*\n"
        f"🌸 Demo Video: {demo_status}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"⚡ Use the buttons below to manage your empire:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast 📢", callback_data="adm_broadcast")],
        [InlineKeyboardButton("📱 Send APK To All 📱", callback_data="adm_send_apk_all")],
        [InlineKeyboardButton("📱 Set APK 📱", callback_data="adm_set_apk"),
         InlineKeyboardButton("🗑 Remove APK 🗑", callback_data="adm_remove_apk")],
        [InlineKeyboardButton("🎪 APK Name 🎪", callback_data="adm_apk_name"),
         InlineKeyboardButton("💬 APK Caption 💬", callback_data="adm_apk_caption")],
        [InlineKeyboardButton("✏️ Welcome ✏️", callback_data="adm_welcome"),
         InlineKeyboardButton("🌸 Set Demo 🌸", callback_data="adm_set_demo")],
        [InlineKeyboardButton("❓ How to use ❓", callback_data="adm_how_to_use"),
         InlineKeyboardButton("📊 Get Report 📊", callback_data="adm_report")],
        [InlineKeyboardButton("📖 Admin Guide 📖", callback_data="adm_guide")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("🚫 Access denied!", show_alert=True)
        return
    
    data = load_data()
    settings = data["settings"]
    action = query.data
    
    if action == "adm_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await query.message.reply_text(
            "📢 *Broadcast Mode*\n\n"
            "Send any message (text, photo, video, document with caption).\n"
            "It will be sent to all verified users.",
            parse_mode="Markdown"
        )
    
    elif action == "adm_set_apk":
        context.user_data["admin_action"] = "set_apk"
        await query.message.reply_text("📱 Send the APK file now:")
    
    elif action == "adm_remove_apk":
        data["settings"]["apk_file_id"] = None
        save_data(data)
        await query.message.reply_text("🗑 APK removed successfully!")
    
    elif action == "adm_apk_name":
        context.user_data["admin_action"] = "apk_name"
        await query.message.reply_text("🎪 Send the new APK name:")
    
    elif action == "adm_apk_caption":
        context.user_data["admin_action"] = "apk_caption"
        await query.message.reply_text("💬 Send the new APK caption:")
    
    elif action == "adm_welcome":
        context.user_data["admin_action"] = "welcome"
        await query.message.reply_text(
            "✏️ *Set Welcome Message*\n\n"
            "Send text, photo, or video for welcome message:",
            parse_mode="Markdown"
        )
    
    elif action == "adm_set_demo":
        context.user_data["admin_action"] = "set_demo"
        await query.message.reply_text(
            "🌸 *Set Demo*\n\n"
            "Send demo video, photo, or text:",
            parse_mode="Markdown"
        )
    
    elif action == "adm_how_to_use":
        context.user_data["admin_action"] = "how_to_use"
        await query.message.reply_text(
            "❓ *Set How to Use*\n\n"
            "Send text, photo, or video for how to use guide:",
            parse_mode="Markdown"
        )
    
    elif action == "adm_send_apk_all":
        apk_id = settings.get("apk_file_id")
        if not apk_id:
            await query.message.reply_text("❌ No APK set! Set APK first.")
            return
        
        caption = settings.get("apk_caption", "Download the app!")
        sent = 0
        failed = 0
        verified_users = [uid for uid, u in data["users"].items() if u.get("verified")]
        
        await query.message.reply_text(f"📱 Sending APK to {len(verified_users)} users...")
        
        for uid in verified_users:
            try:
                await context.bot.send_document(chat_id=int(uid), document=apk_id, caption=caption)
                sent += 1
            except:
                failed += 1
        
        await query.message.reply_text(f"✅ APK sent!\n✅ Success: {sent}\n❌ Failed: {failed}")
    
    elif action == "adm_report":
        today = str(date.today())
        today_count = data["join_dates"].get(today, 0)
        total = len(data["users"])
        verified = len([u for u in data["users"].values() if u.get("verified")])
        
        # Weekly count
        from datetime import timedelta
        week_count = 0
        month_count = 0
        for d, count in data["join_dates"].items():
            try:
                d_date = datetime.strptime(d, "%Y-%m-%d").date()
                days_diff = (date.today() - d_date).days
                if days_diff <= 7:
                    week_count += count
                if days_diff <= 30:
                    month_count += count
            except:
                pass
        
        await query.message.reply_text(
            f"📊 *Growth Report*\n\n"
            f"📅 Today: *{today_count}* users\n"
            f"📅 This Week: *{week_count}* users\n"
            f"📅 This Month: *{month_count}* users\n\n"
            f"👥 Total Users: *{total}*\n"
            f"✅ Verified Males: *{verified}*",
            parse_mode="Markdown"
        )
    
    elif action == "adm_guide":
        await query.message.reply_text(
            "📖 *Admin Guide*\n\n"
            "*/admin* — Admin panel\n"
            "*/report* — Quick report\n\n"
            "━━━━ 📢 Broadcast ━━━━\n"
            "• Click Broadcast → send any message\n"
            "• Text, photo, video, document (caption ok)\n\n"
            "━━━━ 📱 APK & Guide ━━━━\n"
            "• Set APK — Upload APK file\n"
            "• APK Name — Set display name\n"
            "• APK Caption — Set download caption\n"
            "• How to use — Set guide (text/photo/video)\n"
            "• Send APK to all — Blast to all users\n\n"
            "━━━━ 📊 Reports ━━━━\n"
            "• Get Report — Today/week/month stats\n\n"
            "━━━━ ✏️ Welcome & Demo ━━━━\n"
            "• Welcome — Set welcome message\n"
            "• Set Demo — Set demo video/photo/text",
            parse_mode="Markdown"
        )

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    action = context.user_data.get("admin_action")
    if not action:
        return
    
    data = load_data()
    msg = update.message
    
    if action == "broadcast":
        users = data["users"]
        verified_users = [uid for uid, u in users.items() if u.get("verified")]
        sent = 0
        failed = 0
        
        await msg.reply_text(f"📢 Broadcasting to {len(verified_users)} users...")
        
        for uid in verified_users:
            try:
                await msg.copy(chat_id=int(uid))
                sent += 1
            except:
                failed += 1
        
        await msg.reply_text(f"✅ Broadcast done!\n✅ Sent: {sent}\n❌ Failed: {failed}")
    
    elif action == "set_apk":
        if msg.document:
            data["settings"]["apk_file_id"] = msg.document.file_id
            save_data(data)
            await msg.reply_text("✅ APK set successfully!")
        else:
            await msg.reply_text("❌ Please send a document/APK file!")
        
    elif action == "apk_name":
        data["settings"]["apk_name"] = msg.text
        save_data(data)
        await msg.reply_text(f"✅ APK Name set to: *{msg.text}*", parse_mode="Markdown")
    
    elif action == "apk_caption":
        data["settings"]["apk_caption"] = msg.text
        save_data(data)
        await msg.reply_text("✅ APK Caption updated!")
    
    elif action == "welcome":
        if msg.photo:
            data["settings"]["welcome_media_id"] = msg.photo[-1].file_id
            data["settings"]["welcome_media_type"] = "photo"
            data["settings"]["welcome_text"] = msg.caption or "Welcome! 🎉"
        elif msg.video:
            data["settings"]["welcome_media_id"] = msg.video.file_id
            data["settings"]["welcome_media_type"] = "video"
            data["settings"]["welcome_text"] = msg.caption or "Welcome! 🎉"
        elif msg.text:
            data["settings"]["welcome_text"] = msg.text
            data["settings"]["welcome_media_id"] = None
            data["settings"]["welcome_media_type"] = None
        save_data(data)
        await msg.reply_text("✅ Welcome message updated!")
    
    elif action == "set_demo":
        if msg.video:
            data["settings"]["demo_video_id"] = msg.video.file_id
            data["settings"]["demo_video_type"] = "video"
        elif msg.photo:
            data["settings"]["demo_video_id"] = msg.photo[-1].file_id
            data["settings"]["demo_video_type"] = "photo"
        elif msg.text:
            data["settings"]["demo_text"] = msg.text
            data["settings"]["demo_video_id"] = None
            data["settings"]["demo_video_type"] = None
        save_data(data)
        await msg.reply_text("✅ Demo updated!")
    
    elif action == "how_to_use":
        if msg.video:
            data["settings"]["how_to_use_media_id"] = msg.video.file_id
            data["settings"]["how_to_use_media_type"] = "video"
            data["settings"]["how_to_use_text"] = msg.caption or ""
        elif msg.photo:
            data["settings"]["how_to_use_media_id"] = msg.photo[-1].file_id
            data["settings"]["how_to_use_media_type"] = "photo"
            data["settings"]["how_to_use_text"] = msg.caption or ""
        elif msg.text:
            data["settings"]["how_to_use_text"] = msg.text
            data["settings"]["how_to_use_media_id"] = None
            data["settings"]["how_to_use_media_type"] = None
        save_data(data)
        await msg.reply_text("✅ How to use guide updated!")
    
    context.user_data.pop("admin_action", None)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Access denied.")
        return
    
    data = load_data()
    today = str(date.today())
    today_count = data["join_dates"].get(today, 0)
    total = len(data["users"])
    verified = len([u for u in data["users"].values() if u.get("verified")])
    
    await update.message.reply_text(
        f"📊 *Quick Report*\n\n"
        f"📅 Today: *{today_count}* new users\n"
        f"👥 Total: *{total}* users\n"
        f"✅ Verified: *{verified}*",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGE_CHECK: [CallbackQueryHandler(age_callback, pattern="^age_")],
            GENDER_CHECK: [CallbackQueryHandler(gender_callback, pattern="^gender_")],
            MAIN_MENU: [CallbackQueryHandler(menu_callback, pattern="^(download_apk|see_demo|how_to_use)$")]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^(download_apk|see_demo|how_to_use)$"))
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND & filters.User(ADMIN_ID),
        handle_admin_input
    ))
    
    print("🤖 Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
