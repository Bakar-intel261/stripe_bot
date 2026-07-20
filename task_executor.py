import logging
import base64
import asyncio
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

    async def _click_element_center(self, page, locator, description="element"):
        try:
            box = await locator.bounding_box()
            if not box:
                logger.warning(f"⚠️ Could not get bounding box for {description}")
                await locator.click()
                return
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            logger.info(f"📍 Clicking {description} at coordinates ({x:.1f}, {y:.1f})")
            await page.mouse.click(x, y)
            return True
        except Exception as e:
            logger.error(f"❌ Error clicking {description}: {e}")
            return False

    async def _find_file_input(self, page):
        """Find file input using multiple strategies"""
        # Strategy 1: Direct selector
        for sel in ['input[type="file"]', 'input[accept*="image"]']:
            element = page.locator(sel).first
            if await element.count() > 0:
                logger.info(f"✅ Found file input with selector: {sel}")
                return element
        # Strategy 2: Click upload button and wait for input to appear
        upload_btns = page.locator('button:has-text("Upload"), div:has-text("Upload"), a:has-text("Upload"), div[class*="upload"]')
        if await upload_btns.count() > 0:
            logger.info("🔍 Found upload button, clicking to reveal file input...")
            await upload_btns.first.click()
            await page.wait_for_timeout(1500)
            # Check again
            element = page.locator('input[type="file"]').first
            if await element.count() > 0:
                logger.info("✅ Found file input after clicking upload button")
                return element
        # Strategy 3: JavaScript to find hidden file input
        logger.info("🔍 Using JavaScript to locate hidden file input...")
        js_result = await page.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > 0) {
                    // Return a unique identifier for the first one
                    for (let inp of inputs) {
                        if (inp.offsetParent !== null || inp.style.display !== 'none' || inp.style.visibility !== 'hidden') {
                            return inp.outerHTML;
                        }
                    }
                    return inputs[0].outerHTML; // fallback
                }
                return null;
            }
        """)
        if js_result:
            logger.info("✅ JavaScript found a file input")
            # We can't directly use the element from evaluate, but we can use page.locator with an attribute
            # We'll just use the first visible one again
            element = page.locator('input[type="file"]').first
            if await element.count() > 0:
                return element
        raise Exception("No file input found after all strategies")

    async def process_photo(self, update, image_bytes):
        target_url = "https://www.swapfaces.ai/undress-ai-remover"
        fp = self.fp_gen.get_fingerprint()
        ua = getattr(fp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        width = 1920
        height = 1080

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(user_agent=ua, viewport={"width": width, "height": height})
            page = await context.new_page()

            logger.info("===== Starting process =====")

            # ---- Step 1: Landing & Age Verification ----
            logger.info("🌐 Navigating to swapfaces.ai")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)

            age_btn = page.locator('button:has-text("I Am 18 or Older")').first
            if await age_btn.count() > 0:
                logger.info("✅ Age verification found, clicking via coordinates...")
                await self._click_element_center(page, age_btn, "Age verification button")
                await page.wait_for_timeout(3000)
            else:
                age_btn = page.locator('button:has-text("I Am 18")').first
                if await age_btn.count() > 0:
                    logger.info("✅ Found age button with 'I Am 18', clicking...")
                    await self._click_element_center(page, age_btn, "Age verification button (fallback)")
                    await page.wait_for_timeout(3000)
                else:
                    logger.info("ℹ️ No age verification needed")

            # ---- Screenshot 1: Landing ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="🌐 Landing page (age accepted)")

            # ---- Step 2: Upload ----
            logger.info("🔍 Searching for file input...")
            file_input = await self._find_file_input(page)
            logger.info("✅ Found file input element")
            await file_input.set_input_files(files=[{"name": "image.jpg", "mimeType": "image/jpeg", "buffer": image_bytes}])
            logger.info("📤 Image uploaded")
            await page.wait_for_timeout(3000)

            # ---- Step 3: Consent Popup ----
            consent_checkbox = page.locator('input[type="checkbox"]').first
            if await consent_checkbox.count() > 0:
                logger.info("✅ Consent popup detected, checking checkbox...")
                await consent_checkbox.click()
                await page.wait_for_timeout(500)
                agree_btn = page.locator('button:has-text("Agree & continue"), div:has-text("Agree & continue")').first
                if await agree_btn.count() > 0:
                    logger.info("✅ Clicking Agree & continue via coordinates...")
                    await self._click_element_center(page, agree_btn, "Agree & continue button")
                    await page.wait_for_timeout(3000)
            else:
                logger.info("ℹ️ No consent popup detected")

            # ---- Step 4: Wait for upload to complete ----
            logger.info("⏳ Waiting for upload to complete...")
            await page.wait_for_timeout(3000)

            # ---- Step 5: Enter prompt ----
            prompt_input = page.locator('textarea, input[type="text"], div[contenteditable="true"]').first
            if await prompt_input.count() > 0:
                logger.info("✏️ Entering prompt: 'Remove clothes'")
                await prompt_input.fill("Remove clothes")
                await page.wait_for_timeout(1000)
            else:
                logger.warning("⚠️ No prompt input found, continuing anyway")

            # ---- Screenshot 2: After upload and prompt ----
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📤 Uploaded & prompt entered")

            # ---- Step 6: Click generate ----
            generate_btn = page.locator('button:has-text("Generate"), div:has-text("Generate"), input[value*="Generate"]').first
            if await generate_btn.count() == 0:
                raise Exception("No generate button found")
            logger.info("🔄 Clicking generate button via coordinates...")
            await self._click_element_center(page, generate_btn, "Generate button")
            await page.wait_for_timeout(2000)

            # ---- Step 7: Wait for result (up to 60 seconds) with logging ----
            logger.info("⏳ Waiting for result image... (max 60s)")
            result_img = None
            start_time = asyncio.get_event_loop().time()
            for i in range(60):
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                logger.info(f"🔍 Check {i+1}: Looking for result image... (elapsed {elapsed}s)")
                images = await page.locator('img[src^="data:image"], img[class*="result"], img[class*="output"], img[class*="generated"]').all()
                logger.info(f"   Found {len(images)} candidate image(s)")
                for idx, img in enumerate(images):
                    box = await img.bounding_box()
                    src = await img.get_attribute('src') or ''
                    logger.info(f"   Image {idx}: src={src[:50]}..., box={box}")
                    if box and box['width'] > 0 and box['height'] > 0:
                        result_img = img
                        logger.info(f"✅ Result image detected at {elapsed}s (width={box['width']}, height={box['height']})")
                        break
                if result_img:
                    break
                page_text = await page.content()
                if "credit" in page_text.lower() or "not enough" in page_text.lower():
                    logger.warning("⚠️ Credit/error message detected: " + page_text[:200])
                await asyncio.sleep(1)

            # ---- Step 8: Final screenshot ----
            await page.wait_for_timeout(2000)
            screenshot = await page.screenshot(full_page=True)
            screenshot = self._resize_image(screenshot)
            if result_img:
                caption = f"✅ Final result (generated at {elapsed}s)"
            else:
                page_text = await page.content()
                if "credit" in page_text.lower() or "not enough" in page_text.lower():
                    caption = "⚠️ Credit/error detected – result may not be generated"
                else:
                    caption = "⏱️ Timeout – no result after 60s"
            await update.message.reply_photo(photo=BytesIO(screenshot), caption=caption)
            logger.info(f"===== Process finished. Result found: {result_img is not None} =====")

            await browser.close()
