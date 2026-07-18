import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from donut_manager import DonutManager
from task_executor import TaskExecutor

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Initialize managers
donut = DonutManager()
executor = TaskExecutor(donut)

# Track user tasks (in production, use a database)
user_tasks = {}
user_cooldowns = {}

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    welcome_message = f"""
👋 Welcome {user.first_name}!

I'm a task automation bot powered by Donut Browser.
I can perform automated tasks without getting detected.

Available commands:
/start - Show this message
/start_task - Start a new task
/stats - Check your usage stats
/help - Get help

⚡ Tasks run in under 5 minutes!
    """
    await update.message.reply_text(welcome_message)

async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start_task command"""
    user_id = str(update.effective_user.id)
    current_time = datetime.now()
    
    # Check cooldown (24 hours)
    if user_id in user_cooldowns:
        last_used = user_cooldowns[user_id]
        hours_since = (current_time - last_used).total_seconds() / 3600
        if hours_since < 24:
            remaining = 24 - hours_since
            await update.message.reply_text(
                f"⏳ Please wait {remaining:.1f} hours before starting another task."
            )
            return
    
    # Send processing message
    status_msg = await update.message.reply_text("🔄 Starting task... Please wait.")
    
    try:
        # Step 1: Create Donut profile
        await status_msg.edit_text("🔄 Creating browser profile...")
        profile_id = donut.create_profile(f"user_{user_id}")
        
        # Step 2: Launch Donut browser
        await status_msg.edit_text("🔄 Launching browser...")
        cdp_port = donut.launch_profile(profile_id)
        
        # Step 3: Execute the task
        await status_msg.edit_text("🔄 Executing task...")
        result = await executor.run_task(cdp_port, user_id)
        
        # Step 4: Save result
        user_tasks[user_id] = {
            "profile_id": profile_id,
            "result": result,
            "timestamp": current_time.isoformat()
        }
        user_cooldowns[user_id] = current_time
        
        # Step 5: Send success
        await status_msg.edit_text(
            f"✅ Task completed successfully!\n\n"
            f"📊 Result: {result}\n"
            f"🕐 Duration: ~{result.get('duration', 'unknown')}"
        )
        
    except Exception as e:
        logger.error(f"Error in start_task for user {user_id}: {str(e)}")
        await status_msg.edit_text(
            f"❌ Error: {str(e)}\n\n"
            "Please try again later or contact support."
        )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    user_id = str(update.effective_user.id)
    
    if user_id not in user_tasks:
        await update.message.reply_text("📊 You haven't completed any tasks yet.")
        return
    
    task_data = user_tasks[user_id]
    last_run = task_data.get("timestamp", "Never")
    
    stats_message = f"""
📊 Your Usage Stats

✅ Last task: {task_data.get('result', 'N/A')}
📅 Last run: {last_run}
🔢 Total tasks: {len(user_tasks)}
⏳ Cooldown: {'Active' if user_id in user_cooldowns else 'Ready'}

💡 You can run another task in 24 hours.
    """
    await update.message.reply_text(stats_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🤖 Task Automation Bot

How it works:
1. Send /start_task to begin
2. Bot creates a unique browser profile
3. Automates the task without detection
4. Returns result within 5 minutes

Limits:
• 1 task per 24 hours per user
• Tasks complete in < 5 minutes
• Uses advanced anti-detection (Donut Browser)

Need support? Contact @your_support
    """
    await update.message.reply_text(help_text)

# ==================== MAIN ====================

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_task", start_task))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_command))
    
    # Start bot
    logger.info("Bot started! 🚀")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()