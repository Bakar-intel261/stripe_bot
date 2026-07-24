import logging
import base64
import asyncio
import re
import random
import time
import requests
from io import BytesIO
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator
from PIL import Image

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()
        logger.info("🚀 TaskExecutor initialized")

    def _resize_image(self, image_bytes, max_dim=1280):
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
                await locator.click()
                return True
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            await page.mouse.click(x, y)
            return True
        except Exception as e:
            logger.error(f"Click error: {e}")
            return False

    async def _human_wait(self, min_sec=2, max_sec=3):
        delay = random.randint(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def _get_credits(self, page):
        coin = page.locator('img[alt*="coin"], img[src*="coin"], svg[alt*="coin"]').first
        if await coin.count() > 0:
            parent = coin.locator('..')
            if await parent.count() > 0:
                text = await parent.text_content()
                numbers = re.findall(r'\d+', text)
                if numbers:
                    return int(numbers[0])
        credit_elem = page.locator('span[class*="credit"], div[class*="credit"], .sf-cost-credits').first
        if await credit_elem.count() > 0:
            text = await credit_elem.text_content()
            numbers = re.findall(r'\d+', text)
            if numbers:
                return int(numbers[0])
        page_text = await page.content()
        match = re.search(r'Credits?\s*:?\s*(\d+)', page_text, re.I)
        if match:
            return int(match.group(1))
        return None

    async def _ensure_credits(self, page, update):
        credits = await self._get_credits(page)
        if credits is None:
            return False
        return credits >= 10

    async def _find_download_button(self, page):
        download_links = await page.locator('a[download]').all()
        if download_links:
            for link in download_links:
                href = await link.get_attribute('href')
                if href and ('.jpeg' in href or '.png' in href or '.jpg' in href):
                    return link
            return download_links[0]
        image_links = await page.locator('a[href*=".jpeg"], a[href*=".png"], a[href*=".jpg"], a[href*=".webp"]').all()
        if image_links:
            return image_links[0]
        return None

    # --- ORIGINAL process_photo (unchanged) ---
    async def process_photo(self, update, image_bytes, status_msg=None):
        start_time = time.time()
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 ...')
        width, height = 1920, 1080
        locale = getattr(fp, 'locale', 'en-US')
        timezone = getattr(fp, 'timezone', 'America/New_York')

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": width, "height": height},
                locale=locale,
                timezone_id=timezone
            )
            page = await context.new_page()
            # stealth init
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(window, 'chrome', { value: { runtime: {} } });
            """)
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except:
                pass

            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await self._human_wait(2,3)
            await self._send_screenshot(update, page, "🌐 Landing page")

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                await self._click_element_center(page, age_btn, "Age verification")
                await self._human_wait(2,3)
                await self._send_screenshot(update, page, "✅ Age verification accepted")

            upload_btn = page.locator('button.sf-image-to-image__upload').first
            await upload_btn.wait_for(state="visible", timeout=15000)
            async with page.expect_file_chooser(timeout=15000) as fc_info:
                await upload_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            await self._human_wait(2,3)
            await self._send_screenshot(update, page, "📤 After upload")

            consent_card = page.locator('div.mi-upload-consent__card').first
            try:
                await consent_card.wait_for(state="visible", timeout=8000)
                consent_block = consent_card.locator('div.mi-upload-consent__consent').first
                if await consent_block.count() > 0:
                    await self._click_element_center(page, consent_block, "Consent block")
                    await self._human_wait(1,2)
                agree_btn = consent_card.locator('button:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    await self._click_element_center(page, agree_btn, "Agree button")
                    await self._human_wait(2,3)
            except:
                pass

            prompt_input = page.locator('textarea, input[type="text"]').first
            if await prompt_input.count() > 0:
                await prompt_input.fill("Remove clothes")
                await self._human_wait(1,2)
                await self._send_screenshot(update, page, "📝 Prompt entered")

            # check credits (optional)
            if not await self._ensure_credits(page, update):
                await browser.close()
                return {"status": "error", "error": "Insufficient credits"}

            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            is_disabled = await generate_btn.get_attribute('disabled')
            if is_disabled:
                for _ in range(10):
                    await asyncio.sleep(1)
                    if not await generate_btn.get_attribute('disabled'):
                        break
                else:
                    await browser.close()
                    return {"status": "error", "error": "Generate button never enabled"}
            try:
                await page.evaluate('(btn) => btn.click()', generate_btn)
            except:
                await generate_btn.click(force=True)
            await self._human_wait(2,3)
            await self._send_screenshot(update, page, "⚡ Generate clicked")

            await asyncio.sleep(10)  # wait for generation

            download_btn = None
            for _ in range(15):
                download_btn = await self._find_download_button(page)
                if download_btn:
                    break
                await asyncio.sleep(1)

            if download_btn:
                try:
                    href = await download_btn.get_attribute('href')
                    if href:
                        resp = requests.get(href, timeout=30)
                        if resp.status_code == 200:
                            image_data = resp.content
                            total_time = int(time.time() - start_time)
                            await update.message.reply_photo(
                                photo=BytesIO(image_data),
                                caption=f"✨ Your generated image!\n⏱️ {total_time}s"
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
                    logger.error(f"Download failed: {e}")

            # fallback screenshot
            screenshot = await page.screenshot(full_page=True, type="jpeg", quality=95)
            await browser.close()
            total_time = int(time.time() - start_time)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption=f"⚠️ Screenshot (download failed)\n⏱️ {total_time}s")
            return {
                "status": "success",
                "image": base64.b64encode(screenshot).decode(),
                "method": "screenshot_fallback",
                "size": len(screenshot),
                "time": total_time
            }

    # --- NEW METHOD for Colab ---
    async def process_image_for_colab(self, user_id: str, image_bytes: bytes, bot_token: str):
        """Same logic as process_photo but sends messages via HTTP to Telegram."""
        import requests
        start_time = time.time()
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 ...')
        width, height = 1920, 1080
        locale = getattr(fp, 'locale', 'en-US')
        timezone = getattr(fp, 'timezone', 'America/New_York')

        async def send_message(text):
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": user_id, "text": text, "parse_mode": "Markdown"}
                requests.post(url, json=payload, timeout=5)
            except:
                pass

        async def send_photo(image_data, caption=""):
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                files = {"photo": BytesIO(image_data)}
                data = {"chat_id": user_id, "caption": caption}
                requests.post(url, files=files, data=data, timeout=10)
            except:
                pass

        await send_message("🔄 Step 1/4: Starting browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": width, "height": height},
                locale=locale,
                timezone_id=timezone
            )
            page = await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(window, 'chrome', { value: { runtime: {} } });
            """)
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except:
                pass

            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await self._human_wait(2,3)

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                await self._click_element_center(page, age_btn, "Age verification")
                await self._human_wait(2,3)
                await send_message("✅ Age verification passed")

            await send_message("📤 Step 2/4: Uploading image...")
            upload_btn = page.locator('button.sf-image-to-image__upload').first
            await upload_btn.wait_for(state="visible", timeout=15000)
            async with page.expect_file_chooser(timeout=15000) as fc_info:
                await upload_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            await self._human_wait(2,3)

            consent_card = page.locator('div.mi-upload-consent__card').first
            try:
                await consent_card.wait_for(state="visible", timeout=8000)
                consent_block = consent_card.locator('div.mi-upload-consent__consent').first
                if await consent_block.count() > 0:
                    await self._click_element_center(page, consent_block, "Consent block")
                    await self._human_wait(1,2)
                agree_btn = consent_card.locator('button:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    await self._click_element_center(page, agree_btn, "Agree button")
                    await self._human_wait(2,3)
            except:
                pass

            prompt_input = page.locator('textarea, input[type="text"]').first
            if await prompt_input.count() > 0:
                await prompt_input.fill("Remove clothes")
                await self._human_wait(1,2)

            await send_message("🔄 Step 3/4: Generating (~20 seconds)...")
            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            is_disabled = await generate_btn.get_attribute('disabled')
            if is_disabled:
                for _ in range(10):
                    await asyncio.sleep(1)
                    if not await generate_btn.get_attribute('disabled'):
                        break
                else:
                    await send_message("❌ Generate button never enabled")
                    await browser.close()
                    return None
            try:
                await page.evaluate('(btn) => btn.click()', generate_btn)
            except:
                await generate_btn.click(force=True)
            await self._human_wait(2,3)

            await asyncio.sleep(10)

            download_btn = None
            for _ in range(15):
                download_btn = await self._find_download_button(page)
                if download_btn:
                    break
                await asyncio.sleep(1)

            if download_btn:
                try:
                    href = await download_btn.get_attribute('href')
                    if href:
                        resp = requests.get(href, timeout=30)
                        if resp.status_code == 200:
                            image_data = resp.content
                            total_time = int(time.time() - start_time)
                            await send_photo(image_data, f"✨ Your generated image!\n⏱️ {total_time}s")
                            await browser.close()
                            return image_data
                except:
                    pass

            # fallback screenshot
            screenshot = await page.screenshot(full_page=True, type="jpeg", quality=95)
            await browser.close()
            total_time = int(time.time() - start_time)
            await send_photo(screenshot, f"⚠️ Screenshot (download failed)\n⏱️ {total_time}s")
            return screenshot
