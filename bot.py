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

def resize_image(image_bytes, max_width=1280, max_height=1280):
    img = Image.open(BytesIO(image_bytes))
    if img.width > max_width or img.height > max_height:
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        output = BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=85)
        return output.getvalue()
    return image_bytes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "Send me a photo and I'll process it on aiundress.cc\n"
        "Commands:\n"
        "/start_task - Visit aiundress.cc and get screenshot\n"
        "/stats - View your stats\n"
        "/help - Help"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photo – process it through aiundress.cc"""
    user_id = str(update.effective_user.id)
    photo = update.message.photo[-1]  # highest resolution
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    
    status_msg = await update.message.reply_text("🔄 Processing your image...")
    
    try:
        # Process the image
        result = await executor.process_image(bytes(file_bytes))
        
        if result["status"] == "success":
            image_data = base64.b64decode(result["image"])
            # Resize to be safe
            image_data = resize_image(image_data)
            
            # Store in user_data
            user_data[user_id] = {
                "last_process": time.time(),
                "result": result
            }
            
            await status_msg.edit_text("✅ Image processed successfully!")
            await update.message.reply_photo(
                photo=BytesIO(image_data),
                caption=f"✨ Here's your generated image\nSize: {len(image_data)//1024} KB"
            )
        else:
            # Check if error is about daily limit
            error_msg = result.get('error', 'Unknown error')
            if 'limit' in error_msg.lower() or 'cooldown' in error_msg.lower():
                await status_msg.edit_text(
                    f"⛔ {error_msg}\n\n"
                    "This might mean the site has detected repeated usage from the same fingerprint. "
                    "The bot rotates fingerprints every 24 hours, so please wait or try again later."
                )
            else:
                await status_msg.edit_text(f"❌ Processing failed: {error_msg}")
            
    except Exception as e:
        logger.error(f"Error processing photo for user {user_id}: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Keep old command for backward compatibility
    await update.message.reply_text("Please send me a photo to process, or use /help")

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
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logger.info("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
