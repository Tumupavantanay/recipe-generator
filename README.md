# Recipe Generator — Vercel Deploy

This folder is ready to deploy on **Vercel** (Python Runtime + Serverless Flask).

## Structure
- `index.html` — static frontend (served from root).
- `api/index.py` — Flask app exposing `/health` and `/generate_recipe` (serverless).
- `requirements.txt` — runtime deps.
- `vercel.json` — rewrite all paths to the Flask serverless function (original path preserved).

## Deploy (CLI)
```bash
npm i -g vercel
vercel
# or push to GitHub and import from Vercel dashboard
```

## Environment Variables (Vercel → Project → Settings → Environment Variables)
- `OPENROUTER_API_KEY` = your OpenRouter key
- `APP_URL` = your production URL (optional; used for Referer header)

> Do **not** commit your local `.env` file. Use Vercel env vars instead.
