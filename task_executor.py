import logging
import base64
import asyncio
import re
import random
import os
import time
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()
        logger.info("🚀 FIXED CREDIT + FULL RESOLUTION")

    def _resize_image(self, image_bytes, max_dim=1280):
        # Keep full resolution - only resize if too large for Telegram
        img = Image.open(BytesIO(image_bytes))
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            out = BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=95)
            return out.getvalue()
        return image_bytes

    async def _send_screenshot(self, update, page, caption):
        try:
            screenshot = await page.screenshot(full_page=True, type="jpeg", quality=95)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption=caption)
            return True
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return False

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
        """Get credits from the page - multiple strategies."""
        # Strategy 1: Look for coin icon and its parent
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

        # Strategy 2: Look for credit text
        credit_elem = page.locator('span[class*="credit"], div[class*="credit"], .sf-cost-credits').first
        if await credit_elem.count() > 0:
            text = await credit_elem.text_content()
            numbers = re.findall(r'\d+', text)
            if numbers:
                balance = int(numbers[0])
                logger.info(f"Balance from credit element: {balance}")
                return balance

        # Strategy 3: Search page text
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
        """Find download button with multiple strategies."""
        logger.info("🔍 Searching for download button...")
        
        # Strategy 1: Look for a[download]
        download_links = await page.locator('a[download]').all()
        if download_links:
            logger.info(f"✅ Found {len(download_links)} download links (a[download])")
            for link in download_links:
                href = await link.get_attribute('href')
                if href and ('.jpeg' in href or '.png' in href or '.jpg' in href):
                    logger.info(f"✅ Found image download link")
                    return link
            return download_links[0]

        # Strategy 2: Look for any link with image extension
        image_links = await page.locator('a[href*=".jpeg"], a[href*=".png"], a[href*=".jpg"], a[href*=".webp"]').all()
        if image_links:
            logger.info(f"✅ Found {len(image_links)} image links")
            return image_links[0]

        # Strategy 3: Look for buttons with download icon
        buttons = await page.locator('button, div[role="button"]').all()
        for btn in buttons:
            try:
                html = await btn.evaluate('el => el.outerHTML')
                if 'download' in html.lower() or 'arrow' in html.lower() or '⬇' in html:
                    logger.info(f"✅ Found potential download button")
                    return btn
            except:
                pass

        logger.warning("❌ No download button found")
        return None

    async def process_photo(self, update, image_bytes, status_msg=None):
        start_time = time.time()
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
        logger.info(f"Using fresh fingerprint: {ua[:50]}..., {width}x{height}")

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
            
            # Send landing screenshot
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
                screenshot = await page.screenshot(full_page=True)
                screenshot = self._resize_image(screenshot)
                await update.message.reply_photo(photo=BytesIO(screenshot), caption="⛔ Insufficient credits (0) — please try again later")
                await browser.close()
                return {"status": "error", "error": "Insufficient credits"}

            # === CLICK GENERATE ===
            logger.info("🔍 Looking for generate button...")
            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            
            is_disabled = await generate_btn.get_attribute('disabled')
            if is_disabled:
                logger.warning("⚠️ Generate button is disabled, waiting...")
                for _ in range(10):
                    await asyncio.sleep(1)
                    is_disabled = await generate_btn.get_attribute('disabled')
                    if not is_disabled:
                        logger.info("✅ Generate button is now enabled")
                        break
                else:
                    logger.error("❌ Generate button never became enabled")
                    await browser.close()
                    return {"status": "error", "error": "Generate button never enabled"}

            # === FORCE CLICK GENERATE ===
            try:
                await page.evaluate('(btn) => btn.click()', generate_btn)
                logger.info("✅ JavaScript click executed")
            except:
                await generate_btn.click(force=True)
                logger.info("✅ Force click executed")

            await self._human_wait(2, 3)
            await self._send_screenshot(update, page, "⚡ Generate clicked")

            # === WAIT FOR GENERATION ===
            logger.info("⏳ Waiting for generation to complete...")
            await asyncio.sleep(10)  # Wait for generation

            # === SEARCH FOR DOWNLOAD BUTTON ===
            logger.info("🔍 Searching for download button...")
            download_btn = None
            for i in range(15):  # Try for 15 seconds
                download_btn = await self._find_download_button(page)
                if download_btn:
                    logger.info(f"✅ Download button found at {i+1}s!")
                    break
                await asyncio.sleep(1)

            if download_btn:
                logger.info("🔄 Clicking download button...")
                try:
                    href = await download_btn.get_attribute('href')
                    if href:
                        import requests
                        response = requests.get(href, timeout=30)
                        if response.status_code == 200:
                            image_data = response.content
                            total_time = int(time.time() - start_time)
                            logger.info(f"✅ Downloaded image, size: {len(image_data)} bytes in {total_time}s")
                            
                            # Send full resolution image
                            await update.message.reply_photo(
                                photo=BytesIO(image_data),
                                caption=f"✨ **Your generated image!**\n\n"
                                        f"⏱️ Processed in {total_time} seconds\n"
                                        f"📦 Size: {len(image_data) // 1024} KB",
                                parse_mode="Markdown"
                            )
                            
                            await browser.close()
                            return {
                                "status": "success",
                                "image": base64.b64encode(image_data).decode(),
                                "method": "requests_download",
                                "size": len(image_data),
                                "time": total_time
                            }
                except Exception as e:
                    logger.error(f"❌ Download failed: {e}")

            # === FALLBACK: Screenshot ===
            logger.warning("ℹ️ No download button found, taking screenshot as fallback")
            screenshot_bytes = await page.screenshot(full_page=True, type="jpeg", quality=95)
            await browser.close()
            total_time = int(time.time() - start_time)
            await update.message.reply_photo(
                photo=BytesIO(screenshot_bytes),
                caption=f"⚠️ Screenshot (download failed)\n\n⏱️ Processed in {total_time} seconds",
                parse_mode="Markdown"
            )
            return {
                "status": "success",
                "image": base64.b64encode(screenshot_bytes).decode(),
                "method": "screenshot_fallback",
                "size": len(screenshot_bytes),
                "time": total_time
            }
