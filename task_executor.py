import json
import logging
import base64
import time
import hashlib
import random
from pathlib import Path
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self,
                 used_file="used_fingerprints.json",
                 proxies_file="proxies.txt",
                 cooldown_seconds=86400):
        self.cooldown_seconds = cooldown_seconds
        self.used_file = Path(used_file)
        self.proxies = self._load_proxies(proxies_file)
        self.fp_gen = FingerprintGenerator()

    def _load_proxies(self, file_path):
        proxies = []
        if Path(file_path).exists():
            with open(file_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        proxies.append(line)
        return proxies

    def _load_used(self):
        if self.used_file.exists():
            with open(self.used_file) as f:
                return json.load(f)
        return {}

    def _save_used(self, used):
        with open(self.used_file, 'w') as f:
            json.dump(used, f, indent=2)

    def _get_fingerprint_hash(self, fp):
        ua = getattr(fp, 'user_agent', '') or getattr(fp, 'userAgent', '')
        width = getattr(fp.screen_resolution, 'width', 0) if hasattr(fp, 'screen_resolution') else 0
        height = getattr(fp.screen_resolution, 'height', 0) if hasattr(fp, 'screen_resolution') else 0
        locale = getattr(fp, 'locale', '') or getattr(fp, 'language', '')
        tz = getattr(fp, 'timezone', '') or getattr(fp, 'timezone_id', '')
        key = f"{ua}|{width}x{height}|{locale}|{tz}"
        return hashlib.sha256(key.encode()).hexdigest()

    def _get_available_fingerprint(self):
        used = self._load_used()
        now = time.time()
        for _ in range(100):
            fp = self.fp_gen.get_fingerprint()
            fhash = self._get_fingerprint_hash(fp)
            if fhash not in used or (now - used[fhash]) > self.cooldown_seconds:
                used[fhash] = now
                self._save_used(used)
                return fp
        now = time.time()
        used = {k: v for k, v in used.items() if (now - v) <= self.cooldown_seconds}
        self._save_used(used)
        return self._get_available_fingerprint()

    async def visit_and_screenshot(self, url: str) -> dict:
        fp = self._get_available_fingerprint()
        proxy = None
        if self.proxies:
            proxy = {"server": random.choice(self.proxies)}

        try:
            ua = getattr(fp, 'user_agent', '') or getattr(fp, 'userAgent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            width = getattr(fp.screen_resolution, 'width', 1920) if hasattr(fp, 'screen_resolution') else 1920
            height = getattr(fp.screen_resolution, 'height', 1080) if hasattr(fp, 'screen_resolution') else 1080
            locale = getattr(fp, 'locale', 'en-US') or getattr(fp, 'language', 'en-US')
            tz = getattr(fp, 'timezone', 'America/New_York') or getattr(fp, 'timezone_id', 'America/New_York')

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu"],
                    proxy=proxy
                )
                context = await browser.new_context(
                    user_agent=ua,
                    viewport={"width": width, "height": height},
                    locale=locale,
                    timezone_id=tz,
                )
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)
                screenshot_bytes = await page.screenshot(full_page=True)
                title = await page.title()
                await browser.close()
                return {
                    "status": "success",
                    "screenshot": base64.b64encode(screenshot_bytes).decode(),
                    "title": title,
                    "url": url,
                    "size": len(screenshot_bytes)
                }
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return {"status": "error", "error": str(e)}
