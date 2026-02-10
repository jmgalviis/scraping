from pydantic import BaseModel, Field
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
