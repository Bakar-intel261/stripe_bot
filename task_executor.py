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
        """Upload image by locating the upload area via 'Files supported:' text."""
        text_selectors = [
            'text="Files supported:"',
            'text="Files supported"',
            'div:has-text("Files supported:")',
            'div:has-text("Files supported")'
        ]
        upload_area = None
        for sel in text_selectors:
            try:
                element = page.locator(sel).first
                if await element.count() > 0:
                    logger.info(f"✅ Found text with selector: {sel}")
                    parent = element.locator('xpath=ancestor::div[1]')
                    if await parent.count() > 0:
                        upload_area = parent
                    else:
                        upload_area = element
                    break
            except:
                continue

        if not upload_area or await upload_area.count() == 0:
            upload_area = page.locator('div[class*="drop"], div[class*="upload"], div[class*="drag"]').first
            if await upload_area.count() == 0:
                raise Exception("Could not find upload area")

        logger.info("✅ Upload area located, attempting upload...")
        try:
            async with page.expect_file_chooser(timeout=10000) as fc_info:
                await upload_area.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            logger.info("📤 Image uploaded via file chooser")
            return
        except Exception as e:
            logger.warning(f"File chooser failed: {e}, falling back to direct input")

        file_input = page.locator('input[type="file"]').first
        if await file_input.count() > 0:
            await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            logger.info("📤 Image uploaded via direct file input")
            return

        logger.info("Creating custom file input via JavaScript")
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
                const area = document.querySelector('div[class*="upload"], div[class*="drop"]');
                if (area) area.appendChild(input);
                else document.body.appendChild(input);
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
            await page.wait_for_timeout(5000)  # wait for upload to settle

            # ---- Debug screenshot after upload ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 After upload (debug)")

            # ---- Step 3: Consent Popup ----
            try:
                # Wait for checkbox to be visible (consent popup)
                consent_checkbox = page.locator('input[type="checkbox"]').first
                await consent_checkbox.wait_for(state="visible", timeout=10000)
                if await consent_checkbox.count() > 0:
                    logger.info("✅ Consent popup detected, checking checkbox...")
                    await consent_checkbox.click()
                    await page.wait_for_timeout(500)
                    agree_btn = page.locator('button:has-text("Agree & continue"), div:has-text("Agree & continue")').first
                    if await agree_btn.count() > 0:
                        logger.info("✅ Clicking Agree & continue via coordinates...")
                        await self._click_element_center(page, agree_btn, "Agree & continue button")
                        await page.wait_for_timeout(3000)
                else:
                    logger.info("ℹ️ No consent popup detected")
            except Exception as e:
                logger.warning(f"Consent popup handling failed: {e}")
                # If no checkbox, maybe it's already accepted

            # ---- Step 4: Wait for upload to complete ----
            logger.info("⏳ Waiting for upload to complete...")
            await page.wait_for_timeout(5000)

            # ---- Step 5: Enter prompt ----
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await page.wait_for_timeout(1000)
            else:
                logger.warning("⚠️ No prompt input found, continuing anyway")

            # ---- Screenshot 2: After upload and prompt ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📤 Uploaded & prompt entered")

            # ---- Step 6: Click generate ----
            generate_btn = page.locator('button:has-text("Generate"), div:has-text("Generate"), input[value*="Generate"]').first
            if await generate_btn.count() == 0:
                raise Exception("No generate button found")
            logger.info("🔄 Clicking generate button via coordinates...")
            await self._click_element_center(page, generate_btn, "Generate button")
            await page.wait_for_timeout(2000)

            # ---- Step 7: Wait for result (up to 60 seconds) with logging ----
            logger.info("⏳ Waiting for result image... (max 60s)")
            result_img = None
            start_time = asyncio.get_event_loop().time()
            for i in range(60):
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                logger.info(f"🔍 Check {i+1}: Looking for result image... (elapsed {elapsed}s)")
                images = await page.locator('img[src^="data:image"], img[class*="result"], img[class*="output"], img[class*="generated"]').all()
                logger.info(f"   Found {len(images)} candidate image(s)")
                for idx, img in enumerate(images):
                    box = await img.bounding_box()
                    src = await img.get_attribute('src') or ''
                    logger.info(f"   Image {idx}: src={src[:50]}..., box={box}")
                    if box and box['width'] > 0 and box['height'] > 0:
                        result_img = img
                        logger.info(f"✅ Result image detected at {elapsed}s (width={box['width']}, height={box['height']})")
                        break
                if result_img:
                    break
                page_text = await page.content()
                if "credit" in page_text.lower() or "not enough" in page_text.lower():
                    logger.warning("⚠️ Credit/error message detected: " + page_text[:200])
                await asyncio.sleep(1)

            # ---- Step 8: Final screenshot ----
            await page.wait_for_timeout(2000)
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            if result_img:
                caption = f"✅ Final result (generated at {elapsed}s)"
            else:
                page_text = await page.content()
                if "credit" in page_text.lower() or "not enough" in page_text.lower():
                    caption = "⚠️ Credit/error detected – result may not be generated"
                else:
                    caption = "⏱️ Timeout – no result after 60s"
            await update.message.reply_photo(photo=BytesIO(screenshot), caption=caption)
            logger.info(f"===== Process finished. Result found: {result_img is not None} =====")

            await browser.close()
