# Deployment — steps only Hariom can do

Deployment is mandatory in the spec (Live Demo URL + `/docs`), but it
is **not done yet**, because every step below needs an account in
Hariom's name. Nothing here needs a paid plan.

## 1. Push the repo to GitHub (public)

```bash
cd dxora-link-analysis
git init
git add .
git commit -m "AI-powered website link analysis API (Dxora Python practical test)"
# Create an EMPTY public repo on github.com first, e.g. dxora-link-analysis,
# then:
git remote add origin https://github.com/hariomgupta70427/dxora-link-analysis.git
git branch -M main
git push -u origin main
```

Before pushing, verify no key goes with it:

```bash
git check-ignore .env   # must print ".env"
git ls-files | grep -c "^\.env$"   # must print 0
```

**Do not use the saved GitHub login in this workspace's vault** — it
belongs to a different username (harshitagupta4856), not
hariomgupta70427. Sign in to GitHub as hariomgupta70427 in the browser
(or use a token from that account) for the push.

## 2. Deploy on Render (free tier)

1. Sign up / sign in at https://render.com (GitHub sign-in is easiest).
2. **New + → Web Service → Build and deploy from a Git repository**
   → pick the `dxora-link-analysis` repo.
3. Render detects `render.yaml` automatically: Python, free plan,
   build `pip install -r requirements.txt`, start
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. In **Environment**, add:
   - `NVIDIA_API_KEY` = the `nvapi-...` key (from the local `.env`;
     never paste it anywhere public).
   - The other vars (`NVIDIA_BASE_URL`, `NVIDIA_MODEL`,
     `PYTHON_VERSION`) come from `render.yaml`.
5. **Create Web Service** and wait for the deploy to go live.
6. The service URL will be like
   `https://dxora-link-analysis.onrender.com` — that is the **Live
   Demo URL**; docs are at `<url>/docs`.

## 3. Warm it and smoke-test the deployed URL

Render's free tier sleeps after ~15 minutes of inactivity, so the
first hit after a sleep takes 30–60 s to wake up. Before submitting,
warm it and verify the deployed endpoint (not just localhost):

```bash
curl https://dxora-link-analysis.onrender.com/health
curl -X POST https://dxora-link-analysis.onrender.com/link-analysis \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hariomgupta.vercel.app/"}'
```

Expect HTTP 200 with `"success": true` and all five sections. The
analysis itself takes ~30–60 s with the Ultra model — allow up to
180 s for the request.

## Fallback: Railway

If Render is a problem, Railway's free trial works the same way
(Dockerfile is included): new project → deploy from GitHub repo →
add the same `NVIDIA_API_KEY` variable. Railway also sleeps on the
free tier.
