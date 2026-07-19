import os
import logging
import base64
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from task_executor import TaskExecutor

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
executor = TaskExecutor()

def resize_image(image_bytes, max_dim=1280):
    img = Image.open(BytesIO(image_bytes))
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=85)
        return out.getvalue()
    return image_bytes

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    status = await update.message.reply_text("🔄 Uploading...")
    try:
        result = await executor.upload_and_screenshot(bytes(file_bytes))
        if result["status"] == "success":
            img = base64.b64decode(result["screenshot"])
            img = resize_image(img)
            await status.delete()
            await update.message.reply_photo(photo=BytesIO(img), caption="✅ Upload successful – page screenshot")
        else:
            await status.edit_text(f"❌ {result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.error(e, exc_info=True)
        await status.edit_text(f"❌ Error: {str(e)}")

async def start(update: Update, context):
    await update.message.reply_text("Send me a photo, I'll upload it to aiundress.cc and send a screenshot of the page.")

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
