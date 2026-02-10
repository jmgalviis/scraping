import json
import time
import asyncio
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
from models import ProductData

# Base directory for storing traces
TRACES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces")

# NetNut Datacenter proxy configuration
PROXY_CONFIG = {
    "server": "http://gw.netnut.net:5959",
    "username": "codify-dc-any",
    "password": "58ADAB79s03h8TJ",
}


# Session cookies for goofish.com
GOOFISH_COOKIES = [
    {
        "name": "_m_h5_tk_enc",
        "value": "249dccb6ba590e4504c6b051258fd1a4",
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": False,
        "sameSite": "None",
    },
    {
        "name": "_tb_token_",
        "value": "3393b9b741313",
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": False,
        "sameSite": "None",
    },
    {
        "name": "t",
        "value": "944e9f40518ffe15f1796ccc2c290882",
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": False,
        "sameSite": "None",
    },
    {
        "name": "_m_h5_tk",
        "value": "164f7513736f75657bec6c624622ceb6_1770769127131",
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": False,
        "sameSite": "None",
    },
    {
        "name": "_samesite_flag_",
        "value": "true",
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "None",
    },
    {
        "name": "cookie2",
        "value": "15b8bc66f40ddf51d0160417a45eb56d",
        "domain": ".goofish.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "None",
    },
]


class GoofishScraper:
    def __init__(self):
        self._cache = set()

    def _extract_item_id(self, url: str) -> str:
        """Extract the product ID from the URL query parameters."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'id' in params:
            return params['id'][0]
        if 'itemId' in params:
            return params['itemId'][0]
        return ""

    async def scrape_pdp(self, url: str) -> ProductData:
        item_id = self._extract_item_id(url)

        if not item_id:
            raise ValueError("Could not extract ITEM_ID from the URL")

        if item_id in self._cache:
            raise ValueError("Duplicated Request")

        api_json = None

        # Create trace directory for this execution: traces/{itemId}_{timestamp}/
        trace_name = f"{item_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        trace_dir = os.path.join(TRACES_DIR, trace_name)
        os.makedirs(trace_dir, exist_ok=True)
        trace_path = os.path.join(trace_dir, "trace.zip")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=PROXY_CONFIG,
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/144.0.0.0 Safari/537.36",
                locale="es-ES",
            )

            # Start tracing (screenshots, snapshots and network)
            await context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )

            # Inject cookies before navigating
            await context.add_cookies(GOOFISH_COOKIES)

            page = await context.new_page()

            # Intercept the detail API response
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

            # Wait a bit longer in case the API response arrives late
            if api_json is None:
                await asyncio.sleep(3)

            # Stop tracing and save
            await context.tracing.stop(path=trace_path)

            await browser.close()

        print(f"[Scraper] Trace saved at: {trace_path}")

        if api_json is None:
            raise ValueError("Could not intercept the detail API response")

        result = self._parse_json(api_json, item_id)
        self._cache.add(item_id)
        return result

    def _parse_json(self, json_data: dict, item_id: str) -> ProductData:
        """
        Map the API JSON response to the ProductData model.
        Path: json_data -> data -> itemDO / sellerDO
        """
        root = json_data.get('data', {})
        item_do = root.get('itemDO', {})
        seller_do = root.get('sellerDO', {})

        # Images
        images = []
        for img in item_do.get('imageInfos', []):
            url = img.get('url', '')
            if url:
                images.append(url)

        # Date: prefer the raw string, fallback to timestamp conversion
        gmt_create_str = item_do.get('GMT_CREATE_DATE_KEY', '')
        if not gmt_create_str:
            gmt_create_ts = item_do.get('gmtCreate', 0)
            if gmt_create_ts:
                gmt_create_str = time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(gmt_create_ts / 1000)
                )

        return ProductData(
            ITEM_ID=str(item_do.get('itemId', item_id)),
            CATEGORY_ID=str(item_do.get('categoryId', '')),
            TITLE=item_do.get('title', ''),
            IMAGES=images,
            SOLD_PRICE=str(item_do.get('soldPrice', '0')),
            BROWSE_COUNT=item_do.get('browseCnt', 0),
            WANT_COUNT=item_do.get('wantCnt', 0),
            COLLECT_COUNT=item_do.get('collectCnt', 0),
            QUANTITY=item_do.get('quantity', 0),
            GMT_CREATE=gmt_create_str,
            SELLER_ID=str(seller_do.get('sellerId', '')),
        )


# Global scraper instance
scraper_service = GoofishScraper()
