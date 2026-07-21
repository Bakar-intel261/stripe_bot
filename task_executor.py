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
        logger.info("🚀 FAST AUTO-TERMINATE VERSION")

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

    async def _human_wait(self, min_sec=2, max_sec=3):
        delay = random.randint(min_sec, max_sec)
        logger.info(f"⏳ Waiting {delay}s...")
        await asyncio.sleep(delay)

    async def _get_credits(self, page):
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

    async def _ensure_credits(self, page, update):
        credits = await self._get_credits(page)
        if credits is None:
            logger.warning("Could not read credits. Assuming 0.")
            return False
        if credits >= 10:
            logger.info(f"✅ Sufficient credits: {credits}")
            return True
        else:
            logger.warning(f"Insufficient credits: {credits}. Aborting.")
            return False

    async def _find_download_button(self, page):
        """Find the download button with detailed logging."""
        logger.info("🔍 Searching for download button...")

        # Strategy 1: Look for a[download] (found in logs: href with .jpeg)
        download_links = await page.locator('a[download]').all()
        if download_links:
            logger.info(f"✅ Found {len(download_links)} download links (a[download])")
            for idx, link in enumerate(download_links):
                href = await link.get_attribute('href')
                text = await link.text_content() or ''
                logger.info(f"  Link {idx}: href={href[:80] if href else 'None'}..., text='{text[:30]}'")
                if href and ('.jpeg' in href or '.png' in href or '.jpg' in href):
                    logger.info(f"✅ Found image download link: {href[:100]}...")
                    return link
            return download_links[0]

        # Strategy 2: Look for any link with .jpeg/.png/.jpg
        image_links = await page.locator('a[href*=".jpeg"], a[href*=".png"], a[href*=".jpg"]').all()
        if image_links:
            logger.info(f"✅ Found {len(image_links)} links with image extensions")
            for idx, link in enumerate(image_links):
                href = await link.get_attribute('href')
                logger.info(f"  Link {idx}: href={href[:80] if href else 'None'}...")
            return image_links[0]

        # Strategy 3: Look for buttons with download icon (SVG with arrow-down)
        svg_buttons = await page.locator('button:has(svg), div[role="button"]:has(svg)').all()
        if svg_buttons:
            logger.info(f"✅ Found {len(svg_buttons)} buttons with SVG icons")
            for idx, btn in enumerate(svg_buttons):
                html = await btn.evaluate('el => el.outerHTML')
                logger.info(f"  Button {idx}: {html[:200]}...")
            return svg_buttons[0]

        # Strategy 4: Look for buttons with download text
        text_buttons = await page.locator('button:has-text("Download"), div[role="button"]:has-text("Download")').all()
        if text_buttons:
            logger.info(f"✅ Found {len(text_buttons)} buttons with 'Download' text")
            return text_buttons[0]

        # Strategy 5: Log all buttons for debugging
        all_buttons = await page.locator('button').all()
        logger.info(f"📊 Found {len(all_buttons)} total buttons on page")
        for idx, btn in enumerate(all_buttons[:10]):  # Log first 10
            try:
                text = await btn.text_content() or ''
                class_attr = await btn.get_attribute('class') or ''
                logger.info(f"  Button {idx}: text='{text[:30]}', class='{class_attr[:50]}'")
            except:
                pass

        logger.warning("❌ No download button found")
        return None

    async def process_photo(self, update, image_bytes):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        if hasattr(fp, 'screen_resolution'):
            width = getattr(fp.screen_resolution, 'width', 1920)
            height = getattr(fp.screen_resolution, 'height', 1080)
        else:
            width, height = 1920, 1080
        locale = getattr(fp, 'locale', 'en-US')
        timezone = getattr(fp, 'timezone', 'America/New_York')
        logger.info(f"Using fingerprint: {ua[:50]}..., {width}x{height}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": width, "height": height},
                locale=locale,
                timezone_id=timezone,
                device_scale_factor=1
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
            """)

            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
                logger.info("✅ Stealth applied")
            except ImportError:
                logger.warning("⚠️ playwright-stealth not installed")

            logger.info("===== Starting process =====")

            # === NAVIGATE ===
            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await self._human_wait(2, 3)
            await self._send_screenshot(update, page, "🌐 Landing page")

            # === AGE VERIFICATION ===
            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await self._human_wait(2, 3)
                await self._send_screenshot(update, page, "✅ Age verification accepted")
            else:
                logger.info("ℹ️ No age verification needed")

            # === UPLOAD ===
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
                logger.info("📤 Image uploaded")
            except Exception as e:
                file_input = page.locator('input[type="file"]').first
                if await file_input.count() == 0:
                    raise Exception("No file input found")
                await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
                logger.info("📤 Image uploaded via direct input")

            await self._human_wait(2, 3)
            await self._send_screenshot(update, page, "📤 After upload")

            # === CONSENT POPUP ===
            logger.info("⏳ Waiting for consent popup card...")
            consent_card = page.locator('div.mi-upload-consent__card').first
            try:
                await consent_card.wait_for(state="visible", timeout=8000)
                logger.info("✅ Consent popup card is VISIBLE")
                consent_block = consent_card.locator('div.mi-upload-consent__consent').first
                if await consent_block.count() > 0:
                    await self._click_element_center(page, consent_block, "Consent block")
                    await self._human_wait(1, 2)
                agree_btn = consent_card.locator('button:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    await self._click_element_center(page, agree_btn, "Agree & continue button")
                    await self._human_wait(2, 3)
                await self._send_screenshot(update, page, "✅ Consent popup dismissed")
            except:
                logger.warning("⚠️ Consent popup card did NOT appear")

            # === ENTER PROMPT ===
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await self._human_wait(1, 2)
            await self._send_screenshot(update, page, "📝 Prompt entered")

            # === CHECK CREDITS ===
            logger.info("💰 Checking credits before generate...")
            if not await self._ensure_credits(page, update):
                logger.error("Insufficient credits, aborting")
                await self._send_screenshot(update, page, "⛔ Not enough credits")
                await update.message.reply_text("Insufficient credits (need 10). Please try a different fingerprint or later.")
                await browser.close()
                return

            # === CLICK GENERATE ===
            logger.info("🔍 Looking for generate button...")
            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            if await generate_btn.get_attribute('disabled'):
                logger.warning("⚠️ Generate button is disabled")
                await browser.close()
                return
            await self._click_element_center(page, generate_btn, "Generate button")
            await self._human_wait(2, 3)
            await self._send_screenshot(update, page, "⚡ Generate clicked")

            # === WAIT 5 SECONDS, THEN START SEARCHING ===
            logger.info("⏳ Waiting 5 seconds before checking for download button...")
            await asyncio.sleep(5)

            # === SEARCH FOR DOWNLOAD BUTTON (MAX 10 SECONDS) ===
            logger.info("⏳ Searching for download button (max 10s)...")
            download_btn = None
            start_time = asyncio.get_event_loop().time()
            timeout = 10

            while (asyncio.get_event_loop().time() - start_time) < timeout:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                logger.info(f"🔍 Attempt {elapsed+1}s: Looking for download button...")
                download_btn = await self._find_download_button(page)

                if download_btn:
                    logger.info(f"✅ Download button found at {elapsed}s!")
                    break

                await asyncio.sleep(1)

            # === FINAL CHECK BEFORE TIMEOUT ===
            if not download_btn:
                logger.info("🔍 Final check before timeout...")
                download_btn = await self._find_download_button(page)

            # === CLICK DOWNLOAD BUTTON ===
            if download_btn:
                logger.info("🔄 Clicking download button...")
                try:
                    # Get the href from the download link
                    href = await download_btn.get_attribute('href')
                    if href:
                        logger.info(f"📥 Downloading from URL: {href[:100]}...")
                        # Use requests to download the file
                        import requests
                        response = requests.get(href, timeout=30)
                        if response.status_code == 200:
                            image_data = response.content
                            logger.info(f"✅ Downloaded image, size: {len(image_data)} bytes")
                            await browser.close()
                            return {
                                "status": "success",
                                "image": base64.b64encode(image_data).decode(),
                                "method": "requests_download",
                                "size": len(image_data)
                            }
                        else:
                            logger.error(f"❌ Download failed: HTTP {response.status_code}")
                    else:
                        logger.warning("❌ No href found on download link")
                except Exception as e:
                    logger.error(f"❌ Download failed: {e}")
                    # Fallback: take screenshot
                    screenshot_bytes = await page.screenshot(full_page=True)
                    await browser.close()
                    return {
                        "status": "success",
                        "image": base64.b64encode(screenshot_bytes).decode(),
                        "method": "screenshot_fallback",
                        "size": len(screenshot_bytes)
                    }
            else:
                # === FALLBACK: Take screenshot ===
                logger.warning("ℹ️ No download button found, taking screenshot as fallback")
                screenshot_bytes = await page.screenshot(full_page=True)
                await browser.close()
                return {
                    "status": "success",
                    "image": base64.b64encode(screenshot_bytes).decode(),
                    "method": "screenshot_fallback",
                    "size": len(screenshot_bytes)
                }

            # If we reach here, something went wrong
            screenshot_bytes = await page.screenshot(full_page=True)
            await browser.close()
            return {
                "status": "success",
                "image": base64.b64encode(screenshot_bytes).decode(),
                "method": "screenshot_fallback",
                "size": len(screenshot_bytes)
            }
