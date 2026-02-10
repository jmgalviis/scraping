import asyncio
import logging
import time
from playwright.async_api import async_playwright
from csv_manager import CSVManager
from scraping import GoofishScraper
from config import (
    PROXY_CONFIG_PLAYWRIGHT,
    GOOFISH_COOKIES,
    USER_AGENT,
    DEFAULT_CONCURRENCY,
    REQUEST_DELAY_SECONDS,
)

logger = logging.getLogger("batch_scraper")
logging.basicConfig(level=logging.INFO)

# Convert cookie dict to Playwright list format
PLAYWRIGHT_COOKIES = [
    {
        "name": name,
        "value": value,
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": name in ("_samesite_flag_", "cookie2"),
        "sameSite": "None",
    }
    for name, value in GOOFISH_COOKIES.items()
]


class BatchScraper:
    """
    Orchestrates bulk scraping of 50k Goofish product URLs.
    Uses a single Playwright browser with concurrent pages for efficiency.
    Each page navigates to a product URL and intercepts the API response.
    """

    def __init__(self, concurrency: int = DEFAULT_CONCURRENCY):
        self._concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._csv = CSVManager()
        self._running = False
        self._cancel_event = asyncio.Event()
        self._cookies = list(PLAYWRIGHT_COOKIES)
        self._stats = {
            "started_at": None,
            "completed": 0,
            "failed": 0,
            "token_errors": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> dict:
        csv_stats = self._csv.stats
        elapsed = 0
        rate = 0.0
        if self._stats["started_at"]:
            elapsed = time.time() - self._stats["started_at"]
            done = self._stats["completed"] + self._stats["failed"]
            rate = round(done / elapsed, 2) if elapsed > 0 else 0.0
        return {
            **csv_stats,
            **self._stats,
            "running": self._running,
            "elapsed_seconds": round(elapsed, 1),
            "items_per_second": rate,
        }

    def update_cookies(self, new_cookies: dict):
        """Hot-swap cookies (e.g. after manual token refresh)."""
        self._cookies = [
            {
                "name": name,
                "value": value,
                "domain": ".goofish.com",
                "path": "/",
                "secure": True,
                "httpOnly": name in ("_samesite_flag_", "cookie2"),
                "sameSite": "None",
            }
            for name, value in new_cookies.items()
        ]

    async def run(self):
        """Main entry point: load CSV, launch browser, process all pending items."""
        if self._running:
            raise RuntimeError("Batch is already running")

        self._running = True
        self._cancel_event.clear()
        self._stats["started_at"] = time.time()
        self._stats["completed"] = 0
        self._stats["failed"] = 0
        self._stats["token_errors"] = 0

        try:
            await self._csv.load()
            pending = self._csv.get_pending_items()
            logger.info(f"Batch starting: {len(pending)} items pending")

            async with async_playwright() as p:
                # Single browser instance for the entire batch
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=PROXY_CONFIG_PLAYWRIGHT,
                )

                # Create bounded tasks for all pending items
                tasks = [
                    asyncio.create_task(
                        self._process_item(browser, row_idx, item_id)
                    )
                    for row_idx, item_id in pending
                ]

                # Wait for all tasks (semaphore controls actual concurrency)
                await asyncio.gather(*tasks, return_exceptions=True)

                await browser.close()

            # Final flush to save any remaining in-memory writes
            await self._csv.flush()
            logger.info(
                f"Batch complete. completed={self._stats['completed']} "
                f"failed={self._stats['failed']}"
            )

        except Exception as e:
            logger.error(f"Batch fatal error: {e}")
            await self._csv.flush()
            raise
        finally:
            self._running = False

    async def _process_item(self, browser, row_idx: int, item_id: str):
        """Process a single item: open page, intercept API, close page."""
        if self._cancel_event.is_set():
            return

        async with self._semaphore:
            await asyncio.sleep(REQUEST_DELAY_SECONDS)

            try:
                product = await self._scrape_single(browser, item_id)
                await self._csv.write_success(row_idx, product)
                self._stats["completed"] += 1

                if self._stats["completed"] % 100 == 0:
                    logger.info(
                        f"Progress: {self._stats['completed']} completed, "
                        f"{self._stats['failed']} failed"
                    )

            except Exception as e:
                error_str = str(e)

                # Token/session expired — leave as pending for next run
                if "TOKEN" in error_str.upper() or "SESSION_EXPIRED" in error_str.upper():
                    self._stats["token_errors"] += 1
                    logger.warning(f"Token expired at item {item_id}: {e}")
                    return

                # Retry once for transient errors
                try:
                    await asyncio.sleep(2)
                    product = await self._scrape_single(browser, item_id)
                    await self._csv.write_success(row_idx, product)
                    self._stats["completed"] += 1
                except Exception as retry_err:
                    await self._csv.write_failure(
                        row_idx, item_id, str(retry_err)[:200]
                    )
                    self._stats["failed"] += 1
                    logger.warning(
                        f"Item {item_id} failed after retry: {retry_err}"
                    )

    async def _scrape_single(self, browser, item_id: str):
        """
        Open a new page in the shared browser, navigate to the product URL,
        intercept the API response, parse and return ProductData.
        """
        api_json = None
        url = f"https://www.goofish.com/item?id={item_id}"

        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="es-ES",
        )
        await context.add_cookies(self._cookies)
        page = await context.new_page()

        async def handle_response(response):
            nonlocal api_json
            if "mtop.taobao.idle.pc.detail" in response.url:
                try:
                    api_json = await response.json()
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            # Even on timeout, we may have already captured the API response
            pass

        # Wait a bit longer if the API response hasn't arrived yet
        if api_json is None:
            await asyncio.sleep(3)

        await context.close()

        if api_json is None:
            raise ValueError(f"Could not intercept API response for {item_id}")

        # Check for API-level errors
        ret_codes = api_json.get("ret", [])
        for code in ret_codes:
            code_upper = code.upper()
            if any(
                kw in code_upper
                for kw in ["TOKEN_EMPTY", "TOKEN_EXOIRED", "SESSION_EXPIRED"]
            ):
                raise ValueError(f"Token expired: {code}")

        return GoofishScraper.parse_json(api_json, item_id)

    async def cancel(self):
        """Signal all workers to stop and save progress."""
        self._cancel_event.set()
        await self._csv.flush()
        logger.info("Batch cancellation requested, progress saved.")


# Global singleton
batch_service = BatchScraper()
