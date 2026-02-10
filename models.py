from pydantic import BaseModel
from typing import List, Optional


class ProductData(BaseModel):
    ITEM_ID: str
    CATEGORY_ID: str
    TITLE: str
    IMAGES: List[str]
    SOLD_PRICE: str
    BROWSE_COUNT: int
    WANT_COUNT: int
    COLLECT_COUNT: int
    QUANTITY: int
    GMT_CREATE: str
    SELLER_ID: str


class ScrapeResponse(BaseModel):
    success: bool
    data: Optional[ProductData] = None
    error: Optional[str] = None


class BulkScrapeStatus(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    pending: int = 0
    running: bool = False
    started_at: Optional[float] = None
    elapsed_seconds: float = 0.0
    items_per_second: float = 0.0
    token_errors: int = 0
