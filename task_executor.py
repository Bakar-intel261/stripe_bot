import logging
import base64
import asyncio
import re
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

    async def _send_screenshot(self, update, page, caption):
        screenshot = await page.screenshot(full_page=True)
        screenshot = self._resize_image(screenshot)
        await update.message.reply_photo(photo=BytesIO(screenshot), caption=caption)

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

    async def _refresh_credits_proactively(self, update, page):
        """Click coin icon, wait, go back to refresh credits."""
        logger.info("🪙 Proactive credit refresh: clicking coin icon...")
        coin_btn = page.locator('img[alt*="coin"], img[src*="coin"], button:has-text("Credits"), a:has-text("Credits")').first
        if await coin_btn.count() > 0:
            await coin_btn.click()
            await page.wait_for_timeout(3000)
            await self._send_screenshot(update, page, "🪙 Pricing / Credits page after coin click")
            await page.wait_for_timeout(2000)
            logger.info("🔙 Going back to generation page...")
            await page.go_back()
            await page.wait_for_timeout(3000)
            await self._send_screenshot(update, page, "🔙 Returned to generation page after credit refresh")
            return True
        else:
            logger.warning("⚠️ Coin/credit button not found")
            return False

    async def _get_credits(self, page):
        """Extract credit balance."""
        try:
            credit_elem = page.locator('img[alt*="coin"], div[class*="credit"], span[class*="credit"], .sf-cost-credits').first
            await credit_elem.wait_for(state="visible", timeout=5000)
        except:
            page_text = await page.content()
            match = re.search(r'credits?\s*:?\s*(\d+)', page_text, re.I)
            if match:
                return int(match.group(1))
            return None
        text = await credit_elem.text_content()
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[0])
        parent = credit_elem.locator('..')
        if await parent.count() > 0:
            text = await parent.text_content()
            numbers = re.findall(r'\d+', text)
            if numbers:
                return int(numbers[0])
        return None

    async def _ensure_credits(self, page):
        """Ensure at least 10 credits; refresh if not."""
        credits = await self._get_credits(page)
        if credits is None:
            logger.warning("Could not determine credits, assuming OK")
            return True
        if credits >= 10:
            logger.info(f"✅ Sufficient credits: {credits}")
            return True
        logger.warning(f"⚠️ Insufficient credits: {credits}. Refreshing...")
        coin_btn = page.locator('img[alt*="coin"], img[src*="coin"]').first
        if await coin_btn.count() > 0:
            await coin_btn.click()
            await page.wait_for_timeout(5000)
            await page.go_back()
            await page.wait_for_timeout(3000)
            new_credits = await self._get_credits(page)
            if new_credits is not None and new_credits >= 10:
                logger.info(f"✅ Credits refreshed to {new_credits}")
                return True
            else:
                logger.warning(f"Still insufficient: {new_credits}")
                return False
        return False

    async def process_photo(self, update, image_bytes):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        width = getattr(fp.screen_resolution, 'width', 1920)
        height = getattr(fp.screen_resolution, 'height', 1080)

        async with async_playwright() as p:
            # Launch with anti-detection args
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                    "--disable-dev-shm-usage"
                ]
            )
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": width, "height": height},
                locale=getattr(fp, 'locale', 'en-US'),
                timezone_id=getattr(fp, 'timezone', 'America/New_York'),
                # Reduce detection
                device_scale_factor=1
            )
            page = await context.new_page()

            # Remove webdriver flag
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)

            # Apply playwright-stealth if available
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
                logger.info("✅ Stealth applied")
            except ImportError:
                logger.warning("⚠️ playwright-stealth not installed, continuing without")

            logger.info("===== Starting process =====")

            # ---- Step 1: Landing ----
            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            await self._send_screenshot(update, page, "🌐 Landing page")

            # ---- Step 2: Age Verification ----
            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await page.wait_for_timeout(3000)
                await self._send_screenshot(update, page, "✅ Age verification accepted")
            else:
                logger.info("ℹ️ No age verification needed")

            # ---- Step 3: Proactive Credit Refresh ----
            await self._refresh_credits_proactively(update, page)

            # ---- Step 4: Upload ----
            logger.info("🔍 Looking for upload area...")
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

            await page.wait_for_timeout(2000)
            await self._send_screenshot(update, page, "📤 After upload")

            # ---- Step 5: Consent popup ----
            logger.info("⏳ Waiting for consent popup card...")
            consent_card = page.locator('div.mi-upload-consent__card').first
            try:
                await consent_card.wait_for(state="visible", timeout=8000)
                logger.info("✅ Consent popup card is VISIBLE")
            except:
                logger.warning("⚠️ Consent popup card did NOT appear")
                await self._send_screenshot(update, page, "📸 No consent popup")

            if await consent_card.count() > 0 and await consent_card.is_visible():
                consent_block = consent_card.locator('div.mi-upload-consent__consent').first
                if await consent_block.count() > 0:
                    await self._click_element_center(page, consent_block, "Consent block")
                    await page.wait_for_timeout(500)
                agree_btn = consent_card.locator('button:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    await self._click_element_center(page, agree_btn, "Agree & continue button")
                    await page.wait_for_timeout(3000)
                await self._send_screenshot(update, page, "✅ Consent popup dismissed")

            # ---- Step 6: Enter prompt ----
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await page.wait_for_timeout(1000)
            await self._send_screenshot(update, page, "📝 Prompt entered")

            # ---- Step 7: Credit check before generate ----
            logger.info("💰 Checking credits before generate...")
            if not await self._ensure_credits(page):
                logger.error("Insufficient credits after refresh, aborting")
                await self._send_screenshot(update, page, "⛔ Not enough credits")
                await update.message.reply_text("Insufficient credits (need 10). Please try a different fingerprint or later.")
                await browser.close()
                return
            await self._send_screenshot(update, page, "💰 Credits OK")

            # ---- Step 8: Click Generate ----
            logger.info("🔍 Looking for generate button...")
            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            if await generate_btn.get_attribute('disabled'):
                logger.warning("⚠️ Generate button is disabled")
                if not await self._ensure_credits(page):
                    await self._send_screenshot(update, page, "⛔ Generate disabled, no credits")
                    await browser.close()
                    return
            await self._click_element_center(page, generate_btn, "Generate button")
            await page.wait_for_timeout(2000)
            await self._send_screenshot(update, page, "⚡ Generate clicked")

            # ---- Step 9: Wait for result ----
            logger.info("⏳ Waiting for result image (max 60s)...")
            result_img = None
            start_time = asyncio.get_event_loop().time()
            for i in range(60):
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                images = await page.locator('img[src^="data:image"], img[class*="result"], img[class*="output"], img[class*="generated"]').all()
                for img in images:
                    box = await img.bounding_box()
                    if box and box['width'] > 0 and box['height'] > 0:
                        result_img = img
                        break
                if result_img:
                    break
                await asyncio.sleep(1)

            # ---- Step 10: Final ----
            await page.wait_for_timeout(2000)
            if result_img:
                caption = f"✅ Final result (generated at {elapsed}s)"
            else:
                # Check page for error
                page_text = await page.content()
                if "credit" in page_text.lower() or "not enough" in page_text.lower():
                    caption = "⚠️ Credit/error detected – result may not be generated"
                else:
                    caption = "⏱️ Timeout – no result after 60s"
            await self._send_screenshot(update, page, caption)
            await browser.close()
