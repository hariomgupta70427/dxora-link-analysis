# AI-Powered Website Link Analysis API

Python practical test (Dxora Technologies / CREST) — FastAPI app that
analyses a website URL with an LLM and returns structured business,
competitor, SEO, search-query and target-audience insights.

Spec: [practical-test/link-analysis.md](https://github.com/chivoxai/practical-test/blob/main/link-analysis.md)
(Dxora invite email 18 Nov 2026; submission deadline in the email body
and spec §10 is **22 Nov 2026** — the email header says 27 Nov, plan on
22 Nov.)

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then fill in NVIDIA_API_KEY
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Interactive docs: http://localhost:4000/docs

```bash
curl -X POST http://localhost:4000/link-analysis \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hariomgupta.vercel.app/"}'
```

## API

### `POST /link-analysis`

Request:

```json
{"url": "https://example.com"}
```

Response (200) — five sections, shape per spec §4 (full sample in
[`sample-response.json`](sample-response.json)):

```json
{
  "success": true,
  "website": "https://hariomgupta.vercel.app/",
  "brand": {
    "name": "Hariom Gupta",
    "category": "Flutter & Full-Stack Developer",
    "summary": "B.Tech IT student at GGSIPU building AI-powered mobile apps and web platforms..."
  },
  "analysis": {
    "competitor_analysis": {
      "brand_overview": "...",
      "competitors": [
        {"name": "CodeCrafters Studio", "strengths": ["..."], "weaknesses": ["..."], "source": "ai_generated_suggestion"}
      ],
      "strengths": ["..."],
      "opportunities": ["..."]
    },
    "target_search_queries": [
      {"query": "Flutter freelance developer New Delhi", "platforms": ["Google", "LinkedIn"], "intent": "Find a freelance Flutter developer for a mobile app project", "relevance": "High", "audience": "Startup founders and product managers"}
    ],
    "seo_improvements": {
      "primary_keyword": "Flutter full-stack freelance developer",
      "secondary_keywords": ["..."],
      "long_tail_keywords": ["..."],
      "recommended_title": "Hariom Gupta | Flutter & Full-Stack Developer | AI-Powered Mobile & Web Solutions",
      "meta_description": "...",
      "supporting_content": ["..."]
    },
    "top_services": [
      {"name": "Custom Full-Stack Web & Mobile Development", "description": "...", "industry": "Software Development", "customer": "Startups, SMEs, Enterprises", "benefit": "...", "source": "website_content"}
    ],
    "target_audience": {
      "primary_audience": ["Startup founders", "Product managers", "CTOs of early-stage companies"],
      "secondary_audience": ["..."],
      "industries": ["..."],
      "business_types": ["..."],
      "customer_profiles": ["..."],
      "location": "New Delhi, India (remote worldwide)",
      "customer_needs": ["..."],
      "interests": ["..."],
      "marketing_segments": ["..."]
    }
  },
  "meta": {
    "provider": "NVIDIA",
    "model": "nvidia/nemotron-3-ultra-550b-a55b",
    "latency_ms": 61565,
    "prompt_tokens": 1716,
    "completion_tokens": 2563,
    "estimated_cost_usd": 0.0,
    "mock": false
  }
}
```

Error responses share one envelope — `{"success": false, "website": "<url>", "error": "<plain message>"}`:

| Status | Meaning |
| ------ | ------- |
| 422 | Invalid URL syntax, or blocked by the SSRF check (private/loopback address, non-standard port, unresolvable host, embedded credentials) |
| 502 | Site unreachable / non-HTML / too many redirects, or the LLM call failed |
| 504 | Site fetch timed out (20 s) |

## How it works

1. **Validate** — syntactic check (Pydantic), then the SSRF guard
   (`app/utils/validators.py`): only http(s), only ports 80/443, no
   embedded credentials, and the hostname must resolve to public
   address(es) only — RFC1918, loopback, link-local, CGNAT, multicast,
   unspecified and reserved ranges are all rejected. Every redirect hop
   is re-validated (max 5).
2. **Fetch + extract** (`app/services/website_extractor.py`) — httpx
   fetch (20 s timeout, real browser user-agent), BeautifulSoup parse,
   script/style/nav/footer dropped, title / meta description / headings
   / nav links / visible text kept, duplicate lines removed, text
   truncated to 12,000 chars (~3,000 tokens) before it reaches the LLM.
3. **Analyse** (`app/services/analysis_service.py` + `llm_service.py`)
   — one LLM call with a strict-JSON prompt (temperature 0.2,
   `response_format: json_object`, max 4,096 output tokens). If the
   model returns fewer than 5 queries or 5 services, one repair call
   asks it to complete only the missing items; after that the partial
   result is returned honestly — the API never pads with invented
   services. The reply is validated against the Pydantic schemas
   before it is returned.

### Honesty rules (spec §9) — enforced in code, not just in the prompt

- **No invented search volumes.** The response contains no volume or
  ranking numbers anywhere; queries carry intent/relevance/audience only.
- **Competitors are labelled.** This API has no live web search, so
  every competitor is an AI-generated suggestion drawn from the analysed
  site's own content, and every competitor object carries
  `"source": "ai_generated_suggestion"` (forced by
  `competitor_service.py`, not left to the model).
- **Services come from the site.** Each service carries
  `"source": "website_content"` or `"inferred"`; inferred ones are
  labelled as such.
- **No generic results.** The prompt, the extraction and the response
  all come from the submitted URL's actual content.

## 6. LLM platform & model research — cost, speed, accuracy

Prices checked live on **18 Nov 2026** (provider pricing pages via
public indexes; re-verify before budgeting — prices move).

| Provider | Model | Input / 1M tokens | Output / 1M tokens | Context | JSON support | Response speed* | Accuracy* |
| -------- | ----- | ----------------- | ------------------ | ------- | ------------ | --------------- | --------- |
| **NVIDIA (free tier)** | **nemotron-3-ultra-550b-a55b** | **$0.00** (hosted free tier) | **$0.00** | 1M tokens | `response_format: json_object`, verified live | **31–62 s measured** for a full analysis | Strongest reasoning model available on the free tier; verified live twice with accurate, content-grounded output |
| Google Gemini | gemini-2.5-flash | $0.30 | $2.50 | 1M tokens | Native JSON mode | Estimated 2–5 s | Good; widely used for extraction |
| OpenAI | gpt-4o-mini | $0.15 | $0.60 | 128K tokens | `response_format: json_object` | Estimated 2–5 s | Good; smallest context of the four |
| Anthropic | claude-haiku-4.5 | $1.00 | $5.00 | 200K tokens | Structured output via tool use | Estimated 3–8 s | Very good; ~6× the cost of gpt-4o-mini for this workload |

\* **Measured vs estimated, per spec §6D.** Only the NVIDIA row's speed
and accuracy are measured (two live analyses, 18 Nov 2026 — see
[Live smoke test](#live-smoke-test)). Every other row's speed and
accuracy is an estimate from published documentation, not a benchmark
I ran; I did not test those three providers with a key, and I do not
claim maximum accuracy for any model.

Notes on the table:

- **DeepSeek V4.1 Flash is not in the NVIDIA catalog.** It was the
  first-choice model, but a live `GET /v1/models` on 18 Nov 2026
  returned 32 models and no DeepSeek model at all, so it cannot be
  called with this key. For reference, DeepSeek's own API lists
  deepseek-flash at $0.15 input / $0.60 output per 1M tokens
  off-peak ($0.30 / $1.20 peak).
- **NVIDIA publishes no per-token price** for the hosted free tier —
  it is free for prototyping, rate-limited (~40 req/min reported),
  and its trial terms say prototyping/evaluation only, not production.
  Production on NVIDIA means an AI Enterprise licence
  ($4,500/GPU/year list) or a partner's per-token rate.
- **gpt-4o-mini deprecation reported:** third-party indexes list a
  retirement date of 14 Jan 2027 (verify on OpenAI's page before
  building on it long-term).
- **Gemini 2.5 Flash** has a free tier with rate limits; the paid
  rates above apply once it is exceeded. (Gemini 3.x Flash is the
  current generation at $0.75 / $3.75 per 1M through 31 Dec 2026.)

### Final recommendation (§6D)

- **Recommended provider/model:** NVIDIA, `nvidia/nemotron-3-ultra-550b-a55b`.
- **Reason:** accuracy first (the strongest reasoning model reachable
  at $0), reliable structured JSON (verified live — two full analyses
  returned valid JSON matching the spec shape on the first call, no
  repair call needed), 1M-token context (the whole cleaned page fits
  easily), and $0 out-of-pocket on the free tier.
- **Estimated input tokens:** ~450–1,700 per analysis (measured:
  451 for a thin page, 1,716 for a content-rich page).
- **Estimated output tokens:** ~1,700–2,600 per analysis (measured:
  1,715 and 2,563).
- **Estimated cost per analysis:** **$0.00** on the NVIDIA free tier.
  At the same measured token counts, the paid alternatives would cost
  ≈ **$0.007** (Gemini 2.5 Flash), ≈ **$0.002** (GPT-4o-mini) and
  ≈ **$0.015** (Claude Haiku 4.5) per analysis.
- **Expected response time:** **~30–60 s** per analysis (measured:
  31 s thin page, 62 s rich page). The model reasons before answering,
  so it is slower than the Flash/mini class — that is the trade made
  for accuracy. For an interactive demo where latency matters more,
  switch `NVIDIA_MODEL` to `nvidia/nemotron-3.5-lightning-30b-a3b`
  (same free tier, verified reachable).
- **Fallback model:** Gemini 2.5 Flash (free tier) — configured in
  the app: if the NVIDIA call fails and `GEMINI_API_KEY` is set, the
  analysis retries once on Gemini. Get a key at
  https://aistudio.google.com/app/apikey.
- **Balance:** accuracy > cost > speed for this test, because the
  grade is the quality of the analysis and the cost is $0 either way
  on the free tiers.

### Cost optimisation (§6C) — implemented

- Content is cleaned and deduped before sending (12,000-char cap);
  one LLM call per analysis, plus at most one repair call; short
  prompts; no repeated calls; token usage is returned in every
  response (`meta.prompt_tokens` / `meta.completion_tokens`) so cost
  is measured, not guessed. Not implemented (out of scope for the
  2-hour test): URL-result caching and per-task model routing.

## Tests

```bash
TEST_MODE=1 PYTHONPATH=. .venv/bin/pytest tests/ -q
# 26 passed
```

Coverage: invalid URLs (422), SSRF blocks (localhost, 127.0.0.1,
RFC1918, IPv6 loopback, embedded credentials, non-standard ports),
unresolvable host, fetch failure (502), happy path with mocked fetch +
mock LLM (all five sections, exactly 5 queries, exactly 5 services,
competitors labelled `ai_generated_suggestion`), extractor cleaning /
dedup / truncation, `/docs` availability.

Two invocation notes (both are sandbox quirks, also hit in test 1):
`PYTHONPATH=.` is required or collection fails with
"No module named 'app'", and `app/config.py` strips bracketed IPv6
entries from `no_proxy`/`NO_PROXY` at import because httpx 0.28.1
raises `InvalidURL` on them when constructing any client.

## Live smoke test

`live-smoke-test.log` + [`sample-response.json`](sample-response.json)
(full) and [`sample-response-example.json`](sample-response-example.json):

| Run | Target | Result | Latency | Tokens in/out | Cost |
| --- | ------ | ------ | ------- | ------------- | ---- |
| 1 | https://hariomgupta.vercel.app/ | 200, success, all 5 sections, brand correctly identified | 62 s | 1,716 / 2,563 | $0.00 |
| 2 | https://example.com (thin-content edge case) | 200, success, all 5 sections, honest "not a service" summary | 31 s | 451 / 1,715 | $0.00 |

No repair call was needed in either run (5 queries and 5 services on
the first call). Nothing was posted anywhere; the tests only read the
two public sites.

## Deployment

Deployment is mandatory in the spec (Live Demo URL + `/docs`). The
repo ships `render.yaml` + `Dockerfile` for a free Render web service
(see [`DEPLOYMENT.md`](DEPLOYMENT.md) for the exact steps). Render's
free tier sleeps after inactivity, so the first review hit is slow —
warm the URL before submitting. Deployment itself is **not done yet**:
it needs a public GitHub repo under Hariom's account and a Render
account, both of which only he can create — see `DEPLOYMENT.md`.

## Project structure

```
app/
├── main.py                  # FastAPI app, POST /link-analysis, error envelope
├── config.py                # env-var settings, no_proxy sanitiser, load_dotenv
├── schemas.py               # request/response models (spec §4 shape + meta)
├── services/
│   ├── website_extractor.py # SSRF-checked fetch + BeautifulSoup cleaning
│   ├── llm_service.py       # NVIDIA primary, Gemini fallback, TEST_MODE mock
│   ├── analysis_service.py  # prompt, validation, one repair attempt, costing
│   └── competitor_service.py# competitor normalisation + honesty labelling
└── utils/
    └── validators.py        # URL + SSRF checks
tests/
└── test_link_analysis.py    # 26 tests
```

## Known limitations

- **SSRF TOCTOU:** DNS is resolved and validated once before the
  fetch; a hostile record that changes between validation and
  connection (DNS rebinding) is not defended against — that needs
  connect-to-resolved-IP, which httpx does not expose directly.
- **Competitors are AI suggestions, not researched facts** — the app
  has no live web search; this is labelled in every response, per
  spec §9.
- **NVIDIA free tier is prototyping-only** per its trial terms, and
  rate-limited; it fits this test, not a production deployment.
- **Response time is ~30–60 s** with the Ultra model; see the
  recommendation above for the faster alternative.
- The sandbox this was built in resolves every hostname to a
  benchmarking-range address (198.18.0.0/15) via its egress proxy;
  `validators.py` explicitly allows that range (it can never be an
  internal service) while still blocking every RFC1918/loopback/
  link-local range.
