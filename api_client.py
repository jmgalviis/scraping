import hashlib
import json
import time
import httpx
from config import (
    GOOFISH_API_URL,
    GOOFISH_APP_KEY,
    GOOFISH_API_VERSION,
    GOOFISH_COOKIES,
    PROXY_URL,
    USER_AGENT,
)


class TokenExpiredError(Exception):
    """Raised when the API returns a token/session expired indicator."""
    pass


class ItemNotFoundError(Exception):
    """Raised when the item does not exist or was removed."""
    pass


class GoofishAPIClient:
    """
    Direct HTTP client for the Goofish product detail API.
    Bypasses the browser entirely — constructs signed requests via httpx.
    """

    def __init__(self, cookies: dict = None):
        self._cookies = dict(cookies or GOOFISH_COOKIES)
        self._client: httpx.AsyncClient | None = None

    async def start(self):
        """Create the persistent httpx.AsyncClient with proxy and cookies."""
        self._client = httpx.AsyncClient(
            proxy=PROXY_URL,
            cookies=self._cookies,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.goofish.com/",
                "Origin": "https://www.goofish.com",
                "Accept": "application/json",
                "Accept-Language": "es-419,es;q=0.7",
            },
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=True,
        )

    async def close(self):
        """Shutdown the HTTP client gracefully."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_token(self) -> str:
        """Extract the signing token from _m_h5_tk cookie (part before the first underscore)."""
        raw = self._cookies.get("_m_h5_tk", "")
        return raw.split("_")[0] if raw else ""

    def _build_sign(self, token: str, timestamp: str, data_json: str) -> str:
        """Generate MD5 signature: md5(token & timestamp & appKey & data)."""
        plain = f"{token}&{timestamp}&{GOOFISH_APP_KEY}&{data_json}"
        return hashlib.md5(plain.encode()).hexdigest()

    async def fetch_product(self, item_id: str) -> dict:
        """
        Call the Goofish detail API for a single item.
        Returns the parsed JSON response dict.
        Raises TokenExpiredError or ItemNotFoundError on specific failures.
        """
        timestamp = str(int(time.time() * 1000))
        data_json = json.dumps({"itemId": item_id}, separators=(",", ":"))
        token = self._get_token()
        sign = self._build_sign(token, timestamp, data_json)

        params = {
            "jsv": "2.7.2",
            "appKey": GOOFISH_APP_KEY,
            "t": timestamp,
            "sign": sign,
            "v": GOOFISH_API_VERSION,
            "type": "originaljson",
            "api": "mtop.taobao.idle.pc.detail",
            "dataType": "json",
            "data": data_json,
        }

        response = await self._client.get(GOOFISH_API_URL, params=params)

        # Update cookies from response (token rotation)
        for name, value in response.cookies.items():
            self._cookies[name] = value
            self._client.cookies.set(name, value)

        response.raise_for_status()
        body = response.json()

        # Check API-level error codes in the ret array
        ret_codes = body.get("ret", [])
        for code in ret_codes:
            code_upper = code.upper()
            if any(kw in code_upper for kw in ["TOKEN_EMPTY", "TOKEN_EXOIRED", "SESSION_EXPIRED"]):
                raise TokenExpiredError(f"Token expired: {code}")

        # Check if the response data is empty (item removed / not found)
        data = body.get("data", {})
        item_do = data.get("itemDO", {})
        if not item_do and "SUCCESS" not in str(ret_codes):
            raise ItemNotFoundError(f"Item not found: {item_id}")

        return body

    def update_cookies(self, new_cookies: dict):
        """Hot-swap cookies (e.g. after manual token refresh)."""
        self._cookies.update(new_cookies)
        if self._client:
            for name, value in new_cookies.items():
                self._client.cookies.set(name, value)
