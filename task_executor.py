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

            # ---- Step 3: Crop confirm (if present) ----
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

            # ---- Step 4: Wait for generate button to become enabled ----
            generate_btn = page.locator('button:has-text("Generate"):not([disabled]):not(.disabled):not(.opacity-50)').first
            if await generate_btn.count() == 0:
                generate_btn = page.locator('button:has-text("Generate"), button:has-text("Undress"), button:has-text("Start")').first
                if await generate_btn.count() == 0:
                    raise Exception("No generate button found")
            logger.info("⏳ Waiting for generate button to become active...")
            for _ in range(30):
                disabled = await generate_btn.get_attribute('disabled')
                aria_disabled = await generate_btn.get_attribute('aria-disabled')
                class_attr = await generate_btn.get_attribute('class') or ''
                if not disabled and aria_disabled != 'true' and 'disabled' not in class_attr and 'opacity-50' not in class_attr:
                    logger.info("✅ Generate button is active")
                    break
                await asyncio.sleep(0.5)
            else:
                logger.warning("Generate button still disabled, attempting click anyway")

            box = await generate_btn.bounding_box()
            if not box:
                await generate_btn.click()
            else:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                logger.info(f"📍 Generate button coordinates: ({x}, {y})")
                await generate_btn.scroll_into_view_if_needed()
                await page.mouse.click(x, y)
            logger.info("🔄 Generate clicked")

            # ---- Step 5: Wait for "Processing" / "Verifying" text ----
            await page.wait_for_timeout(2000)
            processing_text = page.locator('text=Processing, text=Verifying, text=Generating, text=Loading, text=Please wait').first
            if await processing_text.count() > 0:
                logger.info("✅ Processing message detected")
            else:
                logger.info("No explicit processing message")
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="🔄 Processing...")

            # ---- Step 6: Wait for result image ----
            logger.info("⏳ Waiting for result image...")
            result_img = None
            for _ in range(60):
                images = await page.locator('img[src^="data:image"], img[class*="result"], img[class*="output"], img[class*="generated"]').all()
                for img in images:
                    box = await img.bounding_box()
                    if box and box['width'] > 0 and box['height'] > 0:
                        result_img = img
                        break
                if result_img:
                    break
                await asyncio.sleep(1)
            if result_img:
                logger.info("✅ Result image found")
            else:
                logger.warning("No result image found")

            # ---- Step 7: Final screenshot ----
            await page.wait_for_timeout(2000)
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="✅ Final result")

            await browser.close()
