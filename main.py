import os
import logging
import time
import base64
import threading
import requests
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
USDT_WALLET = os.environ.get("USDT_WALLET")
COLAB_NOTEBOOK_IDS = os.environ.get("COLAB_NOTEBOOK_IDS", "").split(",")
COLAB_NOTEBOOK_IDS = [n.strip() for n in COLAB_NOTEBOOK_IDS if n.strip()]
MAX_ACTIVE_TASKS = int(os.environ.get("MAX_ACTIVE_TASKS", 5))
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID", "")  # set this to your Telegram ID

# Fallback (optional)
if not SUPABASE_URL:
    SUPABASE_URL = "https://nidptbrkgxjnupqpqakt.supabase.co"
if not SUPABASE_KEY:
    SUPABASE_KEY = "sb_publishable_G93jIOS4WBZBCqwGYyj4og_J9roWaDs"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === CREDIT PACKAGES ===
CREDIT_PACKAGES = {10: 100, 25: 300, 50: 650, 100: 1400}

# === DATABASE HELPERS ===
def get_user(user_id):
    res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None

def create_user(user_id, username, first_name):
    data = {
        "user_id": user_id,
        "username": username or "Unknown",
        "first_name": first_name or "User",
        "credits": 0,
    }
    supabase.table("users").insert(data).execute()

def get_credits(user_id):
    user = get_user(user_id)
    return user["credits"] if user else 0

def add_credits(user_id, amount):
    user = get_user(user_id)
    if not user:
        return None
    new_balance = user["credits"] + amount
    supabase.table("users").update({"credits": new_balance}).eq("user_id", user_id).execute()
    return new_balance

def deduct_credits(user_id, amount=10):
    user = get_user(user_id)
    if not user or user["credits"] < amount:
        return False
    new_balance = user["credits"] - amount
    supabase.table("users").update({"credits": new_balance}).eq("user_id", user_id).execute()
    return True

def add_transaction(user_id, amount, description):
    data = {
        "user_id": user_id,
        "amount": amount,
        "type": "purchase" if amount > 0 else "usage",
        "description": description,
    }
    supabase.table("transactions").insert(data).execute()

def create_task(user_id, task_id, image_b64):
    data = {
        "task_id": task_id,
        "user_id": user_id,
        "status": "pending",
        "image_data": image_b64,
    }
    supabase.table("tasks").insert(data).execute()

def update_task(task_id, status, result_image=None, error=None):
    update_data = {"status": status}
    if result_image:
        update_data["result_image"] = result_image
    if error:
        update_data["error"] = error
    if status in ("success", "failed"):
        update_data["completed_at"] = "now()"
    supabase.table("tasks").update(update_data).eq("task_id", task_id).execute()

# === PAYMENT VERIFICATION ===
def verify_usdt_transaction(tx_id):
    url = f"https://api.trongrid.io/v1/transactions/{tx_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return False, None, None
        data = resp.json()
        txs = data.get("data", [])
        if not txs:
            return False, None, None
        events_url = f"https://api.trongrid.io/v1/transactions/{tx_id}/events"
        events_resp = requests.get(events_url, timeout=10)
        if events_resp.status_code != 200:
            return False, None, None
        for event in events_resp.json().get("data", []):
            if (event.get("event_name") == "Transfer" and
                event.get("contract_address") == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"):
                result = event.get("result", {})
                to = result.get("to")
                if to and to.lower() == USDT_WALLET.lower():
                    value = int(result.get("value", 0)) / 10**6
                    return True, value, result.get("from")
        return False, None, None
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return False, None, None

# === COLAB SPAWNER (Multi‑Notebook) ===
def spawn_colab(task_id, user_id, image_b64):
    if not COLAB_NOTEBOOK_IDS:
        logger.error("❌ No Colab notebook IDs configured!")
        return False
    notebook_id = random.choice(COLAB_NOTEBOOK_IDS)
    url = f"https://colab.research.google.com/notebooks/api/v1/execute?notebook_id={notebook_id}"
    payload = {
        "params": {
            "USER_ID": user_id,
            "TASK_ID": task_id,
            "IMAGE_DATA": image_b64,
            "BOT_TOKEN": BOT_TOKEN,
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_KEY": SUPABASE_KEY,
        }
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            logger.info(f"✅ Colab started for task {task_id} using {notebook_id}")
            return True
        else:
            logger.error(f"Colab error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Colab spawn failed: {e}")
        return False

# === CONTROLLER THREAD ===
def controller_loop():
    while True:
        try:
            # Count active tasks
            active = supabase.table("tasks")\
                .select("task_id", count="exact")\
                .eq("status", "processing")\
                .execute()
            if active.count and active.count >= MAX_ACTIVE_TASKS:
                time.sleep(2)
                continue

            # Get oldest pending task
            resp = supabase.table("tasks")\
                .select("*")\
                .eq("status", "pending")\
                .order("created_at")\
                .limit(1)\
                .execute()
            tasks = resp.data
            if not tasks:
                time.sleep(2)
                continue

            task = tasks[0]
            task_id = task["task_id"]
            user_id = task["user_id"]
            image_b64 = task["image_data"]

            # Atomically set to processing
            updated = supabase.table("tasks")\
                .update({"status": "processing", "started_at": "now()"})\
                .eq("task_id", task_id)\
                .eq("status", "pending")\
                .execute()
            if not updated.data:
                continue

            success = spawn_colab(task_id, user_id, image_b64)
            if not success:
                supabase.table("tasks")\
                    .update({"status": "pending"})\
                    .eq("task_id", task_id)\
                    .execute()
                logger.warning(f"Retrying task {task_id}")
        except Exception as e:
            logger.error(f"Controller error: {e}")
            time.sleep(5)

# === STALE TASK RECOVERY ===
def stale_recovery_loop():
    while True:
        try:
            stale_time = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            supabase.table("tasks")\
                .update({"status": "pending", "retry_count": supabase.raw("retry_count + 1")})\
                .eq("status", "processing")\
                .lt("started_at", stale_time)\
                .execute()
            time.sleep(120)
        except Exception as e:
            logger.error(f"Stale recovery error: {e}")
            time.sleep(120)

# === TELEGRAM HANDLERS ===
async def start(update: Update, context):
    user = update.effective_user
    user_id = str(user.id)
    if not get_user(user_id):
        create_user(user_id, user.username, user.first_name)
    credits = get_credits(user_id)
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n"
        f"💰 Balance: {credits} credits.\n"
        f"Send a photo (costs 10 credits).\n"
        f"Commands: /balance, /buy, /help"
    )

async def balance(update: Update, context):
    user_id = str(update.effective_user.id)
    credits = get_credits(user_id)
    await update.message.reply_text(f"💰 Your balance: {credits} credits.")

async def buy(update: Update, context):
    message = "💳 *Buy Credits with USDT (TRC20)*\n\n"
    message += f"Send USDT to this address:\n`{USDT_WALLET}`\n\n"
    message += "Packages:\n"
    for usdt, credits in CREDIT_PACKAGES.items():
        message += f"• {usdt} USDT → **{credits}** credits\n"
    message += "\nAfter sending, type `/confirm <transaction_id>`\n"
    await update.message.reply_text(message, parse_mode="Markdown")

async def confirm(update: Update, context):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /confirm <transaction_id>")
        return
    tx_id = context.args[0].strip()
    # Check if already processed
    existing = supabase.table("transactions")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("description", tx_id)\
        .execute()
    if existing.data:
        await update.message.reply_text("❌ This transaction has already been confirmed.")
        return
    valid, amount, _ = verify_usdt_transaction(tx_id)
    if not valid:
        await update.message.reply_text("❌ Transaction not found or not sent to our wallet.")
        return
    matched = None
    for pkg, credits in CREDIT_PACKAGES.items():
        if abs(amount - pkg) < 0.01:
            matched = credits
            break
    if not matched:
        await update.message.reply_text(f"⚠️ Amount {amount:.2f} USDT doesn't match any package.")
        return
    new_balance = add_credits(user_id, matched)
    add_transaction(user_id, matched, f"Crypto payment: {tx_id}")
    await update.message.reply_text(
        f"✅ Payment confirmed!\nAdded **{matched}** credits.\n"
        f"New balance: **{new_balance}** credits."
    )

async def addcredits(update: Update, context):
    """Test command: add credits without payment."""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /addcredits <amount>")
        return
    try:
        amount = int(context.args[0])
        new_balance = add_credits(user_id, amount)
        add_transaction(user_id, amount, f"Test add: {amount} credits")
        await update.message.reply_text(f"✅ Added {amount} credits. New balance: {new_balance}.")
    except ValueError:
        await update.message.reply_text("Invalid amount.")

async def reset(update: Update, context):
    """Test command: reset user credits to 0."""
    user_id = str(update.effective_user.id)
    supabase.table("users").update({"credits": 0}).eq("user_id", user_id).execute()
    await update.message.reply_text("✅ Credits reset to 0.")

async def handle_photo(update: Update, context):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    credits = user["credits"]
    if credits < 10:
        await update.message.reply_text("❌ Insufficient credits. Use /buy.")
        return
    # Download photo
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    image_b64 = base64.b64encode(file_bytes).decode('utf-8')
    # Deduct credits
    if not deduct_credits(user_id, 10):
        await update.message.reply_text("❌ Insufficient credits.")
        return
    # Create task
    task_id = f"task_{user_id}_{int(time.time())}"
    create_task(user_id, task_id, image_b64)
    add_transaction(user_id, -10, f"Generation {task_id}")
    await update.message.reply_text(
        f"✅ Task created: `{task_id}`\n⏳ Estimated 30 seconds.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context):
    await update.message.reply_text(
        "/start - Welcome\n"
        "/balance - Check credits\n"
        "/buy - Buy credits (USDT)\n"
        "/confirm <txid> - Confirm payment\n"
        "/addcredits <amount> - Test mode\n"
        "/reset - Test mode\n"
        "/help - This message"
    )

# === ADMIN COMMANDS (only for ADMIN_USER_ID) ===
async def stats(update: Update, context):
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    users = supabase.table("users").select("*", count="exact").execute()
    tasks = supabase.table("tasks").select("*", count="exact").execute()
    total_users = users.count or 0
    total_tasks = tasks.count or 0
    # Sum credits
    credits_resp = supabase.table("users").select("credits").execute()
    total_credits = sum([u["credits"] for u in credits_resp.data]) if credits_resp.data else 0
    await update.message.reply_text(
        f"📊 **Admin Stats**\n"
        f"👤 Users: {total_users}\n"
        f"📋 Tasks: {total_tasks}\n"
        f"💰 Total Credits: {total_credits}\n"
        f"💵 USDT Wallet: `{USDT_WALLET}`"
    )

# === MAIN ===
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    # Start threads
    threading.Thread(target=controller_loop, daemon=True).start()
    threading.Thread(target=stale_recovery_loop, daemon=True).start()
    # Bot app
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("addcredits", addcredits))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))  # admin only
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    logger.info("✅ Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
