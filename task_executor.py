import logging
import base64
import asyncio
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()

    async def _wait_for_enabled(self, element, timeout=30):
        for _ in range(timeout * 2):
            disabled = await element.get_attribute('disabled')
            if not disabled:
                return True
            await asyncio.sleep(0.5)
        return False

    async def _wait_for_result_image(self, page, timeout=60):
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            images = await page.locator('img[src^="data:image"], img[class*="result"], img[class*="output"], img[class*="generated"]').all()
            if images:
                for img in images:
                    box = await img.bounding_box()
                    if box and box['width'] > 0 and box['height'] > 0:
                        return img
            await asyncio.sleep(1)
        return None

    async def _screenshot(self, page, label):
        """Take screenshot and return base64 string."""
        bytes = await page.screenshot(full_page=True)
        logger.info(f"📸 Screenshot taken: {label}")
        return base64.b64encode(bytes).decode()

    async def upload_and_screenshot(self, image_bytes: bytes) -> dict:
        """Full workflow: capture each step."""
        target_url = "https://aiundress.cc"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        width = getattr(fp.screen_resolution, 'width', 1920) if hasattr(fp, 'screen_resolution') else 1920
        height = getattr(fp.screen_resolution, 'height', 1080) if hasattr(fp, 'screen_resolution') else 1080

        screenshots = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(user_agent=ua, viewport={"width": width, "height": height})
            page = await context.new_page()

            # 1. Landing
            logger.info("🌐 Navigating to upload page")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            screenshots['landing'] = await self._screenshot(page, 'landing')

            # 2. Upload
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() == 0:
                raise Exception("No file input found")
            logger.info("📤 Uploading image...")
            await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            await page.wait_for_timeout(2000)
            screenshots['upload'] = await self._screenshot(page, 'upload')

            # 3. Crop confirm (if present)
            await page.wait_for_timeout(2000)
            crop_btn = None
            for selector in [
                'button:has-text("Confirm")', 'button:has-text("Crop")',
                'button:has-text("Apply")', 'button:has-text("Next")',
                'div[role="button"]:has-text("Confirm")',
                'button[class*="crop"]', 'button[class*="confirm"]'
            ]:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        crop_btn = element
                        break
                except:
                    continue
            if crop_btn:
                logger.info("🔄 Clicking crop confirm...")
                await crop_btn.click(timeout=5000)
                await page.wait_for_timeout(2000)
                screenshots['crop'] = await self._screenshot(page, 'crop')
            else:
                screenshots['crop'] = screenshots['upload']  # same as upload

            # 4. Wait for generate button to be enabled
            generate_btn = page.locator('button:has-text("Generate"), button:has-text("Undress"), button:has-text("Start"), button[class*="generate"]').first
            if await generate_btn.count() == 0:
                raise Exception("No generate button found")
            logger.info("⏳ Waiting for generate button to become active...")
            if not await self._wait_for_enabled(generate_btn, timeout=30):
                logger.warning("Generate button never became enabled, proceeding anyway")
            else:
                logger.info("✅ Generate button is active")

            # 5. Click generate and capture "generating" state
            logger.info("🔄 Clicking generate button...")
            await generate_btn.click(timeout=10000)
            await page.wait_for_timeout(3000)  # let generation start
            screenshots['generating'] = await self._screenshot(page, 'generating')

            # 6. Wait for result image (or status change)
            logger.info("⏳ Waiting for result image...")
            result_img = await self._wait_for_result_image(page, timeout=60)
            if result_img:
                logger.info("✅ Result image found")
            else:
                logger.warning("No result image found, capturing current state")

            # 7. Final screenshot
            await page.wait_for_timeout(2000)  # let final render settle
            screenshots['result'] = await self._screenshot(page, 'result')

            await browser.close()

            # Return list of images in order
            image_order = ['landing', 'upload', 'crop', 'generating', 'result']
            return {
                "status": "success",
                "images": [screenshots[key] for key in image_order],
                "labels": image_order,
                "sizes": [len(base64.b64decode(screenshots[key])) for key in image_order]
            }
