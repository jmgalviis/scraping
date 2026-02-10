import os
import asyncio
import pandas as pd
from urllib.parse import urlparse, parse_qs
from models import ProductData
from config import URLS_CSV_PATH, SAVE_INTERVAL_ROWS


class CSVManager:
    """
    Manages reading and writing the urls.csv file.
    Tracks which item_ids are already scraped (deduplication).
    Writes results incrementally and supports resume on restart.
    """

    def __init__(self, csv_path: str = URLS_CSV_PATH):
        self._csv_path = csv_path
        self._lock = asyncio.Lock()
        self._df: pd.DataFrame = None
        self._completed_ids: set = set()
        self._failed_ids: set = set()
        self._writes_since_flush = 0

    async def load(self):
        """Load the CSV and determine which rows are already complete."""
        async with self._lock:
            self._df = pd.read_csv(self._csv_path, dtype=str, keep_default_na=False)

            for idx, row in self._df.iterrows():
                item_id_val = row.get("ITEM_ID", "").strip()
                if item_id_val == "FAILED":
                    item_id = self._extract_id_from_url(row["URL"])
                    self._failed_ids.add(item_id)
                elif item_id_val:
                    self._completed_ids.add(item_id_val)

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        """Extract item ID from URL like https://www.goofish.com/item?id=XXX"""
        params = parse_qs(urlparse(url).query)
        return params.get("id", params.get("itemId", [""]))[0]

    def get_pending_items(self) -> list:
        """Return list of (row_index, item_id) for rows not yet scraped."""
        result = []
        for idx, row in self._df.iterrows():
            item_id = self._extract_id_from_url(row["URL"])
            if item_id not in self._completed_ids and item_id not in self._failed_ids:
                result.append((idx, item_id))
        return result

    async def write_success(self, row_idx: int, data: ProductData):
        """Write a successful result into the DataFrame and conditionally flush."""
        async with self._lock:
            self._df.at[row_idx, "ITEM_ID"] = data.ITEM_ID
            self._df.at[row_idx, "CATEGORY_ID"] = data.CATEGORY_ID
            self._df.at[row_idx, "TITLE"] = data.TITLE
            self._df.at[row_idx, "IMAGES"] = "|".join(data.IMAGES)
            self._df.at[row_idx, "SOLD_PRICE"] = data.SOLD_PRICE
            self._df.at[row_idx, "BROWSE_COUNT"] = str(data.BROWSE_COUNT)
            self._df.at[row_idx, "WANT_COUNT"] = str(data.WANT_COUNT)
            self._df.at[row_idx, "COLLECT_COUNT"] = str(data.COLLECT_COUNT)
            self._df.at[row_idx, "QUANTITY"] = str(data.QUANTITY)
            self._df.at[row_idx, "GMT_CREATE"] = data.GMT_CREATE
            self._df.at[row_idx, "SELLER_ID"] = data.SELLER_ID
            self._completed_ids.add(data.ITEM_ID)
            self._writes_since_flush += 1

            if self._writes_since_flush >= SAVE_INTERVAL_ROWS:
                self._flush_to_disk()

    async def write_failure(self, row_idx: int, item_id: str, reason: str):
        """Mark a row as failed so it is skipped on resume."""
        async with self._lock:
            self._df.at[row_idx, "ITEM_ID"] = "FAILED"
            self._df.at[row_idx, "TITLE"] = reason[:200]
            self._failed_ids.add(item_id)
            self._writes_since_flush += 1

            if self._writes_since_flush >= SAVE_INTERVAL_ROWS:
                self._flush_to_disk()

    def _flush_to_disk(self):
        """Atomic write: write to temp file then rename. Called under lock."""
        tmp_path = self._csv_path + ".tmp"
        self._df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, self._csv_path)
        self._writes_since_flush = 0

    async def flush(self):
        """Force a flush to disk (e.g. on shutdown or at end of batch)."""
        async with self._lock:
            self._flush_to_disk()

    @property
    def stats(self) -> dict:
        total = len(self._df) if self._df is not None else 0
        completed = len(self._completed_ids)
        failed = len(self._failed_ids)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
        }
