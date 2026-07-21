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

    async def _human_wait(self, min_sec=2, max_sec=3):  # FASTER
        delay = random.randint(min_sec, max_sec)
        logger.info(f"⏳ Waiting {delay}s...")
        await asyncio.sleep(delay)

    async def _refresh_credits_proactively(self, update, page):
        logger.info("🪙 Clicking Credits link...")
        credit_link = page.locator('a:has-text("Credits")').first
        if await credit_link.count() == 0:
            credit_link = page.locator('button:has-text("Credits")').first
        if await credit_link.count() == 0:
            logger.warning("⚠️ Credits link not found")
            return False

        await credit_link.click()
        await self._human_wait(2, 3)
        await self._send_screenshot(update, page, "🪙 Credits page")
        await page.go_back()
        await self._human_wait(2, 3)
        await self._send_screenshot(update, page, "🔙 Back to generation page")
        return True

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
            await self._human_wait(2, 3)
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

    async def _find_download_button(self, page):
        """Find and click the download button to get the generated image."""
        logger.info("🔍 Looking for download button...")
        
        # Strategy 1: Look for a[download]
        download_links = await page.locator('a[download]').all()
        if download_links:
            logger.info(f"✅ Found {len(download_links)} download links")
            for link in download_links:
                href = await link.get_attribute('href')
                if href:
                    logger.info(f"Download link href: {href[:100]}...")
                    return link
        
        # Strategy 2: Look for buttons with download icon
        download_buttons = await page.locator('button[aria-label*="download" i], button[title*="download" i]').all()
        if download_buttons:
            logger.info(f"✅ Found {len(download_buttons)} download buttons")
            return download_buttons[0]
        
        # Strategy 3: Look for any button with download text
        download_buttons = await page.locator('button:has-text("Download"), div[role="button"]:has-text("Download")').all()
        if download_buttons:
            logger.info(f"✅ Found {len(download_buttons)} buttons with 'Download' text")
            return download_buttons[0]
        
        # Strategy 4: Look for SVG with arrow-down icon (common download icon)
        svg_buttons = await page.locator('button:has(svg[class*="download"]), button:has(svg[class*="arrow-down"]), div[role="button"]:has(svg[class*="download"])').all()
        if svg_buttons:
            logger.info(f"✅ Found {len(svg_buttons)} buttons with download SVG icon")
            return svg_buttons[0]
        
        # Strategy 5: Look for img with download icon
        img_buttons = await page.locator('button:has(img[alt*="download" i]), button:has(img[src*="download" i])').all()
        if img_buttons:
            logger.info(f"✅ Found {len(img_buttons)} buttons with download image")
            return img_buttons[0]
        
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

            # === REFRESH CREDITS ===
            await self._refresh_credits_proactively(update, page)

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
            if not await self._ensure_credits(page, update, refresh_if_needed=True):
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

            # === WAIT FOR RESULT & CLICK DOWNLOAD ===
            logger.info("⏳ Waiting for generation to complete...")
            
            # Wait for any image to appear (data URL or result class)
            result_found = False
            download_btn = None
            start_time = asyncio.get_event_loop().time()
            timeout = 30  # max 30 seconds
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                logger.info(f"⏳ Checking for result... ({elapsed}s)")
                
                # Try to find the download button
                download_btn = await self._find_download_button(page)
                if download_btn:
                    logger.info("✅ Download button found!")
                    result_found = True
                    break
                
                # Also check for any new image (data URL)
                images = await page.locator('img[src^="data:image"]').all()
                if images:
                    logger.info(f"✅ Found {len(images)} data images")
                    # Try to get the image directly
                    for img in images:
                        box = await img.bounding_box()
                        if box and box['width'] > 50 and box['height'] > 50:
                            src = await img.get_attribute('src')
                            if src and src.startswith('data:image'):
                                logger.info("✅ Found data image, extracting...")
                                match = re.match(r'data:image/([a-zA-Z]+);base64,([A-Za-z0-9+/=]+)', src)
                                if match:
                                    image_data = base64.b64decode(match.group(2))
                                    await browser.close()
                                    return {
                                        "status": "success",
                                        "image": base64.b64encode(image_data).decode(),
                                        "method": "data_image",
                                        "size": len(image_data)
                                    }
                    # If we found images but no download button, try clicking one
                    if not download_btn:
                        try:
                            await images[0].click()
                            logger.info("🖱️ Clicked on result image to trigger download")
                            await asyncio.sleep(2)
                            download_btn = await self._find_download_button(page)
                            if download_btn:
                                result_found = True
                                break
                        except:
                            pass
                
                await asyncio.sleep(1)
            
            # If we found a download button, click it and download
            if download_btn:
                logger.info("🔄 Clicking download button...")
                await download_btn.click()
                await asyncio.sleep(2)
                
                # Get the downloaded content using page.expect_download
                try:
                    async with page.expect_download(timeout=10000) as download_info:
                        await download_btn.click()
                    download = await download_info.value
                    downloaded_bytes = await download.read()
                    logger.info(f"✅ Downloaded image: {download.suggested_filename}, size: {len(downloaded_bytes)} bytes")
                    await browser.close()
                    return {
                        "status": "success",
                        "image": base64.b64encode(downloaded_bytes).decode(),
                        "method": "download",
                        "size": len(downloaded_bytes)
                    }
                except Exception as e:
                    logger.warning(f"Download failed: {e}")
            
            # === FALLBACK: Take screenshot ===
            logger.warning("ℹ️ No result image found, taking screenshot as fallback")
            screenshot_bytes = await page.screenshot(full_page=True)
            await browser.close()
            return {
                "status": "success",
                "image": base64.b64encode(screenshot_bytes).decode(),
                "method": "screenshot_fallback",
                "size": len(screenshot_bytes)
            }
