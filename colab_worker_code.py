# This code runs inside the Colab notebook
import os
import sys
import time
import base64
import requests
from io import BytesIO
from supabase import create_client

user_id = os.environ.get("USER_ID")
task_id = os.environ.get("TASK_ID")
image_b64 = os.environ.get("IMAGE_DATA")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": user_id, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def send_photo(img_bytes):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {"photo": BytesIO(img_bytes)}
        data = {"chat_id": user_id, "caption": "✨ Here's your generated image!"}
        requests.post(url, files=files, data=data, timeout=10)
    except:
        pass

# Install dependencies (run once)
!pip install -q playwright supabase requests pillow
!playwright install chromium

# Import TaskExecutor
from task_executor import TaskExecutor

try:
    send_message("🔄 Step 1/4: Starting...")
    image_bytes = base64.b64decode(image_b64)
    executor = TaskExecutor()
    result = await executor.process_image_for_colab(user_id, image_bytes, BOT_TOKEN)
    if result:
        send_message("✅ Sending result...")
        send_photo(result)
        supabase.table("tasks").update({
            "status": "success",
            "result_image": base64.b64encode(result).decode(),
            "completed_at": "now()"
        }).eq("task_id", task_id).execute()
        send_message("✅ Done!")
    else:
        raise Exception("No result")
except Exception as e:
    error_msg = str(e)[:200]
    send_message(f"❌ Error: {error_msg}")
    supabase.table("tasks").update({
        "status": "failed",
        "error": error_msg,
        "completed_at": "now()"
    }).eq("task_id", task_id).execute()

sys.exit(0)
