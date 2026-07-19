import os
import logging
import time
import base64
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from task_executor import TaskExecutor

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

executor = TaskExecutor()
user_data = {}

def resize_image(image_bytes, max_width=1280, max_height=1280):
    """Resize image to fit within max dimensions, maintain aspect ratio"""
    img = Image.open(BytesIO(image_bytes))
    if img.width > max_width or img.height > max_height:
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        output = BytesIO()
        # Save as JPEG to reduce size, use quality 85
        img.convert("RGB").save(output, format="JPEG", quality=85)
        return output.getvalue()
    return image_bytes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "Commands:\n"
        "/start_task - Visit aiundress.cc and get screenshot\n"
        "/stats - View your stats\n"
        "/help - Help"
    )

async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    status_msg = await update.message.reply_text("🔄 Starting task...")
    
    try:
        await status_msg.edit_text("🔄 Visiting aiundress.cc...")
        result = await executor.visit_and_screenshot("aiundress.cc")
        
        if result["status"] == "success":
            screenshot_data = base64.b64decode(result["screenshot"])
            # Resize if needed
            screenshot_data = resize_image(screenshot_data)
            user_data[user_id] = {
                "result": result,
                "timestamp": time.time()
            }
            
            await status_msg.edit_text(
                f"✅ Task completed!\n"
                f"📄 Title: {result['title']}\n"
                f"📸 Size: {len(screenshot_data) // 1024} KB\n"
                f"🔗 URL: {result['url']}"
            )
            
            await update.message.reply_photo(
                photo=BytesIO(screenshot_data),
                caption=f"📸 Screenshot of {result['url']}"
            )
        else:
            await status_msg.edit_text(f"❌ Task failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error in start_task for user {user_id}: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in user_data:
        await update.message.reply_text("📊 No tasks completed yet.")
        return
    data = user_data[user_id]
    await update.message.reply_text(
        f"📊 Your Stats:\n"
        f"✅ Last task: {data['result'].get('title', 'N/A')}\n"
        f"🕐 Completed: {time.ctime(data['timestamp'])}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Task Automation Bot\n\n"
        "Commands:\n"
        "/start - Welcome\n"
        "/start_task - Visit aiundress.cc\n"
        "/stats - View stats\n"
        "/help - Help\n\n"
        "⚠️ Uses fingerprint rotation for anti-detection"
    )

def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    
    logger.info("🚀 Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_task", start_task))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
