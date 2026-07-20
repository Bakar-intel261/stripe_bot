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

            # Early debug screenshot
            await page.wait_for_timeout(1000)
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="🌐 1s after load (debug)")

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await page.wait_for_timeout(3000)
            else:
                logger.info("ℹ️ No age verification needed")

            # ---- Screenshot 1: Landing (age accepted) ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="🌐 Landing page (age accepted)")

            # ---- Step 2: Upload ----
            logger.info("🔍 Looking for upload area (button.sf-image-to-image__upload)...")
            upload_btn = page.locator('button.sf-image-to-image__upload').first
            await upload_btn.wait_for(state="visible", timeout=15000)
            logger.info("✅ Upload button found and visible")

            try:
                async with page.expect_file_chooser(timeout=15000) as fc_info:
                    logger.info("🖱️ Clicking upload button...")
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
                logger.info("📤 Image uploaded via file chooser")
            except Exception as e:
                logger.warning(f"File chooser failed: {e}, using direct input fallback")
                file_input = page.locator('input[type="file"]').first
                if await file_input.count() == 0:
                    raise Exception("No file input found")
                await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
                logger.info("📤 Image uploaded via direct input")

            # ---- Step 3: Handle consent popup ----
            logger.info("⏳ Waiting for consent popup card...")
            consent_card = page.locator('div.mi-upload-consent__card').first
            try:
                await consent_card.wait_for(state="visible", timeout=8000)
                logger.info("✅ Consent popup card is VISIBLE")
            except:
                logger.warning("⚠️ Consent popup card did NOT appear within 8 seconds")
                screenshot = await page.screenshot(full_page=True)
                screenshot = self._resize_image(screenshot)
                await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 No popup - page state")

            if await consent_card.count() > 0 and await consent_card.is_visible():
                logger.info("🔍 Inspecting consent card contents...")

                # ---- 3a: Click the consent block (the whole div that toggles checkbox) ----
                consent_block = consent_card.locator('div.mi-upload-consent__consent').first
                if await consent_block.count() > 0:
                    logger.info("✅ Found consent block (div.mi-upload-consent__consent)")
                    await self._click_element_center(page, consent_block, "Consent block")
                    await page.wait_for_timeout(500)
                    logger.info("✅ Clicked consent block to toggle checkbox")
                else:
                    logger.warning("⚠️ Consent block not found, trying to find checkbox directly")
                    # Fallback: try to click the checkbox itself
                    checkbox = consent_card.locator('input[type="checkbox"]').first
                    if await checkbox.count() > 0:
                        await self._click_element_center(page, checkbox, "Consent checkbox (fallback)")
                        await page.wait_for_timeout(500)
                    else:
                        logger.warning("⚠️ No checkbox or consent block found inside card")

                # ---- 3b: Click Agree & continue ----
                agree_btn = consent_card.locator('button:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    logger.info("✅ Agree button found inside card")
                    await self._click_element_center(page, agree_btn, "Agree & continue button")
                    await page.wait_for_timeout(3000)
                else:
                    logger.warning("⚠️ Agree button not found inside card")

                # ---- 3c: Verify popup dismissed ----
                await page.wait_for_timeout(1000)
                if await consent_card.count() > 0 and await consent_card.is_visible():
                    logger.warning("⚠️ Consent popup STILL visible after interaction")
                    screenshot = await page.screenshot(full_page=True)
                    screenshot = self._resize_image(screenshot)
                    await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 Popup still visible")
                else:
                    logger.info("✅ Consent popup successfully dismissed")
            else:
                logger.info("ℹ️ No consent popup card found – may not be needed")

            # ---- Debug screenshot after consent ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 After consent (debug)")

            # ---- Step 4: Enter prompt ----
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await page.wait_for_timeout(1000)
            else:
                logger.warning("⚠️ No prompt input found, continuing anyway")

            # ---- Step 5: Final screenshot ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📤 Uploaded & prompt entered")

            logger.info("===== Process finished =====")
            await browser.close()
