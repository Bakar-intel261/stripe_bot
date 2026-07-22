import os
import json
import time
import base64
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8883120947:AAFQhrxUCktC5ihVlcK5AY5gk_i1KdGwDrQ")
MANAGER_TOKEN = os.environ.get("MANAGER_TOKEN", "8616799458:AAEx4LWNnJikrSb69ntJLX159RIV84r95fM")
SUPABASE_URL = "https://nidptbrkgxjnupqpqakt.supabase.co"
SUPABASE_KEY = "sb_publishable_G93jIOS4WBZBCqwGYyj4og_J9roWaDs"

# === SUPABASE ===
def supabase_request(method, endpoint, data=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    try:
        response = requests.request(method, url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201, 204]:
            return response.json() if response.text else {}
        return None
    except Exception as e:
        print(f"Supabase error: {e}")
        return None

def get_user(user_id):
    result = supabase_request("GET", f"users?user_id=eq.{user_id}")
    return result[0] if result else None

def create_user(user_id, username="Unknown", first_name="User"):
    existing = get_user(user_id)
    if existing:
        return existing
    data = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "credits": 0,
        "total_generations": 0,
        "joined_date": datetime.now().isoformat()
    }
    return supabase_request("POST", "users", data)

def get_user_credits(user_id):
    user = get_user(user_id)
    return user["credits"] if user else 0

def deduct_credits(user_id, amount=10):
    user = get_user(user_id)
    if not user:
        return None
    data = {
        "credits": user["credits"] - amount,
        "total_generations": user["total_generations"] + 1
    }
    return supabase_request("PATCH", f"users?user_id=eq.{user_id}", data)

def add_credits(user_id, amount):
    user = get_user(user_id)
    if not user:
        return None
    data = {"credits": user["credits"] + amount}
    return supabase_request("PATCH", f"users?user_id=eq.{user_id}", data)

def create_task(task_id, user_id, image_data):
    data = {
        "task_id": task_id,
        "user_id": user_id,
        "status": "pending",
        "image_data": image_data,
        "created_at": datetime.now().isoformat()
    }
    return supabase_request("POST", "tasks", data)

def update_task(task_id, status, error=None):
    data = {"status": status, "completed_at": datetime.now().isoformat()}
    if error:
        data["error"] = error
    return supabase_request("PATCH", f"tasks?task_id=eq.{task_id}", data)

def get_stats():
    users = supabase_request("GET", "users")
    generations = supabase_request("GET", "generations")
    total_users = len(users) if users else 0
    total_gens = len(generations) if generations else 0
    total_credits = sum([u.get("credits", 0) for u in users]) if users else 0
    return total_users, total_gens, total_credits

def add_generation_log(user_id, task_id, status, credits_used=10):
    data = {
        "user_id": user_id,
        "task_id": task_id,
        "status": status,
        "credits_used": credits_used,
        "created_at": datetime.now().isoformat()
    }
    return supabase_request("POST", "generations", data)

# === COLAB ORCHESTRATOR ===
def spawn_colab_worker(task_id, user_id, image_data):
    """Try to spawn a Colab worker using google-colab-cli or API."""
    try:
        import subprocess
        cmd = [
            "colab", "run",
            "--env", f"USER_ID={user_id}",
            "--env", f"TASK_ID={task_id}",
            "--env", f"IMAGE_DATA={image_data}",
            "--env", f"BOT_TOKEN={BOT_TOKEN}",
            "--env", f"SUPABASE_URL={SUPABASE_URL}",
            "--env", f"SUPABASE_KEY={SUPABASE_KEY}",
            "worker_template.py"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return True
        print(f"Colab CLI error: {result.stderr}")
        return False
    except Exception as e:
        print(f"Colab spawn error: {e}")
        return False

# === TELEGRAM BOT HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    username = user.username or "Unknown"
    first_name = user.first_name or "User"
    
    create_user(user_id, username, first_name)
    credits = get_user_credits(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("💳 Buy Credits", callback_data="buy")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 **Welcome {first_name}!**\n\n"
        f"💰 Credits: **{credits}**\n"
        f"📸 Send a photo to generate an image (costs 10 credits).\n\n"
        f"Commands:\n"
        f"/balance – Check your balance\n"
        f"/buy – Purchase credits\n"
        f"/stats – Global statistics",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    credits = get_user_credits(user_id)
    await update.message.reply_text(f"💰 Your balance: **{credits}** credits", parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users, total_gens, total_credits = get_stats()
    await update.message.reply_text(
        f"📊 **Global Stats**\n\n"
        f"👤 Users: **{total_users}**\n"
        f"🖼️ Generations: **{total_gens}**\n"
        f"💰 Credits in circulation: **{total_credits}**",
        parse_mode="Markdown"
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "💵 **Payment:** Paystack (Card, Bank Transfer, USSD)\n"
        "🔒 **Secure:** Paystack handles all payments.\n"
        "⏳ Credits added instantly after payment.\n\n"
        "⚠️ **Test mode:** Credits added directly.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data = query.data
    credits = int(data.split("_")[1])
    
    # Add credits directly (test mode)
    add_credits(user_id, credits)
    new_balance = get_user_credits(user_id)
    
    await query.edit_message_text(
        f"✅ **Payment Successful!**\n\n"
        f"Added **{credits}** credits.\n"
        f"New balance: **{new_balance}** credits.\n\n"
        f"Send a photo to start generating!",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "Unknown"
    
    # Check user exists
    user = get_user(user_id)
    if not user:
        create_user(user_id, username)
    
    credits = get_user_credits(user_id)
    
    if credits < 10:
        await update.message.reply_text(
            f"❌ **Insufficient credits!**\n\n"
            f"Balance: **{credits}** credits\n"
            f"Need **10 credits** per generation.\n"
            f"Use /buy to purchase more.",
            parse_mode="Markdown"
        )
        return
    
    # Get photo
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    image_data = base64.b64encode(file_bytes).decode('utf-8')
    
    # Create task
    task_id = f"task_{user_id}_{int(time.time())}"
    create_task(task_id, user_id, image_data)
    deduct_credits(user_id, 10)
    
    await update.message.reply_text(
        f"🔄 **Processing your image...**\n"
        f"⏳ Task ID: `{task_id}`\n"
        f"⏱️ Estimated time: 30 seconds\n\n"
        f"You will receive the result here.",
        parse_mode="Markdown"
    )
    
    # Spawn Colab worker
    success = spawn_colab_worker(task_id, user_id, image_data)
    
    if success:
        await update.message.reply_text("✅ Worker started! Progress updates will appear here.")
    else:
        update_task(task_id, "failed", "Failed to start worker")
        await update.message.reply_text("❌ Failed to start worker. Please try again later.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "balance":
        await balance_command(update, context)
    elif query.data == "stats":
        await stats_command(update, context)
    elif query.data == "buy":
        await buy_command(update, context)
    elif query.data.startswith("buy_"):
        await buy_callback(update, context)

def main():
    app = Application.builder().token(MANAGER_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("🚀 Manager Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
