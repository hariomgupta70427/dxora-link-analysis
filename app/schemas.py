"""Request/response schemas for POST /link-analysis.

Response shape follows spec section 4 exactly, plus a ``meta`` object with
the model used, measured latency and token usage, and the estimated cost of
the analysis (spec section 6D asks for cost per analysis to be reported).
"""

from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

ALLOWED_PLATFORMS = {"Google", "Facebook", "Instagram", "LinkedIn", "X"}


def is_valid_url(url: str) -> bool:
    """A URL is syntactically valid when it has an http(s) scheme and host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


class LinkAnalysisRequest(BaseModel):
    """Body of POST /link-analysis: ``{"url": "https://example.com"}``."""

    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        url = value.strip()
        if not url:
            raise ValueError("url must not be empty")
        if not is_valid_url(url):
            raise ValueError(
                "url must be a valid http(s) URL with a host name, "
                f"got: {url[:80]}"
            )
        return url


class Brand(BaseModel):
    name: str
    category: str = ""
    summary: str = ""


class Competitor(BaseModel):
    """One competitor. ``source`` is honest by construction: this API has
    no live web-search, so competitors are always AI-generated suggestions
    drawn from the analysed site's own content (spec section 9)."""

    name: str
    strengths: list[str] = []
    weaknesses: list[str] = []
    source: str = "ai_generated_suggestion"


class CompetitorAnalysis(BaseModel):
    brand_overview: str = ""
    competitors: list[Competitor] = []
    strengths: list[str] = []  # the analysed brand's strengths
    opportunities: list[str] = []


class SearchQuery(BaseModel):
    query: str
    platforms: list[str] = []
    intent: str = ""
    relevance: str = ""
    audience: str = ""

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: list[str]) -> list[str]:
        bad = [p for p in value if p not in ALLOWED_PLATFORMS]
        if bad:
            raise ValueError(f"unknown platforms: {bad}")
        return value


class SeoImprovements(BaseModel):
    primary_keyword: str = ""
    secondary_keywords: list[str] = []
    long_tail_keywords: list[str] = []
    recommended_title: str = ""
    meta_description: str = ""
    supporting_content: list[str] = []


class TopService(BaseModel):
    """One service. ``source`` is "website_content" when the service was
    found in the fetched page, "inferred" when the model derived it from
    surrounding content (spec section 4: label inferred recommendations)."""

    name: str
    description: str = ""
    industry: str = ""
    customer: str = ""
    benefit: str = ""
    source: str = "website_content"


class TargetAudience(BaseModel):
    primary_audience: list[str] = []
    secondary_audience: list[str] = []
    industries: list[str] = []
    business_types: list[str] = []
    customer_profiles: list[str] = []
    location: str = ""
    customer_needs: list[str] = []
    interests: list[str] = []
    marketing_segments: list[str] = []


class Analysis(BaseModel):
    competitor_analysis: CompetitorAnalysis
    target_search_queries: list[SearchQuery] = []
    seo_improvements: SeoImprovements
    top_services: list[TopService] = []
    target_audience: TargetAudience


class AnalysisMeta(BaseModel):
    """Measured (not estimated) run facts, plus the estimated cost."""

    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None
    mock: bool = False  # True only when TEST_MODE produced the analysis


class LinkAnalysisResponse(BaseModel):
    success: bool
    website: str
    brand: Brand
    analysis: Analysis
    meta: AnalysisMeta = AnalysisMeta()


class ErrorResponse(BaseModel):
    success: bool = False
    website: str = ""
    error: str
