import logging
import base64
import asyncio
import re
import random
import aiohttp
from io import BytesIO
from PIL import Image
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()
        self.proxies = []

    async def _fetch_proxies(self):
        proxy_urls = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
            "https://www.proxy-list.download/api/v1/get?type=http",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        ]
        proxy_list = []
        for url in proxy_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            candidates = [line.strip() for line in text.splitlines() if line.strip()]
                            proxy_list.extend(candidates)
                            logger.info(f"Fetched {len(candidates)} proxies from {url}")
                            if len(proxy_list) >= 50:
                                break
            except Exception as e:
                logger.warning(f"Failed to fetch proxies from {url}: {e}")
        valid = []
        seen = set()
        for p in proxy_list:
            if ':' in p and p not in seen and ' ' not in p:
                seen.add(p)
                valid.append(p)
        self.proxies = valid
        logger.info(f"Total proxies available: {len(self.proxies)}")
        return self.proxies

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

    async def _simulate_human_behavior(self, page):
        logger.info("👤 Simulating human behavior...")
        await page.evaluate("window.scrollBy(0, 300)")
        await asyncio.sleep(random.uniform(1, 2))
        await page.evaluate("window.scrollBy(0, -150)")
        await asyncio.sleep(random.uniform(1, 2))
        for _ in range(3):
            x = random.randint(100, 1800)
            y = random.randint(100, 900)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.5, 1.5))
        try:
            style_item = page.locator('div.sf-image-to-image__style__item').first
            if await style_item.count() > 0:
                await style_item.hover()
                await asyncio.sleep(1)
        except:
            pass
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

    async def _refresh_credits_proactively(self, update, page):
        logger.info("🪙 Attempting to trigger free credits...")
        credit_link = page.locator('a:has-text("Credits")').first
        if await credit_link.count() == 0:
            credit_link = page.locator('button:has-text("Credits")').first
        if await credit_link.count() == 0:
            logger.warning("⚠️ Credits link not found")
        else:
            await credit_link.click()
            await self._human_wait(4, 6)
            await self._send_screenshot(update, page, "🪙 Credits page")
            await page.go_back()
            await self._human_wait(5, 8)
            await self._send_screenshot(update, page, "🔙 Back after Credits")

        logger.info("🏠 Navigating to homepage and back...")
        current_url = page.url
        await page.goto("https://www.swapfaces.ai")
        await self._human_wait(5, 8)
        await self._send_screenshot(update, page, "🏠 Homepage")
        await page.goto(current_url)
        await self._human_wait(10, 15)
        await self._send_screenshot(update, page, "🔙 Back after homepage")
        return True

    async def _get_credits(self, page):
        coin = page.locator('img[alt*="coin"], img[src*="coin"], svg[alt*="coin"]').first
        if await coin.count() > 0:
            parent = coin.locator('..')
            if await parent.count() > 0:
                text = await parent.text_content()
                logger.info(f"Text from coin parent: {text}")
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

    async def process_photo(self, update, image_bytes):
        for attempt in range(3):
            proxy = None
            if not self.proxies:
                await self._fetch_proxies()
            if self.proxies:
                proxy_str = random.choice(self.proxies)
                proxy = {"server": f"http://{proxy_str}"}
                logger.info(f"Using proxy: {proxy_str}")
            else:
                logger.warning("No proxies available, running without proxy.")

            try:
                await self._run_browser(update, image_bytes, proxy)
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed with proxy {proxy_str if proxy else 'none'}: {e}")
                if proxy and proxy_str in self.proxies:
                    self.proxies.remove(proxy_str)
                await asyncio.sleep(2)

        logger.warning("All proxy attempts failed, running without proxy.")
        await self._run_browser(update, image_bytes, None)

    async def _run_browser(self, update, image_bytes, proxy):
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
            args = [
                "--no-sandbox",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-first-run",
                "--safebrowsing-disable-auto-update",
                f"--window-size={width},{height}"
            ]
            # Use a real Chrome binary (channel="chrome")
            browser = await p.chromium.launch(
                channel="chrome",  # <-- KEY CHANGE: use real Chrome
                headless=True,
                args=args,
                proxy=proxy,
                chromium_sandbox=False
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
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                const screenProps = { availWidth: window.innerWidth, availHeight: window.innerHeight };
                Object.defineProperty(window.screen, 'availWidth', { get: () => screenProps.availWidth });
                Object.defineProperty(window.screen, 'availHeight', { get: () => screenProps.availHeight });
                Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
                Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight });
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                if (!navigator.connection) {
                    Object.defineProperty(navigator, 'connection', { value: { rtt: 50, downlink: 10 } });
                }
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
            await self._human_wait(5, 7)
            await self._send_screenshot(update, page, "🌐 Landing page")

            await self._simulate_human_behavior(page)

            logger.info("⏳ Waiting 10 seconds before clicking age verification...")
            await asyncio.sleep(10)

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                logger.info("⏳ Waiting 10 seconds after age verification...")
                await asyncio.sleep(10)
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
            if not await self._ensure_credits(page, update):
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
