"""LLM calls: NVIDIA (DeepSeek V4.1 Flash) primary, Gemini fallback.

Both providers speak an OpenAI-compatible chat-completions shape (Gemini
via its OpenAI-compatibility endpoint). One call per analysis, strict
JSON output (``response_format: {"type": "json_object"}``), temperature
0.2. The response includes measured usage so the cost per analysis in
the README is measured, not guessed.

TEST_MODE returns a deterministic mock analysis built from the extracted
content — no network, no key — for the test suite. The mock is labelled
``mock: true`` in the response meta and never claims real competitors.
"""

import json
import re
import time

import httpx

from app.config import settings

SYSTEM_PROMPT = (
    "You are a business analyst API. You receive cleaned text from one "
    "real website and return ONLY a JSON object with the five analysis "
    "sections described in the user message. Rules: use ONLY the website "
    "content supplied — never invent search volumes, prices, locations or "
    "facts not in the text. Competitors must be plausible companies in the "
    "same field, and every competitor object must carry "
    "\"source\": \"ai_generated_suggestion\". Services must come from the "
    "website content; mark any service you inferred (not stated on the "
    "site) with \"source\": \"inferred\". Return exactly 5 search queries "
    "and exactly 5 services. No markdown, no commentary, JSON only."
)

MOCK_ANALYSIS = {
    "brand": {"name": "Mock Brand", "category": "Mock Category", "summary": "Mock summary."},
    "analysis": {
        "competitor_analysis": {
            "brand_overview": "Mock overview.",
            "competitors": [
                {"name": "Mock Competitor A", "strengths": ["s1"], "weaknesses": ["w1"], "source": "ai_generated_suggestion"},
                {"name": "Mock Competitor B", "strengths": ["s1"], "weaknesses": ["w1"], "source": "ai_generated_suggestion"},
                {"name": "Mock Competitor C", "strengths": ["s1"], "weaknesses": ["w1"], "source": "ai_generated_suggestion"},
            ],
            "strengths": ["mock strength"],
            "opportunities": ["mock opportunity"],
        },
        "target_search_queries": [
            {"query": f"mock query {i}", "platforms": ["Google"], "intent": "Service Search", "relevance": "mock", "audience": "mock"}
            for i in range(1, 6)
        ],
        "seo_improvements": {
            "primary_keyword": "mock keyword",
            "secondary_keywords": ["mock secondary"],
            "long_tail_keywords": ["mock long tail keyword"],
            "recommended_title": "Mock Title",
            "meta_description": "Mock meta description.",
            "supporting_content": ["mock FAQ page"],
        },
        "top_services": [
            {"name": f"Mock Service {i}", "description": "mock", "industry": "mock", "customer": "mock", "benefit": "mock", "source": "website_content"}
            for i in range(1, 6)
        ],
        "target_audience": {
            "primary_audience": ["mock audience"],
            "secondary_audience": ["mock secondary audience"],
            "industries": ["mock industry"],
            "business_types": ["mock business"],
            "customer_profiles": ["mock profile"],
            "location": "mock location",
            "customer_needs": ["mock need"],
            "interests": ["mock interest"],
            "marketing_segments": ["mock segment"],
        },
    },
}


class LlmError(Exception):
    """The LLM call failed (no key, HTTP error, bad JSON)."""


def _strip_fences(text: str) -> str:
    """Remove ```json fences and return the largest {...} block."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    if text.startswith("{"):
        return text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_json(text: str) -> dict:
    try:
        parsed = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise LlmError(f"LLM did not return valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LlmError("LLM returned JSON that is not an object")
    return parsed


async def _chat_completion(
    base_url: str, api_key: str, model: str, prompt: str, timeout: float = 90.0
) -> tuple[dict, dict | None, float]:
    """One OpenAI-compatible chat completion. Returns (parsed, usage, ms)."""
    started = time.monotonic()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(base_url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise LlmError(f"LLM request failed: {exc}") from exc
    latency_ms = (time.monotonic() - started) * 1000
    if response.status_code != 200:
        raise LlmError(
            f"LLM API returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise LlmError("LLM API returned a non-JSON response") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"LLM response has no message content: {body}") from exc
    return _parse_json(content), body.get("usage"), latency_ms


def _mock_result(prompt: str) -> tuple[dict, dict | None, float]:
    """Deterministic TEST_MODE result. Brand name comes from the prompt's
    title line when present, so the mock still reflects the input page."""
    import copy

    result = copy.deepcopy(MOCK_ANALYSIS)
    title = re.search(r"^Title: (.+)$", prompt, re.MULTILINE)
    if title:
        result["brand"]["name"] = title.group(1).strip()[:80]
    return result, {"prompt_tokens": 0, "completion_tokens": 0}, 0.0


async def analyze_with_llm(prompt: str) -> tuple[dict, dict, dict | None, float]:
    """Run the analysis prompt.

    Returns (parsed_json, meta_dict, usage, latency_ms). Tries NVIDIA
    first, then Gemini when configured. Raises LlmError if nothing works.
    In TEST_MODE returns the deterministic mock.
    """
    if settings.test_mode:
        parsed, usage, latency = _mock_result(prompt)
        return parsed, {"provider": "mock", "model": "mock", "mock": True}, usage, latency

    errors: list[str] = []
    if settings.nvidia_api_key:
        try:
            parsed, usage, latency = await _chat_completion(
                settings.nvidia_base_url,
                settings.nvidia_api_key,
                settings.nvidia_model,
                prompt,
            )
            return parsed, {
                "provider": "NVIDIA",
                "model": settings.nvidia_model,
                "mock": False,
            }, usage, latency
        except LlmError as exc:
            errors.append(f"NVIDIA: {exc}")
    if settings.gemini_api_key:
        try:
            parsed, usage, latency = await _chat_completion(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                settings.gemini_api_key,
                settings.gemini_model,
                prompt,
            )
            return parsed, {
                "provider": "Gemini",
                "model": settings.gemini_model,
                "mock": False,
            }, usage, latency
        except LlmError as exc:
            errors.append(f"Gemini: {exc}")
    if not errors:
        raise LlmError(
            "no LLM API key is configured — set NVIDIA_API_KEY "
            "(or GEMINI_API_KEY) in .env"
        )
    raise LlmError("all LLM providers failed — " + "; ".join(errors))
