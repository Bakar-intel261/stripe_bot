import asyncio
import logging
import base64
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        # No donut_manager needed – we connect directly via CDP
        pass

    async def visit_and_screenshot(self, url: str) -> dict:
        try:
            async with async_playwright() as p:
                # Connect to the already‑running Chrome via CDP
                browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                if browser.contexts:
                    context = browser.contexts[0]
                    pages = context.pages
                    if pages:
                        page = pages[0]
                    else:
                        page = await context.new_page()
                else:
                    context = await browser.new_context()
                    page = await context.new_page()

                logger.info(f"🌐 Navigating to: {url}")
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                screenshot_bytes = await page.screenshot(full_page=True)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                title = await page.title()

                await browser.close()

                return {
                    "status": "success",
                    "title": title,
                    "url": url,
                    "screenshot": screenshot_b64,
                    "size": len(screenshot_bytes)
                }

        except Exception as e:
            logger.error(f"❌ Task failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
