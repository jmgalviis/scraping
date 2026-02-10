import asyncio
from fastapi.responses import RedirectResponse
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Query, HTTPException
from scraping import scraper_service
from batch_scraper import batch_service
from models import ScrapeResponse, BulkScrapeStatus


# =================================================================
# FAST API CONFIGURATION
# =================================================================
YOUR_NAME = "JUAN MANUEL GALVIS"

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=f"Goofish Scraping API - Developed by {YOUR_NAME}",
        version="1.0.0",
        description="Technical Assesment Test for the position of Backend Engineer at Iceberg Data. This API is used to scrape the Goofish website and extract product information.",
        routes=app.routes
    )

    if "HTTPValidationError" in openapi_schema["components"]["schemas"]:
        del openapi_schema["components"]["schemas"]["HTTPValidationError"]
    if "ValidationError" in openapi_schema["components"]["schemas"]:
        del openapi_schema["components"]["schemas"]["ValidationError"]

    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.pop("servers", None)
            if "responses" in method:
                if "422" in method["responses"]:
                    del method["responses"]["422"]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI()
app.openapi = custom_openapi


# =================================================================
# API ENDPOINTS — Single URL Scraping
# =================================================================
# Redirect to the documentation
@app.get("/", include_in_schema=False, response_class=RedirectResponse, tags=["Root"])
async def redirect_to_docs():
    return "/docs"


# Single URL scraping endpoint (Playwright-based)
@app.get("/scrapePDP", tags=["Single Scraping"])
async def scrape_pdp_endpoint(
            url: str = Query(..., description="The URL of the Goofish product to scrape")
        ) -> list:

        if not url:
            raise HTTPException(status_code=400, detail="URL is required")

        try:
            # Call the Playwright-based scraping logic
            data = await scraper_service.scrape_pdp(url)
            return ScrapeResponse(success=True, data=data)

        except ValueError as ve:
            # Controlled errors (404, duplicate, parsing)
            return ScrapeResponse(success=False, error=str(ve))

        except Exception as e:
            # Unexpected errors
            return ScrapeResponse(success=False, error=f"Internal Server Error: {str(e)}")


# =================================================================
# API ENDPOINTS — Bulk Scraping
# =================================================================
# Start the batch scraping process
@app.post("/scrapeBulk", tags=["Batch Scraping"])
async def scrape_bulk_start(
    concurrency: int = Query(default=15, ge=1, le=50, description="Max concurrent requests")
):
    """
    Start the batch scraping process for all pending URLs in urls.csv.
    Runs in the background. Use /scrapeBulk/status to monitor progress.
    """
    if batch_service.is_running:
        raise HTTPException(status_code=409, detail="Batch is already running")

    # Update concurrency if different from default
    batch_service._semaphore = asyncio.Semaphore(concurrency)

    # Launch as a background task
    asyncio.create_task(batch_service.run())
    return {"message": "Batch scraping started", "concurrency": concurrency}


# Check batch progress
@app.get("/scrapeBulk/status", tags=["Batch Scraping"], response_model=BulkScrapeStatus)
async def scrape_bulk_status():
    """Get current batch scraping progress and statistics."""
    return batch_service.status


# Cancel running batch
@app.post("/scrapeBulk/cancel", tags=["Batch Scraping"])
async def scrape_bulk_cancel():
    """Cancel the running batch. All progress is saved to CSV."""
    if not batch_service.is_running:
        raise HTTPException(status_code=400, detail="No batch is running")
    await batch_service.cancel()
    return {"message": "Batch cancellation requested, progress saved"}


# Hot-swap cookies when token expires
@app.post("/updateCookies", tags=["Configuration"])
async def update_cookies(cookies: dict):
    """
    Update session cookies (e.g. after token expiry mid-batch).
    Pass a dict like: {"_m_h5_tk": "new_value", "_m_h5_tk_enc": "new_value", ...}
    """
    batch_service.update_cookies(cookies)
    return {"message": "Cookies updated", "keys": list(cookies.keys())}


# =================================================================
# TESTING
# =================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
