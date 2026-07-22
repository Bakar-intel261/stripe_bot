import os
import logging
import sqlite3
import json
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === CONFIG ===
MANAGER_TOKEN = os.environ.get("MANAGER_TOKEN", "8616799458:AAEx4LWNnJikrSb69ntJLX159RIV84r95fM")
WORKER_BOT_TOKEN = os.environ.get("BOT_TOKEN", "8883120947:AAFQhrxUCktC5ihVlcK5AY5gk_i1KdGwDrQ")

# === DATABASE ===
DB_PATH = "manager.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  credits INTEGER DEFAULT 0,
                  total_generations INTEGER DEFAULT 0,
                  total_spent INTEGER DEFAULT 0,
                  joined_date TIMESTAMP,
                  last_active TIMESTAMP)''')
    # Transactions table
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  type TEXT,
                  amount INTEGER,
                  description TEXT,
                  timestamp TIMESTAMP)''')
    # Generations table
    c.execute('''CREATE TABLE IF NOT EXISTS generations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  status TEXT,
                  credits_used INTEGER,
                  image_size INTEGER,
                  timestamp TIMESTAMP)''')
    # Daily stats
    c.execute('''CREATE TABLE IF NOT EXISTS daily_stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  total_generations INTEGER DEFAULT 0,
                  total_users INTEGER DEFAULT 0,
                  credits_used INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# === DATABASE FUNCTIONS ===
def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def create_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, credits, joined_date, last_active) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, username, first_name, 0, datetime.now(), datetime.now()))
    conn.commit()
    conn.close()

def update_credits(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ?, last_active = ? WHERE user_id = ?", (amount, datetime.now(), user_id))
    conn.commit()
    conn.close()

def add_transaction(user_id, type, amount, description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, type, amount, description, timestamp) VALUES (?, ?, ?, ?, ?)",
              (user_id, type, amount, description, datetime.now()))
    conn.commit()
    conn.close()

def add_generation(user_id, status, credits_used, image_size):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO generations (user_id, status, credits_used, image_size, timestamp) VALUES (?, ?, ?, ?, ?)",
              (user_id, status, credits_used, image_size, datetime.now()))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_generations) FROM users")
    total_generations = c.fetchone()[0] or 0
    c.execute("SELECT SUM(credits) FROM users")
    total_credits = c.fetchone()[0] or 0
    conn.close()
    return total_users, total_generations, total_credits

def get_today_stats():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT total_generations, credits_used FROM daily_stats WHERE date = ?", (today,))
    result = c.fetchone()
    conn.close()
    return result if result else (0, 0)

def update_daily_stats(generations=1, credits_used=10):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO daily_stats (date, total_generations, total_users, credits_used) VALUES (?, ?, ?, ?)",
              (today, 0, 0, 0))
    c.execute("UPDATE daily_stats SET total_generations = total_generations + ?, credits_used = credits_used + ? WHERE date = ?",
              (generations, credits_used, today))
    conn.commit()
    conn.close()

# === BOT HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    username = user.username or "Unknown"
    first_name = user.first_name or "User"
    
    create_user(user_id, username, first_name)
    
    keyboard = [
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("💳 Buy Credits", callback_data="buy")],
        [InlineKeyboardButton("📸 Generate Image", callback_data="generate")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 **Welcome {first_name}!**\n\n"
        "I'm your AI Image Generator Manager.\n\n"
        "💡 **How it works:**\n"
        "• Each generation costs **10 credits**\n"
        "• Send a photo to generate\n"
        "• Use /buy to purchase credits\n\n"
        "🔒 **Privacy:** Your images are deleted immediately.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ User not found. Please use /start first.")
        return
    
    credits = user[3]
    total_gens = user[4]
    total_spent = user[5]
    
    await update.message.reply_text(
        f"💰 **Your Balance**\n\n"
        f"Credits: **{credits}**\n"
        f"Generations: **{total_gens}**\n"
        f"Total spent: **{total_spent}** credits\n\n"
        f"Each generation costs **10 credits**.\n"
        f"Use /buy to purchase more.",
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users, total_generations, total_credits = get_stats()
    today_gens, today_credits = get_today_stats()
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    user_credits = user[3] if user else 0
    
    await update.message.reply_text(
        f"📊 **Global Stats**\n\n"
        f"👤 Total Users: **{total_users}**\n"
        f"🖼️ Total Generations: **{total_generations}**\n"
        f"💰 Credits in circulation: **{total_credits}**\n\n"
        f"📆 **Today**\n"
        f"Generations: **{today_gens}**\n"
        f"Credits used: **{today_credits}**\n\n"
        f"Your balance: **{user_credits}** credits",
        parse_mode="Markdown"
    )

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 100 Credits ($1)", callback_data="buy_100")],
        [InlineKeyboardButton("💳 500 Credits ($4)", callback_data="buy_500")],
        [InlineKeyboardButton("💳 1000 Credits ($7)", callback_data="buy_1000")],
        [InlineKeyboardButton("💳 5000 Credits ($30)", callback_data="buy_5000")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💳 **Buy Credits**\n\n"
        "Select a package below.\n\n"
        "💵 **Payment Method:** Paystack (Card, Bank Transfer, USSD)\n"
        "🔒 **Secure Payment:** Paystack handles all payments.\n"
        "⏳ Credits added instantly after payment.\n\n"
        "**Contact:** @support for issues.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data = query.data
    credits = int(data.split("_")[1])
    amount = credits // 100  # $1 per 100 credits
    
    # In test mode, add credits directly
    update_credits(user_id, credits)
    add_transaction(user_id, "purchase", credits, f"Bought {credits} credits (${amount})")
    
    await query.edit_message_text(
        f"✅ **Payment Successful!**\n\n"
        f"Added **{credits} credits** to your account.\n"
        f"New balance: **{get_user(user_id)[3]}** credits.\n\n"
        f"Send a photo to start generating!",
        parse_mode="Markdown"
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 **Send me a photo** to generate an image.\n\n"
        "⚠️ This will cost **10 credits**.\n"
        "Check /balance to see your credits.",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return
    
    credits = user[3]
    
    if credits < 10:
        await update.message.reply_text(
            f"⛔ **Insufficient credits!**\n\n"
            f"Need **10 credits** to generate.\n"
            f"Your balance: **{credits}**\n\n"
            f"Use /buy to purchase more.",
            parse_mode="Markdown"
        )
        return
    
    # Deduct credits
    update_credits(user_id, -10)
    add_transaction(user_id, "generation", -10, "AI Image Generation")
    
    await update.message.reply_text(
        "🔄 **Processing your image...**\n\n"
        "⏳ This will take about **30 seconds**.\n"
        "Please wait.",
        parse_mode="Markdown"
    )
    
    # Forward to the worker bot
    try:
        worker_app = Application.builder().token(WORKER_BOT_TOKEN).build()
        await worker_app.bot.send_photo(
            chat_id=user_id,
            photo=update.message.photo[-1].file_id,
            caption="📸 Processing your image..."
        )
        await update.message.reply_text(
            "✅ **Image sent to generator!**\n\n"
            "You will receive the result shortly.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error forwarding to worker: {e}")
        await update.message.reply_text(
            "❌ **Error processing your image.**\n\n"
            "Please try again later.",
            parse_mode="Markdown"
        )
        # Refund credits if worker fails
        update_credits(user_id, 10)
        add_transaction(user_id, "refund", 10, "Refund due to worker error")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "balance":
        await balance(update, context)
    elif data == "stats":
        await stats(update, context)
    elif data == "buy":
        await buy(update, context)
    elif data == "generate":
        await generate(update, context)
    elif data.startswith("buy_"):
        await buy_callback(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Help & Commands**\n\n"
        "/start – Welcome\n"
        "/balance – Check your credits\n"
        "/buy – Purchase credits\n"
        "/stats – Global statistics\n"
        "/help – This help\n\n"
        "📸 Send a photo to generate an image.\n"
        "⚠️ Each generation costs **10 credits**.",
        parse_mode="Markdown"
    )

def main():
    if not MANAGER_TOKEN:
        logger.error("❌ MANAGER_TOKEN not set!")
        return
    
    logger.info("🚀 Manager Bot starting...")
    app = Application.builder().token(MANAGER_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("generate", generate))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Photos
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logger.info("✅ Manager Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
