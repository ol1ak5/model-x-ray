# Deployment

Decision, 26 Oct 2026: Model X-Ray runs as one project on Vercel's free (Hobby) plan. The React app and the FastAPI API share one domain, Nemotron runs on Nebius Token Factory, and nothing else is paid for. This replaces the container options weighed in #75 (Nebius AI Cloud needed its own billing; Render and Hugging Face Spaces sleep when idle).

## How the project is put together

| Piece | Where it comes from |
|---|---|
| API | `app.py` at the repository root, one of the entrypoint names Vercel looks for. It builds the app with `app_from_env()` and becomes a single Vercel Function (Fluid compute) |
| Python and dependencies | `.python-version` (3.13) and `pyproject.toml` with `uv.lock`; Vercel installs them with uv |
| Frontend | `vercel.json` sets the build command to `npm --prefix frontend ci && npm --prefix frontend run build`. `app.py` serves `frontend/dist` with `app.frontend("/")`, which Vercel promotes to its CDN. API routes win over frontend files, so `/health`, `/spreadsheets` and `/investigations/...` reach the function and every other path gets the page |
| Same origin | A production build calls the API on its own origin (`API_URL` is `""` unless `VITE_API_URL` is set), so there is no CORS setup to keep in sync |
| Function size | `vercel.json` leaves `frontend/node_modules`, the frontend sources, tests, docs, tools and the demo logic sets out of the function bundle; the demo model the API serves is `demo_models/demo.xlsx` |

## What changes on Vercel

A Vercel Function keeps nothing between requests: two requests from one visitor can reach two instances, and only `/tmp` is writable. Everything the API used to keep between requests now travels with the request or the answer (`docs/api.md`, "Requests that carry the model"):

- the browser re-sends the uploaded `.xlsx` with every stream request, under an id derived from its content;
- the final `view` event carries the sheet window and, after an approval, the corrected workbook;
- the run's state already lived in the browser (`docs/persistence.md`).

When the `VERCEL` environment variable is set (Vercel sets it), every writable default moves under the system temp folder (`/tmp/model-x-ray`): uploads, corrected copies, the SQLite checkpointer and the long-term memory store. The memory store therefore lasts only as long as one instance; overrides and past findings are a convenience, not a guarantee, on the public demo.

## Limits to know

| Limit | Value on Hobby | What it means here |
|---|---|---|
| Request body | 4.5 MB | The largest model a visitor can check online. The API itself accepts up to 10 MB when run elsewhere |
| Response body | 4.5 MB | The corrected workbook comes back inside the stream, so the same size bound applies |
| Duration | 300 s per request (`maxDuration` in `vercel.json`) | A full investigation takes 30 to 60 s on the demo model |
| Usage cap | `DEMO_MAX_PER_VISITOR`, `DEMO_MAX_PER_DAY` | Counted per instance and reset when an instance is recycled, so the real ceiling is higher than the numbers. Visitors are told apart by `x-forwarded-for` |
| Plan | Hobby is for non-commercial use | Fits a hackathon demo |

## Steps the owner does once

1. Sign in at vercel.com with GitHub and choose **Add New → Project**, then import `ol1ak5/model-x-ray`. Keep the root directory as the repository root; Vercel detects FastAPI from `pyproject.toml`.
2. Under **Settings → Environment Variables** add `NEBIUS_API_KEY` (the Token Factory key, marked Sensitive). The model names, limits and paths have defaults; set `DEMO_MAX_PER_VISITOR` and `DEMO_MAX_PER_DAY` only to change the cap.
3. Deploy. Every push to `main` deploys again; every pull request gets a preview URL.
4. Smoke test on the deployed URL: open the page, run the demo model to the review, approve, and download the corrected file. One run costs about 4 cents of Token Factory credit.

## Running the same setup locally

`npm --prefix frontend run build`, then `VERCEL=1 uv run uvicorn app:app --port 8000` serves the built page and the API on http://localhost:8000 with the temp-folder defaults. `scripts/dev.sh` stays the everyday setup: two servers with hot reload.
