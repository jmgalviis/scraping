
from fastapi.responses import RedirectResponse
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Query, HTTPException
from scraping import scraper_service
from models import ScrapeResponse


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
# API ENDPOINTS
# =================================================================
# Redirect to the documentation
@app.get("/", include_in_schema=False, response_class=RedirectResponse, tags=["Root"])
async def redirect_to_docs():
    return "/docs"

# Scraping endpoint
@app.get("/scrapePDP", tags=["Scraping"])
async def scrape_pdp_endpoint(
            url: str = Query(..., description="The URL of the Goofish product to scrape")
        ) -> list:

        if not url:
            raise HTTPException(status_code=400, detail="URL is required")

        try:
            # Call the scraping logic
            data = await scraper_service.scrape_pdp(url)
            return ScrapeResponse(success=True, data=data)

        except ValueError as ve:
            # Controlled errors (404, duplicate, parsing)
            return ScrapeResponse(success=False, error=str(ve))

        except Exception as e:
            # Unexpected errors
            return ScrapeResponse(success=False, error=f"Internal Server Error: {str(e)}")


# =================================================================
# TESTING
# =================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
