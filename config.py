import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACES_DIR = os.path.join(BASE_DIR, "traces")
URLS_CSV_PATH = os.path.join(BASE_DIR, "urls.csv")

# =================================================================
# NetNut Datacenter Proxy
# =================================================================
# httpx format (URL string with embedded credentials)
PROXY_URL = "http://codify-dc-any:58ADAB79s03h8TJ@gw.netnut.net:5959"

# Playwright format (dict with separate fields)
PROXY_CONFIG_PLAYWRIGHT = {
    "server": "http://gw.netnut.net:5959",
    "username": "codify-dc-any",
    "password": "58ADAB79s03h8TJ",
}

# =================================================================
# Goofish API
# =================================================================
GOOFISH_API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
GOOFISH_APP_KEY = "34839810"
GOOFISH_API_VERSION = "1.0"

# =================================================================
# Session Cookies
# =================================================================
GOOFISH_COOKIES = {
    "_m_h5_tk": "164f7513736f75657bec6c624622ceb6_1770769127131",
    "_m_h5_tk_enc": "249dccb6ba590e4504c6b051258fd1a4",
    "_tb_token_": "3393b9b741313",
    "t": "944e9f40518ffe15f1796ccc2c290882",
    "_samesite_flag_": "true",
    "cookie2": "15b8bc66f40ddf51d0160417a45eb56d",
}

# =================================================================
# Browser User Agent
# =================================================================
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Safari/537.36"
)

# =================================================================
# Batch Processing Defaults
# =================================================================
DEFAULT_CONCURRENCY = 15
SAVE_INTERVAL_ROWS = 50
REQUEST_DELAY_SECONDS = 0.2
