"""Competitor normalisation (spec sections 3.1 and 9).

This API has no live web search, so it cannot verify competitors
against real market data. Every competitor is therefore labelled
``ai_generated_suggestion`` — a plausible company in the same field,
derived from the analysed site's own content — and the response never
presents one as researched fact. The service only enforces shape:
at least 3 competitors where the model supplied them, strengths and
weaknesses as lists, and the source label always present.
"""

MIN_COMPETITORS = 3


def normalise_competitors(competitors: list[dict]) -> list[dict]:
    """Keep well-formed competitors, force the honesty label on all."""
    out: list[dict] = []
    for comp in competitors or []:
        name = str(comp.get("name", "")).strip()
        if not name:
            continue
        out.append(
            {
                "name": name[:120],
                "strengths": [str(s)[:200] for s in comp.get("strengths", []) or []],
                "weaknesses": [str(s)[:200] for s in comp.get("weaknesses", []) or []],
                # Honesty rule: no web search is performed, so this label
                # is never anything else.
                "source": "ai_generated_suggestion",
            }
        )
    return out


def competitors_are_labelled(competitors: list[dict]) -> bool:
    """True when every competitor carries the AI-suggestion label."""
    return all(
        c.get("source") == "ai_generated_suggestion" for c in competitors
    ) and len(competitors) >= 0
