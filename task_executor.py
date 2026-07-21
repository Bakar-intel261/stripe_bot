import logging
import base64
import asyncio
import re
import random
import json
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
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"
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
                if p.startswith('http://') or p.startswith('https://'):
                    valid.append(p)
                else:
                    valid.append(f"http://{p}")
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

    async def _log_storage(self, page):
        logger.info("📦 LocalStorage contents:")
        local_storage = await page.evaluate("() => JSON.stringify(localStorage)")
        try:
            ls = json.loads(local_storage)
            for key, value in ls.items():
                logger.info(f"  {key}: {value[:100]}..." if len(value) > 100 else f"  {key}: {value}")
        except:
            logger.info(f"  Raw: {local_storage[:200]}...")

        user_info = await page.evaluate("() => localStorage.getItem('user-info')")
        if user_info:
            try:
                ui = json.loads(user_info)
                logger.info(f"👤 user-info: {ui}")
                if 'credits' in ui:
                    logger.info(f"💰 Credits from user-info: {ui['credits']}")
                if 'effectiveCycles' in ui:
                    logger.info(f"🔄 effectiveCycles: {ui['effectiveCycles']}")
            except:
                logger.info(f"👤 user-info (raw): {user_info}")

    async def _intercept_requests(self, page):
        async def log_request(request):
            if '/api/' in request.url:
                logger.info(f"🌐 Request: {request.method} {request.url}")
        async def log_response(response):
            if '/api/' in response.url:
                logger.info(f"🌐 Response: {response.status} {response.url}")
                if '/api/account/detail' in response.url:
                    try:
                        body = await response.text()
                        logger.info(f"📄 Response body: {body[:500]}...")
                    except:
                        pass
        page.on('request', log_request)
        page.on('response', log_response)

    async def _get_credits(self, page):
        # First try localStorage
        user_info = await page.evaluate("() => localStorage.getItem('user-info')")
        if user_info:
            try:
                ui = json.loads(user_info)
                if 'credits' in ui and ui['credits'] > 0:
                    return ui['credits']
            except:
                pass
        # Fallback to DOM
        coin = page.locator('img[alt*="coin"], img[src*="coin"], svg[alt*="coin"]').first
        if await coin.count() > 0:
            parent = coin.locator('..')
            if await parent.count() > 0:
                text = await parent.text_content()
                numbers = re.findall(r'\d+', text)
                if numbers:
                    return int(numbers[0])
        page_text = await page.content()
        match = re.search(r'Credits?\s*:?\s*(\d+)', page_text, re.I)
        if match:
            return int(match.group(1))
        return None

    async def process_photo(self, update, image_bytes):
        if not self.proxies:
            await self._fetch_proxies()
        attempts = 3
        for attempt in range(attempts):
            proxy = None
            if self.proxies:
                proxy_str = random.choice(self.proxies)
                proxy = {"server": proxy_str}
                logger.info(f"Attempt {attempt+1}: Using proxy: {proxy_str}")
            else:
                logger.warning("No proxies available, running without proxy.")

            try:
                await self._run_browser(update, image_bytes, proxy)
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                if proxy and proxy_str in self.proxies:
                    self.proxies.remove(proxy_str)
                await asyncio.sleep(3)

        logger.warning("All proxy attempts failed. Running without proxy as last resort.")
        await self._run_browser(update, image_bytes, None)

    async def _run_browser(self, update, image_bytes, proxy):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"
        width, height = 412, 915
        viewport_w, viewport_h = 411, 800
        locale = getattr(fp, 'locale', 'en-US')
        timezone = getattr(fp, 'timezone', 'America/New_York')
        device_scale = 1.75
        logger.info(f"Using mobile fingerprint: {ua[:50]}..., {width}x{height}")

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
                f"--window-size={viewport_w},{viewport_h}"
            ]
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
                args=args,
                proxy=proxy,
                chromium_sandbox=False
            )
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": viewport_w, "height": viewport_h},
                locale=locale,
                timezone_id=timezone,
                device_scale_factor=device_scale,
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
                Object.defineProperty(navigator, 'platform', { get: () => 'Android' });
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

            await self._intercept_requests(page)

            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await self._human_wait(3, 5)

            # ---- FIRST: CLICK AGE GATE ----
            logger.info("🔍 Looking for age verification button...")
            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await self._human_wait(5, 8)  # wait for credits to be allocated
                await self._send_screenshot(update, page, "✅ Age verification accepted")
            else:
                logger.info("ℹ️ No age verification needed")

            # ---- THEN CHECK CREDITS ----
            await self._log_storage(page)
            credits = await self._get_credits(page)
            logger.info(f"💰 Credits detected: {credits}")

            # If still 0, try refreshing via homepage and back
            if credits is None or credits < 10:
                logger.warning("Credits insufficient, refreshing...")
                await page.goto("https://www.swapfaces.ai")
                await self._human_wait(3, 5)
                await page.goto(target_url)
                await self._human_wait(5, 7)
                await self._log_storage(page)
                credits = await self._get_credits(page)
                logger.info(f"💰 Credits after refresh: {credits}")

            if credits is not None and credits >= 10:
                logger.info("✅ Credits OK. Proceeding with upload.")
            else:
                logger.error("❌ No credits. Aborting.")
                await self._send_screenshot(update, page, "⛔ No credits")
                await update.message.reply_text("No free credits available. Please try a different proxy or later.")
                await browser.close()
                return

            # ---- CONTINUE WITH UPLOAD, CONSENT, PROMPT, GENERATE ----
            # (same as before, but we ensure these steps are reached only if credits > 0)
            # ... (copy upload, consent, prompt, generate from previous version)
            # We'll just put a placeholder here to avoid duplication; we'll include the full flow.

            logger.info("🔍 Looking for upload area...")
            upload_btn = page.locator('button.sf-image-to-image__upload').first
            await upload_btn.wait_for(state="visible", timeout=15000)
            logger.info("✅ Upload button found and visible")

            try:
                async with page.expect_file_chooser(timeout=15000) as fc_info:
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

            logger.info("🔍 Looking for generate button...")
            generate_btn = page.locator('button.sf-image-to-image__generate-btn, button:has-text("Generate")').first
            await generate_btn.wait_for(state="visible", timeout=10000)
            if await generate_btn.get_attribute('disabled'):
                logger.warning("⚠️ Generate button is disabled, aborting")
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
                caption = "⏱️ Timeout – no result after 60s"
            await self._send_screenshot(update, page, caption)
            await browser.close()
