import os
import logging
import time
import base64
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from task_executor import TaskExecutor

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
executor = TaskExecutor()
user_data = {}

def resize_image(image_bytes, max_dim=1280):
    img = Image.open(BytesIO(image_bytes))
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=85)
        return out.getvalue()
    return image_bytes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "Send me a photo and I'll process it on aiundress.cc\n"
        "Commands:\n"
        "/start - Welcome\n"
        "/stats - View your stats\n"
        "/help - Help\n"
        "/stop - Stop the bot (exit the workflow)"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gracefully stop the bot and exit the process."""
    await update.message.reply_text("🛑 Bot is stopping... Goodbye!")
    logger.info("Stopping bot via /stop command")
    # Exit the process to stop the workflow
    os._exit(0)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    status_msg = await update.message.reply_text("🔄 Processing your image...")
    try:
        await executor.process_photo(update, bytes(file_bytes))
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Error processing photo for user {user_id}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in user_data:
        await update.message.reply_text("📊 No tasks processed yet.")
        return
    data = user_data[user_id]
    await update.message.reply_text(
        f"📊 Your Stats:\n"
        f"✅ Last processed: {time.ctime(data['last_process'])}\n"
        f"📸 Result size: {data['result'].get('size', 0)//1024} KB"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Task Automation Bot\n\n"
        "Send me a photo and I'll upload it to aiundress.cc and return the generated image.\n"
        "Commands:\n"
        "/start - Welcome\n"
        "/stats - View stats\n"
        "/help - Help\n"
        "/stop - Stop the bot (exit the workflow)"
    )

def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    logger.info("🚀 Bot started. Send a photo or use /stop to exit.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
