import json
import logging
import base64
import time
import hashlib
import random
import re
from pathlib import Path
from urllib.parse import urlparse
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

    def _normalize_url(self, url):
        url = url.strip()
        if not url:
            return None
        if not url.startswith(('http://', 'https://')):
            parsed = urlparse('//' + url)
            if not parsed.netloc:
                return None
            return 'https://' + parsed.netloc
        return url

    async def visit_and_screenshot(self, url: str) -> dict:
        # kept for backward compatibility
        target_url = self._normalize_url(url)
        if not target_url:
            return {"status": "error", "error": "Invalid URL"}

        fp = self._get_available_fingerprint()
        proxy = None

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
                await page.goto(target_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)
                screenshot_bytes = await page.screenshot(full_page=True)
                title = await page.title()
                await browser.close()
                return {
                    "status": "success",
                    "screenshot": base64.b64encode(screenshot_bytes).decode(),
                    "title": title,
                    "url": target_url,
                    "size": len(screenshot_bytes)
                }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def process_image(self, image_bytes: bytes) -> dict:
        """
        Upload an image to aiundress.cc, generate, and return the result image.
        Includes debug logging and detection of daily limit / cooldown.
        """
        target_url = "https://aiundress.cc"
        fp = self._get_available_fingerprint()
        proxy = None

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
                logger.info("🌐 Navigating to upload page")
                await page.goto(target_url, wait_until="networkidle", timeout=30000)

                # ---- Debug: page title and URL ----
                logger.info(f"Page title: {await page.title()}")
                logger.info(f"Page URL: {page.url}")

                # ---- Check for cooldown / limit message BEFORE upload ----
                page_text = await page.content()
                if re.search(r'(limit|cooldown|try again|wait|minutes|hours|daily)', page_text, re.I):
                    logger.warning("⚠️ Cooldown/limit detected on page load – maybe fingerprint already used?")
                    # We'll still proceed, but if generation fails we'll report it.

                # ---- Upload the image ----
                file_input = page.locator('input[type="file"]').first
                if await file_input.count() == 0:
                    logger.error("❌ No file input found")
                    raise Exception("No file input found on the page.")

                logger.info("📤 Uploading image...")
                await file_input.set_input_files(files=[("image.jpg", image_bytes, "image/jpeg")])

                # ---- Click generate button ----
                generate_btn = page.locator('button:has-text("Generate"), button:has-text("Start"), button:has-text("Process"), input[type="submit"][value*="Generate"]').first
                if await generate_btn.count() == 0:
                    generate_btn = page.locator('div[role="button"]:has-text("Generate")').first
                if await generate_btn.count() == 0:
                    logger.error("❌ No generate button found")
                    raise Exception("No generate button found")

                logger.info("🔄 Clicking generate button...")
                await generate_btn.click()

                # ---- Wait for generation and check for cooldown/limit ----
                # Wait a few seconds for any messages to appear
                await page.wait_for_timeout(3000)

                # Check for limit/cooldown message on the page
                page_text = await page.content()
                if re.search(r'(limit|cooldown|try again|wait|minutes|hours|daily)', page_text, re.I):
                    logger.warning("🚫 Cooldown/limit detected after generation – fingerprint may have been used before.")
                    # Return a specific error so we can report it in the bot
                    await browser.close()
                    return {
                        "status": "error",
                        "error": "Daily limit reached. The site is asking to wait. Fingerprint may not have been rotated properly or you've hit the limit for this fingerprint."
                    }

                # ---- Wait for result image ----
                result_img = page.locator('img[class*="result"], img[class*="output"], img[class*="generated"], div.result img, div.output img').first
                if await result_img.count() == 0:
                    # Fallback: wait for any image that appears after generation
                    logger.info("⏳ Waiting for result image to appear...")
                    # Wait for new images to load (we can wait for network idle and then look for image elements)
                    await page.wait_for_timeout(5000)
                    all_images = await page.locator('img').all()
                    # Heuristic: find an image with a data URL or blob URL
                    candidate = None
                    for img in all_images:
                        src = await img.get_attribute('src')
                        if src and (src.startswith('data:image') or 'blob:' in src or 'generated' in src):
                            candidate = img
                            break
                    if not candidate:
                        # If still no image, we fall back to full-page screenshot
                        logger.warning("ℹ️ No result image found, falling back to full-page screenshot")
                        screenshot_bytes = await page.screenshot(full_page=True)
                        await browser.close()
                        return {
                            "status": "success",
                            "image": base64.b64encode(screenshot_bytes).decode(),
                            "method": "screenshot_fallback",
                            "size": len(screenshot_bytes)
                        }
                    result_img = candidate

                # Get the image source
                src = await result_img.get_attribute('src')
                if not src:
                    logger.warning("ℹ️ Result image has no src, using screenshot fallback")
                    screenshot_bytes = await page.screenshot(full_page=True)
                    await browser.close()
                    return {
                        "status": "success",
                        "image": base64.b64encode(screenshot_bytes).decode(),
                        "method": "screenshot_fallback",
                        "size": len(screenshot_bytes)
                    }

                # Download the image
                if src.startswith('data:'):
                    m = re.match(r'data:image/([a-zA-Z]+);base64,([A-Za-z0-9+/=]+)', src)
                    if m:
                        image_data = base64.b64decode(m.group(2))
                    else:
                        raise Exception("Cannot decode data URL")
                else:
                    # It's a URL – fetch it using aiohttp
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(src) as resp:
                            if resp.status != 200:
                                raise Exception(f"Failed to download image: {resp.status}")
                            image_data = await resp.read()

                await browser.close()
                logger.info(f"✅ Image downloaded, size: {len(image_data)} bytes")
                return {
                    "status": "success",
                    "image": base64.b64encode(image_data).decode(),
                    "method": "downloaded",
                    "size": len(image_data)
                }

        except Exception as e:
            logger.error(f"❌ Error processing image: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
