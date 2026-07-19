import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from task_executor import TaskExecutor

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
executor = TaskExecutor()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    status = await update.message.reply_text("🔄 Starting...")
    try:
        await executor.process_photo(update, bytes(file_bytes))
        await status.delete()
    except Exception as e:
        logger.error(e, exc_info=True)
        await status.edit_text(f"❌ Error: {str(e)}")

async def start(update: Update, context):
    await update.message.reply_text("Send me a photo, I'll process it step by step on aiundress.cc and send screenshots.")

def main():
    if not BOT_TOKEN:
        logger.error("Missing BOT_TOKEN")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
