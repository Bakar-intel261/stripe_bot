import logging
import base64
import asyncio
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()

    def _resize_image(self, image_bytes, max_dim=1280):
        img = Image.open(BytesIO(image_bytes))
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            out = BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=90)
            return out.getvalue()
        return image_bytes

    async def process_photo(self, update, image_bytes):
        target_url = "https://aiundress.cc"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        width = 1920
        height = 1080

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(user_agent=ua, viewport={"width": width, "height": height})
            page = await context.new_page()

            # ---- Step 1: Landing ----
            logger.info("🌐 Navigating to upload page")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="🌐 Landing page")

            # ---- Step 2: Upload ----
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() == 0:
                raise Exception("No file input found")
            logger.info("📤 Uploading image...")
            await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            await page.wait_for_timeout(2000)
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📤 After upload")

            # ---- Step 3: Crop confirm ----
            await page.wait_for_timeout(2000)
            crop_btn = None
            for selector in [
                'button:has-text("Confirm")', 'button:has-text("Crop")',
                'button:has-text("Apply")', 'button:has-text("Next")',
                'div[role="button"]:has-text("Confirm")',
                'button[class*="crop"]', 'button[class*="confirm"]'
            ]:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        crop_btn = element
                        break
                except:
                    continue
            if crop_btn:
                logger.info("🔄 Clicking crop confirm...")
                await crop_btn.click(timeout=5000)
                await page.wait_for_timeout(2000)
                screenshot = await page.screenshot(full_page=True)
                screenshot = self._resize_image(screenshot)
                await update.message.reply_photo(photo=BytesIO(screenshot), caption="✂️ After crop confirm")

            # ---- Step 4: Find and click generate ----
            logger.info("🔍 Searching for generate button...")
            generate_btn = None
            possible_texts = ["Generate", "Undress", "Start", "Generate Image"]
            for text in possible_texts:
                buttons = await page.locator(f'button:has-text("{text}")').all()
                if buttons:
                    for btn in buttons:
                        disabled = await btn.get_attribute('disabled')
                        aria_disabled = await btn.get_attribute('aria-disabled')
                        class_attr = await btn.get_attribute('class') or ''
                        box = await btn.bounding_box()
                        if not disabled and aria_disabled != 'true' and 'disabled' not in class_attr and 'opacity-50' not in class_attr and box and box['width'] > 0 and box['height'] > 0:
                            generate_btn = btn
                            logger.info(f"✅ Found enabled button with text '{text}', box: {box}")
                            break
                    if generate_btn:
                        break

            if not generate_btn:
                generate_btn = page.locator('button:has-text("Generate")').first
                if await generate_btn.count() == 0:
                    raise Exception("No generate button found")

            box = await generate_btn.bounding_box()
            if not box:
                raise Exception("Cannot get bounding box")
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            logger.info(f"📍 Button center: ({x}, {y})")

            await generate_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await generate_btn.hover()
            await page.wait_for_timeout(200)
            await page.mouse.down()
            await page.wait_for_timeout(100)
            await page.mouse.up()
            await page.wait_for_timeout(500)
            logger.info("🔄 Generate clicked")

            # ---- Step 5: Wait full 20 minutes ----
            WAIT_SECONDS = 1200  # 20 minutes
            CHECK_INTERVAL = 10
            elapsed = 0
            limit_detected = False
            result_found = False
            error_message = None

            logger.info(f"⏳ Waiting {WAIT_SECONDS//60} minutes for generation (no early sends)...")
            while elapsed < WAIT_SECONDS:
                await asyncio.sleep(CHECK_INTERVAL)
                elapsed += CHECK_INTERVAL

                # Log progress every minute
                if elapsed % 60 == 0:
                    logger.info(f"⏱️ {elapsed//60} minutes elapsed, {WAIT_SECONDS - elapsed} seconds remaining")

                # Check for limit (log only, don't break)
                page_text = await page.content()
                limit_keywords = ['limit', 'cooldown', 'try again', 'wait', 'minutes', 'hours', 'daily', 'exceeded', 'reached']
                if any(kw in page_text.lower() for kw in limit_keywords):
                    if not limit_detected:
                        logger.warning("🚫 Daily limit or cooldown detected on page")
                    limit_detected = True
                    # Don't break, just keep waiting

                # Check for result image (log only)
                selectors = [
                    'img[class*="result"]', 'img[class*="output"]',
                    'img[class*="generated"]', 'img[alt*="result"]',
                    'img[data-testid*="result"]', 'div.result img',
                    'div.output img', 'div.generated img',
                    'img[src^="data:image"]', 'img:not([src*="logo"])'
                ]
                for sel in selectors:
                    try:
                        imgs = await page.locator(sel).all()
                        for img in imgs:
                            box = await img.bounding_box()
                            if box and box['width'] > 0 and box['height'] > 0:
                                if not result_found:
                                    logger.info(f"✅ Result image detected with selector: {sel} at {elapsed}s")
                                result_found = True
                                break
                    except:
                        continue
                    if result_found:
                        break

            # ---- Step 6: Final screenshot after full wait ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)

            # Build caption
            if limit_detected:
                caption = "⛔ Daily limit or cooldown detected during wait"
            elif result_found:
                caption = "✅ Generation complete (result image found)"
            else:
                caption = "⏱️ Timeout – no result image detected after 20 minutes"

            await update.message.reply_photo(photo=BytesIO(screenshot), caption=caption)

            # Send a text summary as well
            summary = f"Status: {caption}\nResult detected: {result_found}\nLimit detected: {limit_detected}"
            await update.message.reply_text(summary)

            await browser.close()
