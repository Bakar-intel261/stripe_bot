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

    async def _click_element_center(self, page, locator, description="element"):
        try:
            box = await locator.bounding_box()
            if not box:
                logger.warning(f"⚠️ Could not get bounding box for {description}")
                await locator.click()
                return
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            logger.info(f"📍 Clicking {description} at ({x:.1f}, {y:.1f})")
            await page.mouse.click(x, y)
            return True
        except Exception as e:
            logger.error(f"❌ Error clicking {description}: {e}")
            return False

    async def _upload_image(self, page, image_bytes):
        """Upload image using the upload button and custom input fallback."""
        # First, click the upload button to ensure any event listeners fire
        upload_btn = page.locator('button.sf-image-to-image__upload').first
        if await upload_btn.count() > 0:
            logger.info("🖱️ Clicking upload button...")
            await upload_btn.click()
            await page.wait_for_timeout(1000)
        else:
            logger.warning("⚠️ Upload button not found, proceeding with custom input")

        # Use custom input method (worked previously)
        logger.info("📤 Creating custom file input via JavaScript...")
        await page.evaluate("""
            () => {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'image/*';
                input.id = 'custom_file_input';
                input.style.position = 'absolute';
                input.style.opacity = '0';
                input.style.width = '100%';
                input.style.height = '100%';
                input.style.cursor = 'pointer';
                const area = document.querySelector('button.sf-image-to-image__upload');
                if (area) {
                    area.style.position = 'relative';
                    area.appendChild(input);
                } else {
                    document.body.appendChild(input);
                }
            }
        """)
        custom_input = page.locator('#custom_file_input')
        if await custom_input.count() > 0:
            await custom_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            logger.info("📤 Image uploaded via custom input")
            return
        raise Exception("Could not upload image")

    async def process_photo(self, update, image_bytes):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        width = 1920
        height = 1080

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(user_agent=ua, viewport={"width": width, "height": height})
            page = await context.new_page()

            logger.info("===== Starting process =====")

            # ---- Step 1: Landing & Age Verification ----
            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await page.wait_for_timeout(3000)
            else:
                age_btn = page.locator('button:has-text("I Am 18")').first
                if await age_btn.count() > 0:
                    logger.info("✅ Found age button with 'I Am 18', clicking...")
                    await self._click_element_center(page, age_btn, "Age verification button (fallback)")
                    await page.wait_for_timeout(3000)
                else:
                    logger.info("ℹ️ No age verification needed")

            # ---- Screenshot 1: Landing ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="🌐 Landing page (age accepted)")

            # ---- Step 2: Upload ----
            logger.info("📤 Uploading image...")
            await self._upload_image(page, image_bytes)
            await page.wait_for_timeout(3000)  # wait for upload to process

            # ---- Step 3: Check for consent popup briefly ----
            # Wait a small amount for potential popup, but don't click it
            await page.wait_for_timeout(2000)

            # ---- Step 4: Enter prompt ----
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await page.wait_for_timeout(1000)
            else:
                logger.warning("⚠️ No prompt input found, continuing anyway")

            # ---- Final screenshot: Uploaded & prompt entered ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📤 Uploaded & prompt entered")

            logger.info("===== Process finished (stopped after upload+prompt) =====")
            # We intentionally stop here – no generate, no waiting

            await browser.close()
