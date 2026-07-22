
# ============================================
# FILE 3: colab_utils.py – Colab API Wrapper
# ============================================
import os
import time
import requests
import json
import subprocess

class ColabOrchestrator:
    def __init__(self):
        self.api_key = os.environ.get("COLAB_API_KEY")
        self.notebook_id = os.environ.get("COLAB_NOTEBOOK_ID")
        
    def spawn_worker(self, task_id, user_id, image_data_b64):
        """Spawn a Colab notebook with the task data."""
        try:
            # Method 1: Using google-colab-cli
            cmd = [
                "colab", "run",
                "--env", f"USER_ID={user_id}",
                "--env", f"TASK_ID={task_id}",
                "--env", f"IMAGE_DATA={image_data_b64}",
                "--env", f"BOT_TOKEN={os.environ.get('BOT_TOKEN')}",
                "worker_template.py"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except:
            # Method 2: Using Colab API (fallback)
            try:
                url = f"https://colab.research.google.com/notebooks/api/v1/execute?notebook_id={self.notebook_id}"
                payload = {
                    "params": {
                        "user_id": user_id,
                        "task_id": task_id,
                        "image_data": image_data_b64
                    }
                }
                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                return response.status_code == 200
            except:
                return False

    def delete_notebook(self, notebook_id):
        """Delete a temporary notebook after completion."""
        try:
            url = f"https://colab.research.google.com/notebooks/api/v1/delete?notebook_id={notebook_id}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.post(url, headers=headers, timeout=30)
            return response.status_code == 200
        except:
            return False
