# ============================================
# FILE 1: manager.py – GitHub Actions Manager
# ============================================
import os
import json
import time
import sqlite3
import requests
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from colab_utils import ColabOrchestrator

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MANAGER_TOKEN = os.environ.get("MANAGER_TOKEN", "8616799458:AAEx4LWNnJikrSb69ntJLX159RIV84r95fM")
DB_PATH = "manager.db"

# === DATABASE ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (task_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  status TEXT,
                  credits_used INTEGER DEFAULT 10,
                  created_at TIMESTAMP,
                  completed_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY,
                  credits INTEGER DEFAULT 0,
                  total_generations INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_user_credits(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def deduct_credits(user_id, amount=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits - ?, total_generations = total_generations + 1 WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_task(task_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (task_id, user_id, status, created_at) VALUES (?, ?, ?, ?)",
              (task_id, user_id, "pending", datetime.now()))
    conn.commit()
    conn.close()

def update_task(task_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?", (status, datetime.now(), task_id))
    conn.commit()
    conn.close()

# === BOT HANDLERS ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_credits = get_user_credits(user_id)
    
    if user_credits < 10:
        await update.message.reply_text("❌ Insufficient credits. Please purchase more.")
        return
    
    # Get photo
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    image_data = base64.b64encode(file_bytes).decode('utf-8')
    
    # Create task
    task_id = f"task_{user_id}_{int(time.time())}"
    add_task(task_id, user_id)
    
    await update.message.reply_text(
        f"🔄 **Processing your image...**\n"
        f"⏳ Task ID: `{task_id}`\n"
        f"⏱️ Estimated time: 30 seconds\n\n"
        f"You will receive the result here.",
        parse_mode="Markdown"
    )
    
    # Spawn Colab worker
    orchestrator = ColabOrchestrator()
    success = orchestrator.spawn_worker(task_id, user_id, image_data)
    
    if success:
        # Deduct credits
        deduct_credits(user_id, 10)
        await update.message.reply_text("✅ Task sent to worker! Progress updates will appear here.")
    else:
        update_task(task_id, "failed")
        await update.message.reply_text("❌ Failed to start worker. Please try again later.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    credits = get_user_credits(user_id)
    await update.message.reply_text(
        f"👋 Welcome!\n\n"
        f"💰 Credits: {credits}\n"
        f"Send a photo to generate an image (costs 10 credits).\n\n"
        f"Commands:\n"
        f"/balance - Check your balance\n"
        f"/buy - Purchase credits"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    credits = get_user_credits(user_id)
    await update.message.reply_text(f"💰 Your balance: {credits} credits")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 **Buy Credits**\n\n"
        "Choose a package:\n"
        "/buy_100 - 100 credits ($1)\n"
        "/buy_500 - 500 credits ($4)\n"
        "/buy_1000 - 1000 credits ($7)"
    )

async def buy_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    amount = int(update.message.text.split("_")[1])
    # In test mode, add credits directly
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Added {amount} credits to your account!")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("buy_100", buy_credits))
    app.add_handler(CommandHandler("buy_500", buy_credits))
    app.add_handler(CommandHandler("buy_1000", buy_credits))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
