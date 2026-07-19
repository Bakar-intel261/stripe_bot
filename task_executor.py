import logging
import base64
from playwright.async_api import async_playwright
from chrome_fingerprints import FingerprintGenerator

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.fp_gen = FingerprintGenerator()

    async def upload_and_screenshot(self, image_bytes: bytes) -> dict:
        """Upload image to aiundress.cc, click crop confirm, then screenshot."""
        target_url = "https://aiundress.cc"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        width = getattr(fp.screen_resolution, 'width', 1920) if hasattr(fp, 'screen_resolution') else 1920
        height = getattr(fp.screen_resolution, 'height', 1080) if hasattr(fp, 'screen_resolution') else 1080

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(user_agent=ua, viewport={"width": width, "height": height})
            page = await context.new_page()

            logger.info("🌐 Navigating to upload page")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)

            file_input = page.locator('input[type="file"]').first
            if await file_input.count() == 0:
                raise Exception("No file input found")

            logger.info("📤 Uploading image...")
            await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])

            # Wait for crop UI to appear
            logger.info("⏳ Waiting for crop UI...")
            await page.wait_for_timeout(3000)

            # Try to find and click crop confirm button
            crop_btn = None
            for selector in [
                'button:has-text("Confirm")',
                'button:has-text("Crop")',
                'button:has-text("Apply")',
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'button:has-text("Submit")',
                'button:has-text("OK")',
                'div[role="button"]:has-text("Confirm")',
                'div[role="button"]:has-text("Crop")',
                'button[class*="crop"]',
                'button[class*="confirm"]'
            ]:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        crop_btn = element
                        logger.info(f"✅ Found crop button with selector: {selector}")
                        break
                except:
                    continue

            if crop_btn:
                logger.info("🔄 Clicking crop confirm button...")
                await crop_btn.click(timeout=5000)
                await page.wait_for_timeout(3000)  # let it process
            else:
                logger.warning("⚠️ No crop confirm button found, continuing")

            screenshot_bytes = await page.screenshot(full_page=True)
            await browser.close()

            return {
                "status": "success",
                "screenshot": base64.b64encode(screenshot_bytes).decode(),
                "size": len(screenshot_bytes)
            }
