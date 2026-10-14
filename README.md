# Triage Desk

A support-ticket triage prototype using **OpenRouter embeddings for RAG search** and **OpenRouter chat completions for the LLM**. Users write their own knowledge and tickets. Suggestions include exact source quotes and become final only after human confirmation.

The prototype is configured for **zero-cost AI and free hosting plans**:

- Embeddings: `nvidia/nemotron-3-embed-1b:free` through OpenRouter.
- LLM: `nvidia/nemotron-3-super-120b-a12b:free` through OpenRouter, with JSON-schema structured output.
- Hosting: **Vercel Hobby**, for a personal, non-commercial prototype.
- Database: **Neon Free**, with PostgreSQL and stored embeddings.

Both model IDs must end in `:free`. The server rejects paid IDs and automatic model routers, and every AI request sets a zero-price limit for input tokens, output tokens, and per-request fees. There is no paid model fallback. Only one OpenRouter key is needed; no NVIDIA key or credit purchase is required for these free model variants.

Free plans have usage limits. OpenRouter currently documents 20 requests per minute and 50 requests per day for free variants on accounts that have not bought credits. Providers can impose additional limits or become unavailable. Indexing, searching, and triage consume API requests. Quota errors stay visible, and rules comparison/manual decisions remain available. Vercel Hobby and Neon Free also have usage allowances: stay on their free plans and wait for quota resets rather than upgrading. This configuration is for a bounded prototype, not unlimited free service.

Sources: [NVIDIA free embeddings](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free), [NVIDIA free LLM](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free), [OpenRouter free-model limits](https://openrouter.ai/docs/api_reference/limits), [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Neon Free](https://neon.com/pricing).

There are **no seeded tickets, articles, or fictional product policies**. The administrator and editable category/queue defaults are configuration only. Older installations automatically remove tagged demo tickets and unchanged original demo articles; user-created tickets and edited articles are preserved. The old synthetic evaluation datasets have been removed.

## Deploy from GitHub to Vercel

Vercel supports this FastAPI backend and React frontend as one project. `pyproject.toml` selects `backend.app.main:app`, and `vercel.json` builds the frontend and allows a 300-second function. Use the **repository root** as the Vercel Root Directory.

1. Import this GitHub repository into your **Vercel Hobby** account. Select the **FastAPI** framework preset if it is not detected automatically. Keep the checked-in Build Command; leave Output Directory unset. Use the free `vercel.app` address; a purchased domain is unnecessary.
2. Create a hosted **Neon PostgreSQL database on the Free plan** through Vercel's Storage/Marketplace flow and connect it to this project. If the integration does not offer a Free plan, create the database directly on [Neon Free](https://neon.com/pricing) and set its URL manually. Use its **pooled connection URL**, with TLS enabled. The backend accepts either `DATABASE_URL` or the Marketplace's `POSTGRES_URL`. If both exist, `DATABASE_URL` wins. Do not set a SQLite URL on Vercel.
3. Before deploying, configure these backend environment variables in Vercel for Production and the Preview environments you will use:

   - `DATABASE_URL`: the pooled PostgreSQL URL, unless `POSTGRES_URL` is already supplied by the integration.
   - `OPENROUTER_API_KEY`: your OpenRouter key; the selected `:free` models do not require buying credits.
   - `ADMIN_USERNAME`: your desired username (default `admin`).
   - `ADMIN_PASSWORD`: a strong password of your choosing.
   - `COOKIE_SECURE=true`: required for HTTPS cookies on the deployment.
   - `GENERATION_MODEL=nvidia/nemotron-3-super-120b-a12b:free`: replace any earlier paid model setting.
   - `EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b:free`: replace any earlier paid embedding setting.

4. Deploy or redeploy after setting the variables. Startup runs Alembic migrations and creates the administrator once. Database migrations and administrator bootstrap are serialized across instances with PostgreSQL transaction locks. `/api/health` should return `{"status":"ok"}`.
5. Open the deployment, sign in with your configured credentials, and follow the first-use steps below.

You can also run `npx vercel login`, `npx vercel link`, verify the selected project with `npx vercel project inspect --non-interactive`, and deploy with `npx vercel --prod` from this directory. The database and environment variables must already be configured.

Vercel's filesystem is temporary, so **all tickets, knowledge, sessions, audit records, and embeddings live in PostgreSQL**. No Chroma directory, local model download, or separate vector database is needed. The prototype stores vectors as JSON and computes cosine similarity over a bounded index (256 chunks by default). This is intended for a small knowledge base; larger deployments should move vector search into a database vector index.

Indexing and triage finish **inside the HTTP request**, avoiding background threads that may stop after a serverless response. Job records still expose progress, outcomes, and errors. Admission is serialized in the shared database. Interrupted jobs are recoverable after their time budget expires. Larger indexing workloads need a durable worker rather than increasing the prototype limits indefinitely.

## First use: bring your own knowledge

For a public project review, set `PUBLIC_DEMO_ENABLED=true` in Vercel Production and redeploy. The login page displays the dedicated `demo` / `try-triage` credentials and a **Try the demo** button. Visitors can try tickets, articles, and free-model triage in the shared workspace; category/queue configuration and provider diagnostics require the administrator. The administrator password is never published. The page labels demo content as public, so use non-sensitive examples. Set the flag to `false` to disable both demo sign-in and existing demo sessions. This adds a visitor account, not seeded tickets or articles.

1. Open **Knowledge base** and write or paste a support article describing your product, supported categories, and routing guidance. Save it.
2. Create a separate article, check **Use as urgency policy**, and define when your team assigns `low`, `normal`, `high`, or `urgent`. Save it. No default policy is fabricated.
3. Click **Rebuild index**. This sends article chunks to OpenRouter's embedding endpoint and stores the vectors in your database.
4. Type a question in **Search your knowledge** to inspect relevant passages and their similarity scores.
5. Click **New ticket**, type a subject and request, and click **Run triage**. The backend embeds the request, retrieves knowledge, and asks the OpenRouter LLM for a structured recommendation.
6. Inspect the quoted sources and rationale, change labels if needed, then click **Confirm decision**. Notes, status changes, revisions, and decisions remain auditable.

Rules comparison and manual decisions work without an OpenRouter key. RAG requires an indexed support article and urgency policy. Article edits invalidate the index until a successful rebuild. Changing `EMBEDDING_MODEL` also requires a rebuild. Requests and article passages used for AI are sent to OpenRouter and its selected model provider.

## Local development

Prerequisites: Python 3.13, Node.js 22 or 24, and npm.

```powershell
Copy-Item .env.example .env
# Edit .env: replace ADMIN_PASSWORD and OPENROUTER_API_KEY placeholders.
.\scripts\setup.ps1
.\scripts\start.ps1
```

Open **http://127.0.0.1:8000**. Local development uses SQLite at ignored `data/triage.db`, including the stored embeddings. The same SQL models and migrations support PostgreSQL on Vercel. For separate frontend development, run `npm run dev` in `frontend`; Vite proxies `/api` to port 8000.

`.env` and `.env.local` are ignored. Real keys never belong in the frontend or repository. An optional `OPENROUTER_EMBEDDING_API_KEY` can use a different key for embeddings; leaving it blank uses `OPENROUTER_API_KEY` for both APIs. Defaults are the free NVIDIA models listed above. Alternate models must have a `:free` suffix, and the generation model must support JSON-schema structured outputs. Routing requires support for the requested parameters. Paid settings from older versions now fail validation instead of making a billed request. After changing the embedding model, rebuild any existing knowledge index.

The environment template documents the remaining settings. `INFERENCE_TIMEOUT` defaults to 60 seconds per provider call, and `JOB_TIMEOUT` defaults to 240 seconds. The OpenRouter status reports whether keys are configured; actual requests verify authentication, free quotas, and provider availability. Missing keys and provider failures produce visible errors without a paid fallback. Reasoning is disabled for the short structured triage response to keep it within the prototype request budget.

`ADMIN_USERNAME` and `ADMIN_PASSWORD` bootstrap the first administrator only; changing them does not replace an existing account. Use a dedicated database for this prototype. If your database account cannot run migrations, migrate once with appropriate credentials using `python -m backend.app.cli init`, then set `AUTO_MIGRATE=false` for the runtime account.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Backend tests mock OpenRouter's HTTP transport to verify authentication, embedding ordering and validation, structured generation, and safe errors. SQL retrieval tests use a real SQLite database and reopen the stored index. Browser tests use a real isolated API/database with explicitly mocked OpenRouter responses, starting empty and adding knowledge through the UI. Real OpenRouter calls and hosted PostgreSQL require configured credentials and are not represented as verified by these mocks.

GitHub Actions also runs the complete backend flow against a disposable PostgreSQL 16 service. Locally, that integration test is skipped unless `TEST_POSTGRES_URL` points to a disposable test database. It creates and removes a uniquely named test schema. It uses mocked OpenRouter responses; it does not spend API credits.

## References

- [OpenRouter free NVIDIA embeddings](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free)
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)

## Provider connection checks

An administrator can test the configured OpenRouter services with POST /api/system/check-provider?kind=embeddings or kind=llm, including the normal X-CSRF-Token header. Each explicit check sends one tiny request through the existing free-only gateway and creates no tickets, articles, or index entries. The response reports success or a safe provider error without returning API keys. These checks count toward free-model rate limits.
