# ============================================
# FILE 2: worker_template.py
# ============================================
import os
import sys
import time
import base64
import requests
import asyncio
from io import BytesIO
from datetime import datetime

# === ENVIRONMENT VARIABLES ===
user_id = os.environ.get("USER_ID")
task_id = os.environ.get("TASK_ID")
image_data_b64 = os.environ.get("IMAGE_DATA")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# === TELEGRAM ===
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": user_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Send message failed: {e}")

def send_telegram_photo(image_bytes):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {"photo": BytesIO(image_bytes)}
        data = {"chat_id": user_id, "caption": "✨ Here's your generated image!"}
        requests.post(url, files=files, data=data, timeout=30)
    except Exception as e:
        print(f"Send photo failed: {e}")

# === SUPABASE ===
def supabase_update_task(status, error=None):
    try:
        url = f"{SUPABASE_URL}/rest/v1/tasks?task_id=eq.{task_id}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        data = {"status": status, "completed_at": datetime.now().isoformat()}
        if error:
            data["error"] = error
        requests.patch(url, json=data, headers=headers, timeout=10)
    except Exception as e:
        print(f"Supabase update failed: {e}")

def supabase_add_generation(status, credits_used=10):
    try:
        url = f"{SUPABASE_URL}/rest/v1/generations"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "user_id": user_id,
            "task_id": task_id,
            "status": status,
            "credits_used": credits_used,
            "created_at": datetime.now().isoformat()
        }
        requests.post(url, json=data, headers=headers, timeout=10)
    except Exception as e:
        print(f"Add generation failed: {e}")

# === MAIN ===
try:
    send_telegram_message("🔄 **Step 1/4:** Starting image generation...")
    
    # Decode image
    image_bytes = base64.b64decode(image_data_b64)
    
    send_telegram_message("🔄 **Step 2/4:** Uploading to AI service...")
    
    # Import and run the Donut logic
    from task_executor import TaskExecutor
    executor = TaskExecutor()
    
    send_telegram_message("🔄 **Step 3/4:** Generating... (~20 seconds)")
    
    # Run the processor
    result = asyncio.run(executor.process_photo(user_id, image_bytes))
    
    if result["status"] == "success":
        image_data = base64.b64decode(result["image"])
        send_telegram_message("✅ **Step 4/4:** Sending your image...")
        send_telegram_photo(image_data)
        supabase_update_task("success")
        supabase_add_generation("success", 10)
        send_telegram_message("✅ **Done!** Image generated and sent.")
    else:
        error = result.get("error", "Unknown error")
        send_telegram_message(f"❌ **Generation failed:** {error}")
        supabase_update_task("failed", error)
        supabase_add_generation("failed", 0)
        
except Exception as e:
    error_msg = str(e)[:200]
    send_telegram_message(f"❌ **Error:** {error_msg}")
    supabase_update_task("failed", error_msg)
    supabase_add_generation("failed", 0)

# === SELF-TERMINATE ===
sys.exit(0)
