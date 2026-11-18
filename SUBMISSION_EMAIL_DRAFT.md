# Submission email — DRAFT, do NOT send yet

**To:** hr@chivoxai.com
**Subject:** Hariom Gupta - Python Practical Link Analysis test review

---

Hi Dxora team,

Please find my submission for the Python Practical Test — AI-Powered
Website Link Analysis API.

- **Full name:** Hariom Gupta
- **Demo Link:** [PASTE DEPLOYED URL HERE — e.g. https://dxora-link-analysis.onrender.com]
- **API documentation:** [PASTE DEPLOYED URL HERE]/docs
- **Public GitHub Repository:** [PASTE REPO URL HERE — e.g. https://github.com/hariomgupta70427/dxora-link-analysis]
- **Contact Number:** +91 9315175199
- **Current Location:** New Delhi, India
- **Preferred Date and Time for Final Discussion:** [FILL IN — fresh date/time; the 18 Nov after-8 PM slot was for the first test and no longer applies]

**About the implementation**

- One endpoint, `POST /link-analysis`, taking `{"url": "..."}` and
  returning the five required sections (competitor analysis, top 5
  target search queries, SEO improvements, top 5 services, target
  audience) as structured JSON.
- Website content is fetched and parsed with BeautifulSoup, cleaned
  and truncated before it reaches the LLM; SSRF protection blocks
  private/internal addresses and re-validates every redirect hop.
- LLM: NVIDIA Nemotron-3 Ultra (free tier) via the NVIDIA hosted API,
  with Gemini 2.5 Flash as fallback. The README contains the full
  4-provider comparison with live pricing (checked 18 Nov 2026), the
  final recommendation, measured token usage and cost per analysis
  ($0.00 on the free tier), and the expected ~30–60 s response time.
- Competitors are clearly labelled as AI-generated suggestions and
  services as website content vs inferred, per the spec — no search
  volumes are invented anywhere.
- Tests: 26/26 passing (pytest). Live smoke-tested against two real
  sites (logs and sample responses are in the repo).

**Verification steps (spec §11)**

- I have followed Dxora Technologies on LinkedIn:
  [PASTE YOUR LINKEDIN PROFILE LINK HERE]
- I have followed CREST on Instagram:
  [PASTE YOUR INSTAGRAM PROFILE LINK HERE]

Thank you for the opportunity — looking forward to the final
discussion with the Dxora Panel.

Best regards,
Hariom Gupta
hariomgupta70427@gmail.com
https://hariomgupta.vercel.app/
https://github.com/hariomgupta70427

---

## Still needed before this can be sent

1. **Deployed Demo URL** — needs the GitHub push + Render deploy in
   `DEPLOYMENT.md` (both need Hariom's accounts).
2. **Public repo URL** — same as above.
3. **Fresh preferred date/time for the final discussion.**
4. **His LinkedIn + Instagram profile links** (Instagram handle is
   not on file — do not guess it).
