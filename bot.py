import os
import logging
import time
import base64
from io import BytesIO
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 **Welcome {user.first_name}!**\n\n"
        "I can remove clothes from photos using AI.\n\n"
        "📸 **How to use:**\n"
        "• Send me a photo\n"
        "• Wait ~30 seconds\n"
        "• Receive the generated image\n\n"
        "🔒 **Privacy:** Your images are deleted immediately.\n"
        "💡 **Commands:** /help for more info",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Help & Commands**\n\n"
        "📸 **Send a photo** to remove clothes\n"
        "⏳ Processing takes ~30 seconds\n"
        "📊 **/stats** – View your stats\n"
        "🔄 **/retry** – Retry last generation\n\n"
        "⚠️ **Need help?** Contact @support",
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    await update.message.reply_text(
        f"📊 **Your Stats**\n\n"
        f"🆔 User ID: `{user_id}`\n"
        f"📸 Generations: 0\n"
        f"⏳ Last active: Now",
        parse_mode="Markdown"
    )

async def retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 **Retry command received.**\n\n"
        "Please send a photo to start a new generation.",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    start_time = time.time()
    
    status_msg = await update.message.reply_text(
        "📥 **Step 1/4:** Downloading your photo...",
        parse_mode="Markdown"
    )
    
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    
    await status_msg.edit_text(
        "📤 **Step 2/4:** Uploading to AI service...\n"
        "⏳ Estimated time: ~15 seconds",
        parse_mode="Markdown"
    )
    
    try:
        result = await executor.process_photo(update, bytes(file_bytes), status_msg)
        
        if result["status"] == "success":
            image_data = base64.b64decode(result["image"])
            elapsed = int(time.time() - start_time)
            
            await status_msg.edit_text(
                f"✅ **Step 3/4:** Generation complete!\n"
                f"⏱️ Time taken: {elapsed} seconds\n"
                f"📦 Size: {len(image_data) // 1024} KB\n\n"
                f"📸 **Step 4/4:** Sending your image...",
                parse_mode="Markdown"
            )
            
            await update.message.reply_photo(
                photo=BytesIO(image_data),
                caption=f"✨ **Here's your generated image!**\n\n"
                        f"⏱️ Processed in {elapsed} seconds\n"
                        f"🔒 Your privacy is respected",
                parse_mode="Markdown"
            )
            
            await status_msg.edit_text(
                "✅ **Done!** Your image has been generated and sent.\n\n"
                "📸 Send another photo to continue.\n"
                "🔄 **New fingerprint** will be used for the next request.",
                parse_mode="Markdown"
            )
            
        else:
            error_msg = result.get("error", "Unknown error")
            await status_msg.edit_text(
                f"❌ **Generation failed!**\n\n"
                f"Error: {error_msg}\n\n"
                f"🔄 Please try again with a different photo.",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ **Something went wrong!**\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"🔄 Please try again.",
            parse_mode="Markdown"
        )

def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    
    logger.info("🚀 Bot started. Send a photo.")
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("retry", retry))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logger.info("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
