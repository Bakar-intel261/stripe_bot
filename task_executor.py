import logging
import base64
import asyncio
import re
import random
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

    async def _human_wait(self, min_sec=5, max_sec=10):
        delay = random.randint(min_sec, max_sec)
        logger.info(f"⏳ Waiting {delay} seconds...")
        await asyncio.sleep(delay)

    async def _refresh_credits_proactively(self, update, page):
        """Navigate to homepage and back to force new session credits."""
        logger.info("🔄 Refreshing credits by going to homepage and back...")
        current_url = page.url
        await page.goto("https://www.swapfaces.ai")
        await self._human_wait(4, 6)
        await self._send_screenshot(update, page, "🏠 Homepage")
        await page.goto(current_url)
        await self._human_wait(5, 8)
        await self._send_screenshot(update, page, "🔙 Back to generation page")
        return True

    async def _get_credits(self, page):
        """Extract the actual credit balance after waiting for it to load."""
        # Wait for the coin icon to be visible (up to 10 seconds)
        try:
            coin = page.locator('img[alt*="coin"], img[src*="coin"], svg[alt*="coin"]').first
            await coin.wait_for(state="visible", timeout=10000)
        except:
            logger.warning("Coin icon not visible after 10s")
            return None

        # Now get the parent text
        parent = coin.locator('..')
        if await parent.count() > 0:
            text = await parent.text_content()
            logger.info(f"Text from coin parent: {text}")
            numbers = re.findall(r'\d+', text)
            if numbers:
                balance = int(numbers[0])
                logger.info(f"Balance from coin parent: {balance}")
                return balance

        # Fallback: search for "Credits" followed by a number
        page_text = await page.content()
        match = re.search(r'Credits?\s*:?\s*(\d+)', page_text, re.I)
        if match:
            balance = int(match.group(1))
            logger.info(f"Balance from page text: {balance}")
            return balance

        return None

    async def _ensure_credits(self, page, update):
        """Check credits; if 0, refresh via homepage and re-check up to 2 times."""
        for attempt in range(2):
            credits = await self._get_credits(page)
            if credits is None:
                logger.warning("Could not read credits. Assuming 0.")
                return False
            if credits >= 10:
                logger.info(f"✅ Sufficient credits: {credits}")
                return True
            logger.warning(f"⚠️ Insufficient credits: {credits} (attempt {attempt+1}/2). Refreshing...")
            await self._refresh_credits_proactively(update, page)
            # Wait extra to let credits load
            await self._human_wait(8, 12)
        logger.error("No free credits after two refresh attempts. Aborting.")
        return False

    async def process_photo(self, update, image_bytes):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        # Full fingerprint application
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        # Get screen resolution
        if hasattr(fp, 'screen_resolution'):
            width = getattr(fp.screen_resolution, 'width', 1920)
            height = getattr(fp.screen_resolution, 'height', 1080)
        elif hasattr(fp, 'screen'):
            if isinstance(fp.screen, dict):
                width = fp.screen.get('width', 1920)
                height = fp.screen.get('height', 1080)
            else:
                width = getattr(fp.screen, 'width', 1920)
                height = getattr(fp.screen, 'height', 1080)
        else:
            width, height = 1920, 1080

        locale = getattr(fp, 'locale', 'en-US')
        timezone = getattr(fp, 'timezone', 'America/New_York')
        device_scale = getattr(fp, 'device_scale_factor', 1)

        logger.info(f"Using fingerprint: {ua[:50]}..., {width}x{height}, locale={locale}, tz={timezone}")

        async with async_playwright() as p:
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
            # Create a context with full fingerprint and realistic settings
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": width, "height": height},
                locale=locale,
                timezone_id=timezone,
                device_scale_factor=device_scale,
                color_scheme='light',  # or random
                extra_http_headers={
                    'Accept-Language': f"{locale},en;q=0.9",
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Cache-Control': 'max-age=0',
                },
                java_script_enabled=True,
                bypass_csp=True,
            )
            page = await context.new_page()

            # Remove webdriver and add other stealth properties
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(window, 'chrome', { value: { runtime: {} } });
                Object.defineProperty(navigator, 'platform', { value: 'Win32' });
                // Add more to mimic real browser
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
                logger.info("✅ Stealth applied")
            except ImportError:
                logger.warning("⚠️ playwright-stealth not installed")

            logger.info("===== Starting process =====")

            # ---- Step 1: Landing ----
            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await self._human_wait(5, 8)
            await self._send_screenshot(update, page, "🌐 Landing page")

            # ---- Step 2: Age Verification ----
            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await self._human_wait(3, 5)
                await self._send_screenshot(update, page, "✅ Age verification accepted")
            else:
                logger.info("ℹ️ No age verification needed")

            # ---- Step 3: Check credits immediately after age gate ----
            logger.info("💰 Checking credits after age gate...")
            if not await self._ensure_credits(page, update):
                logger.error("No free credits after refresh, aborting")
                await self._send_screenshot(update, page, "⛔ No free credits available")
                await update.message.reply_text("No free credits available. Please try a different fingerprint or later.")
                await browser.close()
                return
            await self._send_screenshot(update, page, "💰 Credits OK (10+)")

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

            await self._human_wait(2, 4)
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
                    await self._human_wait(1, 2)
                agree_btn = consent_card.locator('button:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    await self._click_element_center(page, agree_btn, "Agree & continue button")
                    await self._human_wait(3, 5)
                await self._send_screenshot(update, page, "✅ Consent popup dismissed")

            # ---- Step 6: Enter prompt ----
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await self._human_wait(1, 2)
            await self._send_screenshot(update, page, "📝 Prompt entered")

            # ---- Step 7: Click Generate ----
            logger.info("🔍 Looking for generate button...")
            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            if await generate_btn.get_attribute('disabled'):
                logger.warning("⚠️ Generate button is disabled, aborting")
                await self._send_screenshot(update, page, "⛔ Generate disabled")
                await browser.close()
                return
            await self._click_element_center(page, generate_btn, "Generate button")
            await self._human_wait(2, 3)
            await self._send_screenshot(update, page, "⚡ Generate clicked")

            # ---- Step 8: Wait for result ----
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

            # ---- Step 9: Final ----
            await self._human_wait(2, 4)
            if result_img:
                caption = f"✅ Final result (generated at {elapsed}s)"
            else:
                page_text = await page.content()
                if "credit" in page_text.lower() or "not enough" in page_text.lower():
                    caption = "⚠️ Credit/error detected – result may not be generated"
                else:
                    caption = "⏱️ Timeout – no result after 60s"
            await self._send_screenshot(update, page, caption)
            await browser.close()
