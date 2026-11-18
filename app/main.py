"""AI-Powered Website Link Analysis API — FastAPI app.

One endpoint: POST /link-analysis with ``{"url": "..."}``.
Flow: validate URL (incl. SSRF checks) -> fetch + parse HTML ->
clean content -> LLM analysis -> structured JSON with five sections.
Interactive docs at /docs.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas import ErrorResponse, LinkAnalysisRequest, LinkAnalysisResponse
from app.services.analysis_service import analyse_url
from app.services.llm_service import LlmError
from app.services.website_extractor import FetchError, fetch_website
from app.utils.validators import UnsafeUrlError

app = FastAPI(
    title="AI-Powered Website Link Analysis API",
    description=(
        "Analyse a website URL with an LLM and return structured business, "
        "competitor, SEO, search-query and target-audience insights. "
        "Primary LLM: NVIDIA DeepSeek V4.1 Flash; fallback: Gemini 2.5 Flash."
    ),
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return the same error envelope for body-validation failures
    (FastAPI's default 422 body has a different shape)."""
    detail = "; ".join(str(e.get("msg", "")) for e in exc.errors()) or "invalid request"
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(website="", error=detail).model_dump(),
    )


@app.get("/", summary="Service info")
async def root() -> dict:
    return {
        "service": "AI-Powered Website Link Analysis API",
        "version": "1.0.0",
        "endpoint": "POST /link-analysis",
        "docs": "/docs",
        "llm_configured": settings.llm_configured,
        "test_mode": settings.test_mode,
    }


@app.get("/health", summary="Health check")
async def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/link-analysis",
    response_model=LinkAnalysisResponse,
    summary="Analyse a website URL",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid or unsafe URL"},
        502: {"model": ErrorResponse, "description": "Fetch or LLM failure"},
        504: {"model": ErrorResponse, "description": "Website fetch timed out"},
    },
)
async def link_analysis(payload: LinkAnalysisRequest) -> LinkAnalysisResponse:
    """Validate the URL, fetch and analyse the site, return the 5 sections.

    422 — invalid URL syntax or SSRF-blocked address.
    502 — site unreachable / non-HTML / LLM failure.
    504 — site fetch timed out.
    """
    url = payload.url
    try:
        content = await fetch_website(url)
    except UnsafeUrlError as exc:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(website=url, error=f"unsafe URL: {exc}").model_dump(),
        )
    except FetchError as exc:
        message = str(exc)
        status = 504 if "timed out" in message else 502
        return JSONResponse(
            status_code=status,
            content=ErrorResponse(website=url, error=message).model_dump(),
        )
    try:
        return await analyse_url(content)
    except LlmError as exc:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                website=url, error=f"analysis failed: {exc}"
            ).model_dump(),
        )
