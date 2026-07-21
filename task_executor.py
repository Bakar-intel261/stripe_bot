import logging
import base64
import asyncio
import re
import random
import os
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()
        logger.info("🚀 VPN COMPATIBLE VERSION DEPLOYED")

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
        """Click Credits link, wait, then go back to generation page."""
        logger.info("🪙 Clicking Credits link...")
        credit_link = page.locator('a:has-text("Credits")').first
        if await credit_link.count() == 0:
            credit_link = page.locator('button:has-text("Credits")').first
        if await credit_link.count() == 0:
            logger.warning("⚠️ Credits link not found")
            return False

        await credit_link.click()
        await self._human_wait(3, 5)
        await self._send_screenshot(update, page, "🪙 Credits page")

        # Go back to generation page
        logger.info("🔙 Going back to generation page...")
        await page.go_back()
        await self._human_wait(3, 5)
        await self._send_screenshot(update, page, "🔙 Back to generation page")
        return True

    async def _get_credits(self, page):
        """Extract the actual credit balance."""
        selectors = [
            'span[class*="credit"]',
            'div[class*="credit"]',
            'span:has-text("Credits")',
            'div:has-text("Credits")',
            '.sf-cost-credits',
            '.credits',
            '[data-testid="credits"]',
        ]
        for sel in selectors:
            try:
                elem = page.locator(sel).first
                if await elem.count() > 0:
                    text = await elem.text_content()
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        balance = int(numbers[0])
                        logger.info(f"Found balance {balance} with selector '{sel}'")
                        return balance
            except Exception:
                continue

        coin = page.locator('img[alt*="coin"], img[src*="coin"], svg[alt*="coin"]').first
        if await coin.count() > 0:
            parent = coin.locator('..')
            if await parent.count() > 0:
                text = await parent.text_content()
                numbers = re.findall(r'\d+', text)
                if numbers:
                    balance = int(numbers[0])
                    logger.info(f"Balance from coin parent: {balance}")
                    return balance

        page_text = await page.content()
        match = re.search(r'Credits?\s*:?\s*(\d+)', page_text, re.I)
        if match:
            balance = int(match.group(1))
            logger.info(f"Balance from page text: {balance}")
            return balance

        logger.warning("Could not find credit balance")
        return None

    async def _ensure_credits(self, page, update, refresh_if_needed=True):
        credits = await self._get_credits(page)
        if credits is None:
            logger.warning("Could not read credits. Assuming 0.")
            return False
        if credits >= 10:
            logger.info(f"✅ Sufficient credits: {credits}")
            return True
        if refresh_if_needed:
            logger.warning(f"⚠️ Insufficient credits: {credits}. Attempting refresh...")
            await self._refresh_credits_proactively(update, page)
            await self._human_wait(3, 5)
            credits = await self._get_credits(page)
            if credits is not None and credits >= 10:
                logger.info(f"✅ Credits refreshed to {credits}")
                return True
            else:
                logger.warning(f"Still insufficient: {credits}. Aborting.")
                return False
        else:
            logger.warning(f"Insufficient credits: {credits}. Aborting.")
            return False

    async def process_photo(self, update, image_bytes):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
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
        logger.info(f"Using fingerprint: {ua[:50]}..., {width}x{height}, locale={locale}, tz={timezone}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                channel="chrome",
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
                locale=locale,
                timezone_id=timezone,
                device_scale_factor=1,
                extra_http_headers={
                    'Accept-Language': f"{locale},en;q=0.9",
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Cache-Control': 'max-age=0',
                }
            )
            page = await context.new_page()

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(window, 'chrome', { value: { runtime: {} } });
                Object.defineProperty(navigator, 'platform', { value: 'Win32' });
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

            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)

            try:
                ip = await page.evaluate("() => fetch('https://api.ipify.org?format=json').then(r => r.json()).then(data => data.ip)")
                logger.info(f"🖥️ Current IP: {ip}")
            except:
                logger.warning("Could not fetch IP")

            await self._human_wait(3, 6)
            await self._send_screenshot(update, page, "🌐 Landing page")

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await self._human_wait(3, 5)
                await self._send_screenshot(update, page, "✅ Age verification accepted")
            else:
                logger.info("ℹ️ No age verification needed")

            await self._refresh_credits_proactively(update, page)

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

            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await self._human_wait(1, 2)
            await self._send_screenshot(update, page, "📝 Prompt entered")

            logger.info("💰 Checking credits before generate...")
            if not await self._ensure_credits(page, update, refresh_if_needed=True):
                logger.error("Insufficient credits after refresh, aborting")
                await self._send_screenshot(update, page, "⛔ Not enough credits")
                await update.message.reply_text("Insufficient credits (need 10). Please try a different fingerprint or later.")
                await browser.close()
                return
            await self._send_screenshot(update, page, "💰 Credits OK (10+)")

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
