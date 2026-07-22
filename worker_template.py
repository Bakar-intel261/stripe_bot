
# ============================================
# FILE 2: worker_template.py – Colab Worker
# ============================================
# This code gets injected into the temporary Colab notebook
import os
import sys
import time
import base64
import requests
from io import BytesIO

# === TASK DATA (injected by manager) ===
user_id = os.environ.get("USER_ID")
task_id = os.environ.get("TASK_ID")
image_data_b64 = os.environ.get("IMAGE_DATA")  # base64 encoded image
manager_url = os.environ.get("MANAGER_URL", "https://your-manager.com")

# === TELEGRAM BOT TOKEN ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def send_progress(message):
    """Send progress update to user via Telegram."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": user_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except:
        pass

def send_result(image_bytes):
    """Send the generated image to the user."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {"photo": BytesIO(image_bytes)}
        data = {"chat_id": user_id, "caption": "✨ Here's your generated image!"}
        requests.post(url, files=files, data=data)
    except:
        pass

def report_completion(status, credits_used=10):
    """Report completion back to the manager."""
    try:
        url = f"{manager_url}/complete"
        payload = {"task_id": task_id, "status": status, "credits_used": credits_used}
        requests.post(url, json=payload)
    except:
        pass

try:
    send_progress("🔄 **Step 1/4:** Decoding your image...")
    
    # Decode image
    image_bytes = base64.b64decode(image_data_b64)
    
    send_progress("🔄 **Step 2/4:** Uploading to AI service...")
    
    # === IMPORT: Use your existing task_executor logic ===
    from task_executor import TaskExecutor
    executor = TaskExecutor()
    
    # Process the image
    send_progress("🔄 **Step 3/4:** Generating... (this takes ~20 seconds)")
    
    result = asyncio.run(executor.process_photo(user_id, image_bytes))
    
    if result["status"] == "success":
        image_data = base64.b64decode(result["image"])
        send_progress("✅ **Step 4/4:** Sending your image...")
        send_result(image_data)
        report_completion("success")
        send_progress("✅ **Done!** Image generated and sent.")
    else:
        error = result.get("error", "Unknown error")
        send_progress(f"❌ **Generation failed:** {error}")
        report_completion("failed")
        
except Exception as e:
    error_msg = str(e)[:200]
    send_progress(f"❌ **Error:** {error_msg}")
    report_completion("failed")

# === SELF-TERMINATE ===
os._exit(0)
