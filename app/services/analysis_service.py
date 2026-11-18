"""Orchestration: extracted content -> LLM prompt -> validated analysis.

One LLM call per analysis (spec section 6C: avoid repeated calls). If
the model returns fewer than 5 queries or 5 services, one repair call
asks it to complete only the missing items; after that, whatever is
present is returned honestly — the API never pads with invented
services. Cost per analysis is computed from the *measured* token
usage returned by the provider and the provider's published rates
(see README section 6 for the live-priced table).
"""

from app.config import settings
from app.schemas import (
    Analysis,
    AnalysisMeta,
    Brand,
    LinkAnalysisResponse,
)
from app.services.competitor_service import normalise_competitors
from app.services.llm_service import LlmError, analyze_with_llm
from app.services.website_extractor import ExtractedContent

# Published list prices (USD per 1M tokens), checked 18 Nov 2026.
# NVIDIA hosted API is free for prototyping on the key used here, so its
# out-of-pocket cost is $0; NVIDIA publishes no per-token price for the
# hosted free tier.
COST_PER_1M = {
    ("NVIDIA", "nvidia/nemotron-3-ultra-550b-a55b"): (0.0, 0.0),  # free tier
    ("Gemini", "gemini-2.5-flash"): (0.30, 2.50),
}

PROMPT_TEMPLATE = """Analyse this real website and return a JSON object with exactly these keys:
brand {{name, category, summary}},
analysis {{
  competitor_analysis {{brand_overview, competitors: [{{name, strengths: [], weaknesses: [], source: "ai_generated_suggestion"}}] (minimum 3), strengths: [], opportunities: []}},
  target_search_queries: [{{query, platforms: [], intent, relevance, audience}}] (exactly 5; each platform must be one of Google, Facebook, Instagram, LinkedIn, X),
  seo_improvements {{primary_keyword, secondary_keywords: [], long_tail_keywords: [], recommended_title, meta_description, supporting_content: []}},
  top_services: [{{name, description, industry, customer, benefit, source}}] (exactly 5; source is "website_content" when the service is stated on the site, "inferred" when you derived it),
  target_audience {{primary_audience: [], secondary_audience: [], industries: [], business_types: [], customer_profiles: [], location, customer_needs: [], interests: [], marketing_segments: []}}
}}
Do NOT invent search volumes, prices or facts not in the text below.

Title: {title}
Meta description: {meta_description}
Headings: {headings}
Navigation links: {nav_links}
Page text:
{text}
"""


def build_prompt(content: ExtractedContent) -> str:
    return PROMPT_TEMPLATE.format(
        title=content.title or "(no title)",
        meta_description=content.meta_description or "(none)",
        headings=" | ".join(content.headings) or "(none)",
        nav_links=" | ".join(content.nav_links) or "(none)",
        text=content.text or "(no readable text)",
    )


def _cost_usd(provider: str, model: str, usage: dict | None) -> float | None:
    if not usage:
        return None
    rates = COST_PER_1M.get((provider, model))
    if rates is None:
        return None
    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0
    return round(
        prompt_tokens * rates[0] / 1_000_000
        + completion_tokens * rates[1] / 1_000_000,
        6,
    )


def _validate_and_build(parsed: dict, website: str) -> tuple[Brand, Analysis]:
    """Validate the LLM JSON against the Pydantic schemas.

    Competitors are normalised (label forced); everything else is
    validated as-is. Raises ValueError on a structurally invalid reply.
    """
    brand = Brand(**parsed.get("brand", {}))
    analysis_raw = parsed.get("analysis") or {}
    comp = analysis_raw.get("competitor_analysis") or {}
    comp["competitors"] = normalise_competitors(comp.get("competitors", []))
    analysis_raw["competitor_analysis"] = comp
    analysis = Analysis(**analysis_raw)
    return brand, analysis


async def analyse_url(content: ExtractedContent) -> LinkAnalysisResponse:
    """Run one analysis for already-extracted *content*."""
    prompt = build_prompt(content)
    try:
        parsed, provider_meta, usage, latency_ms = await analyze_with_llm(prompt)
    except LlmError as exc:
        raise

    try:
        brand, analysis = _validate_and_build(parsed, content.final_url)
    except Exception as exc:
        raise LlmError(f"LLM response failed validation: {exc}") from exc

    # One repair attempt if the model under-delivered on the "exactly 5" lists.
    missing_queries = max(0, 5 - len(analysis.target_search_queries))
    missing_services = max(0, 5 - len(analysis.top_services))
    if (missing_queries or missing_services) and not provider_meta.get("mock"):
        repair_prompt = (
            prompt
            + f"\n\nYour previous reply was short: it had "
            f"{len(analysis.target_search_queries)} search queries and "
            f"{len(analysis.top_services)} services. Reply with the FULL JSON "
            f"again, with exactly 5 search queries and exactly 5 services, "
            f"using only the website content above."
        )
        try:
            parsed2, provider_meta2, usage2, latency2 = await analyze_with_llm(
                repair_prompt
            )
            brand2, analysis2 = _validate_and_build(parsed2, content.final_url)
            if len(analysis2.target_search_queries) >= len(
                analysis.target_search_queries
            ) and len(analysis2.top_services) >= len(analysis.top_services):
                brand, analysis = brand2, analysis2
                provider_meta, usage, latency_ms = provider_meta2, usage2, latency2
        except LlmError:
            pass  # keep the first (partial but honest) result

    meta = AnalysisMeta(
        provider=provider_meta.get("provider", ""),
        model=provider_meta.get("model", ""),
        latency_ms=int(latency_ms),
        prompt_tokens=(usage or {}).get("prompt_tokens"),
        completion_tokens=(usage or {}).get("completion_tokens"),
        estimated_cost_usd=_cost_usd(
            provider_meta.get("provider", ""),
            provider_meta.get("model", ""),
            usage,
        ),
        mock=bool(provider_meta.get("mock")),
    )
    return LinkAnalysisResponse(
        success=True,
        website=content.final_url,
        brand=brand,
        analysis=analysis,
        meta=meta,
    )
