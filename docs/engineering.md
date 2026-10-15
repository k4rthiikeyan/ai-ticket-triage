# Triage Desk: engineering and deployment guide

[Back to the portfolio overview and walkthrough](../README.md). Commands below run from the repository root.

A support application with **automatic, sourced answers for routine enquiries** and **human exception handling**. It uses OpenRouter embeddings to retrieve knowledge and an OpenRouter language model to write the answer. Both models are free-only; embeddings alone do not generate solutions.

Customers use **`/support`**. Administrators use **`/`**. A grounded informational answer completes a customer ticket automatically. An administrator can inspect any completed ticket, publish a correction, reopen it, or request an AI revision. Revisions of published answers remain private drafts until the administrator publishes them. The original triage/rules comparison and manual label decisions remain available in the admin workspace.

See [the researched redesign plan](../REDESIGN_PLAN.md) for the product requirements, escalation policy, implementation order and release evidence. The redesign is deployed to the existing app: [customer portal](https://ai-ticket-triage-chi.vercel.app/support) and [administrator workspace](https://ai-ticket-triage-chi.vercel.app/). Migration `0004` and the real-provider resolution/review flow have been verified in the hosted environment, with persistent owner content preserved.

## Customer and administrator workflow

1. An administrator writes active support articles and a separate urgency policy, then rebuilds the knowledge index. Active support articles are the approved customer-answer corpus; keep confidential internal material out of these articles.
2. A customer opens `/support` and receives a separate, anonymous browser session. They submit a subject and enquiry. Customer cookies and CSRF tokens are distinct from administrator credentials.
3. The server checks non-delegable escalation gates, retrieves support evidence, and asks the free LLM for a structured, cited answer and routing labels. Exact quotes and taxonomy values are validated. Low relevance, missing/stale knowledge or provider errors preserve the enquiry and transfer it to support.
4. Supported, routine informational answers are published and marked **Answered by AI** immediately. The customer can expand the sources. No administrator approval is requested for this path. This means the question was answered; no payment, account change or operational repair is executed.
5. Exceptions appear in **Needs review** on the administrator dashboard. The reviewer sees the conversation, reason for escalation, evidence and audit history. They can publish a customer-ready correction or request AI changes using internal instructions.
6. Revised AI answers are private drafts. Publishing one creates another immutable public message. Original answers remain in the conversation. Customers can reply to reopen an unsatisfactory outcome for a person.

Human review is required for explicit requests for a person, actual refunds/financial adjustments, account-specific investigation or changes, identity recovery, security incidents, service outages, privacy/legal/deletion requests, policy exceptions, unsuccessful prior answers, insufficient/invalid evidence, and provider/usage failures. Policy explanations, documented self-service and routine how-to questions can complete automatically. These are project policy decisions informed by the sources in the plan, not a universal corporate rule.

Public customer sessions use owner knowledge and create owner-workspace tickets. A signed-in demo visitor can select **Customer portal** to preview the same workflow in their isolated demo workspace. Anonymous history is accessible only through the current customer session (eight hours by default), rather than a verified customer account. Once it expires, the support team retains the records but the browser must start a new session. This is a non-sensitive prototype; the free NVIDIA endpoint's published terms exclude confidential or personal data.

`CUSTOMER_PORTAL_ENABLED=false` disables public customer-session creation and customer APIs. Demo deletion also removes that demo's customer sessions and conversation messages. Existing owner content is preserved by migration `0004`.

**[Live demo](https://ai-ticket-triage-chi.vercel.app/)** — select **Try the demo**. Each browser receives an isolated workspace with **six labelled example articles and three example tickets**. Click **Rebuild index**, open a ticket, and run triage. You can edit the guidance or enter your own requests. Loading examples makes no AI calls; embeddings are generated only when you build the index.

## Engineering highlights

- **Traceable outcomes:** exact-quote validation, immutable customer conversations, versioned outcome review, private revision drafts, stale-result rejection, explicit acceptance/override, and audit history. In-flight AI work cannot overwrite a newer human/customer intervention or publish against changed knowledge.
- **Workspace isolation:** server-selected workspace membership scopes tickets, articles, search indexes, dashboards, and jobs. Guessing another visitor's record ID returns 404. Owner content is preserved separately.
- **Bounded free usage:** atomic SQL counters work across server instances. Defaults are 40 AI requests per UTC day globally, 8 per minute globally, and 12 per demo workspace per UTC day. Index batches, query embeddings, and completions each count as requests. There is no paid fallback.
- **Reproducible evaluation:** 24 hand-labelled fixtures covering five categories, all four priorities, unrelated/ambiguous requests, negation, and paraphrases. These fixtures never populate the live application.
- **Verification:** backend tests, real PostgreSQL integration in CI, frontend tests, and Playwright browser workflows. Model transport is mocked in CI; live-provider results are reported separately.

## Code organization and request flow

`customer portal → customer-scoped route → risk gates → retrieval + free LLM → validated answer → automatic completion or admin review`

`admin dashboard → workspace-scoped route → review / correction / private AI revision → published answer + audit history`

```text
backend/app/
  main.py             Application assembly, lifecycle, headers, frontend serving
  dependencies.py     Authentication, CSRF, workspace access checks
  routes/             Auth, tickets, knowledge, taxonomy, system endpoints
  services/
    provider.py       Free-only OpenRouter HTTP requests and validation
    retrieval.py      Chunking, embedding snapshots, bounded cosine search
    triage.py         Prompt, evidence validation, abstention, rules baseline
    resolution.py     Automatic answers, risk gates, customer-answer citations
    workspaces.py     Demo lifecycle, scoped state, expiry cleanup
    usage.py          Atomic shared usage limits and provider admission
    records.py        Revision invalidation, audit, presentation helpers
  jobs.py             Serialized admission and recoverable request-bound jobs
  models.py           SQL entities
  schemas.py          Input and generated-output validation
backend/migrations/   Versioned schema upgrades
frontend/src/         Separate page, search, recommendation, and form components
  CustomerPortal.tsx Customer enquiry interface and public conversation
  OutcomeReview.tsx  Admin correction, revision and publication controls
evaluation/           Isolated fixtures, runners, and measured results
tests/                API, isolation, concurrency, migration, and RAG checks
```

The frontend context lives separately from the application shell, avoiding page-to-shell import cycles. Page components own their UI state; the administrator API client owns admin CSRF and session expiry handling. The customer client uses a separate cookie and CSRF header. No microservices or extra paid infrastructure are needed for this scope.

## Evaluation and limitations

The checked-in [rules benchmark](../evaluation/results/rules.json) measured **20/22 (90.9%) category accuracy**, **20/22 (90.9%) priority accuracy**, correct review on **2/2** unrelated/ambiguous cases, and suggestions on **20/24** cases. Abstaining on a labelled case counts as a miss. Negation and paraphrased billing language remain failures. These numbers describe a small hand-authored rules benchmark, **not LLM accuracy or production performance**.

Run `python -m evaluation.run --output artifacts/rules-evaluation.json` without an API request. See [evaluation instructions](../evaluation/README.md) for the opt-in free-model RAG check, retrieval recall, exact-quote checks, and latency measurements.

Design tradeoffs:

- SQL-stored vectors and bounded in-process cosine search keep this small prototype simple. A growing knowledge base should use a database vector index; adding one now would not establish scalability by itself.
- Shared routing categories are administrator-managed; visitor tickets, knowledge, and index versions are isolated. Isolation is enforced in application services, not database row-level security. This is a prototype rather than a compliance boundary for sensitive data.
- A demo uses a browser-session cookie, with **30 minutes of sliding inactivity expiry** as a server-side safeguard. Normal navigation, reload and active editing preserve the workspace. **End demo & delete data** removes its tickets, knowledge, embeddings, notes, decisions, revisions, job records and login sessions from the app database. If an AI request is running, the session is revoked immediately and its data is purged when that request finishes. Owner data is preserved. Anonymous quota counters remain until their retention window expires.
- Browsers do not reliably notify the server when a tab or browser closes, and some restore session cookies. Closing one tab therefore does not guarantee immediate physical deletion. Expired demo data is purged in bounded batches on subsequent API requests; no paid scheduler is required. The app does not send a logout beacon on navigation or reload, which would unexpectedly erase active work. The administrator's separate persistent login default remains eight hours.
- One index rebuild or triage runs globally at a time. This is a deliberate bound on free-provider load. Larger workloads need durable workers and a different concurrency policy.
- Free-provider availability and quota vary. App counters are additional safeguards; they do not measure usage from other apps sharing the same OpenRouter key. The UI reports quota errors and preserves manual/rules workflows.
- Automatic-resolution counts mean answered enquiries, not verified customer satisfaction. A follow-up reopens the ticket. Full multi-account identity, external action integrations, and enterprise certification are outside this implementation.
- Limits also bound demo writes, new workspace creation, and per-workspace articles/tickets. Visitors cannot change operator settings. This does not replace abuse protection for a large public launch.

Migration `0003` keeps existing content in owner workspace 1 and revokes legacy shared-demo sessions. Existing visitors sign in again to receive isolated workspaces. Database upgrades are tested before release; schema rollback is not an automatic recovery strategy for newly created visitor content.

The prototype is configured for **zero-cost AI and free hosting plans**:

- Embeddings: `nvidia/nemotron-3-embed-1b:free` through OpenRouter.
- LLM: `nvidia/nemotron-3-super-120b-a12b:free` through OpenRouter, with JSON-schema structured output.
- Hosting: **Vercel Hobby**, for a personal, non-commercial prototype.
- Database: **Neon Free**, with PostgreSQL and stored embeddings.

Both model IDs must end in `:free`. The server rejects paid IDs and automatic model routers, and every AI request sets a zero-price limit for input tokens, output tokens, and per-request fees. There is no paid model fallback. Only one OpenRouter key is needed; no NVIDIA key or credit purchase is required for these free model variants.

Free plans have usage limits. Check the linked provider documentation for current account allowances. Providers can impose additional limits or become unavailable. Indexing, searching, and triage consume API requests. Quota errors stay visible, and rules comparison/manual decisions remain available. Vercel Hobby and Neon Free also have usage allowances: stay on their free plans and wait for quota resets rather than upgrading. This configuration is for a bounded prototype, not unlimited free service.

Sources: [NVIDIA free embeddings](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free), [NVIDIA free LLM](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free), [OpenRouter free-model limits](https://openrouter.ai/docs/api_reference/limits), [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Neon Free](https://neon.com/pricing).

The owner workspace starts without tickets or knowledge. Temporary demo sessions include clearly labelled fictional starter guidance and tickets to make the workflow easy to try; they are separated from owner data and removed with the session. No AI recommendations or embeddings are fabricated. Older installations automatically remove the original legacy demo records while preserving user-created and edited content. Evaluation fixtures remain separate from starter content.

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

## Administrator setup and triage comparison

For a public project review, set `PUBLIC_DEMO_ENABLED=true` in Vercel Production and redeploy. The login page displays the dedicated `demo` / `try-triage` credentials and a **Try the demo** button. Visitors receive labelled starter examples in their own temporary workspace; category/queue configuration and provider diagnostics require the administrator. The administrator password is never published. Use non-sensitive examples. Existing empty demo workspaces can use **Load starter examples** in Knowledge base. Automated evaluations can pass `starter_examples=false` at demo login for an empty workspace. Set the flag to `false` to disable new and existing demo access.

1. Open **Knowledge base** and write or paste a support article describing your product, supported categories, and routing guidance. Save it.
2. Create a separate article, check **Use as urgency policy**, and define when your team assigns `low`, `normal`, `high`, or `urgent`. Save it. No default policy is fabricated.
3. Click **Rebuild index**. This sends article chunks to OpenRouter's embedding endpoint and stores the vectors in your database.
4. Type a question in **Search your knowledge** to inspect relevant passages and their similarity scores.
5. Click **New ticket**, type a subject and request, and click **Run triage**. The backend embeds the request, retrieves knowledge, and asks the OpenRouter LLM for a structured recommendation.
6. Inspect the quoted sources and rationale, change labels if needed, then click **Confirm decision**. Notes, status changes, revisions, and decisions remain auditable.

Rules comparison and manual decisions work without an OpenRouter key. RAG requires an indexed support article and urgency policy. Article edits invalidate the index until a successful rebuild. Changing `EMBEDDING_MODEL` also requires a rebuild. Requests and article passages used for AI are sent to OpenRouter and its selected model provider.

After indexing, select **Customer portal** for the automatic-answer experience described above. The older **Run triage / Confirm decision** controls provide an optional administrator comparison workflow; customer submissions do not require those controls.

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

`tests/test_resolution.py` covers autonomous completion, risk/negation boundaries, customer ownership and CSRF, provider/evidence failures, customer reopening, private revisions, publication, and in-flight human/knowledge changes. `frontend/e2e/resolution.spec.ts` exercises customer submission through admin correction and reopening, including a mobile viewport. The browser fixture uses a higher mocked per-minute allowance so several test journeys can run together; production defaults remain unchanged.

For an explicitly opt-in real-provider smoke check, run `python -m evaluation.resolution --live`. It creates and removes a disposable local SQLite database, uses at most three free provider requests, tests one automatic answer and two deterministic escalations, and writes `artifacts/live-resolution.json`. It never connects to the configured owner database. A configured server-side OpenRouter key is required; a provider failure is reported as a failure, not a successful live test.

To verify the deployed resolution flow using the key already on Vercel, run `python -m evaluation.remote_resolution https://ai-ticket-triage-chi.vercel.app --output artifacts/deployed-resolution-verification.json`. This uses an isolated demo workspace, five normal free-provider requests, and no exported key. It verifies automatic completion, five escalation scenarios, private revision, publication, correction, reopening, isolation and logout cleanup. `node frontend/scripts/verify-deployed.mjs https://ai-ticket-triage-chi.vercel.app` verifies the deployed customer/admin browser flow in another temporary demo without additional AI requests. Both checks passed for the released redesign.

GitHub Actions also runs the complete backend flow against a disposable PostgreSQL 16 service. Locally, that integration test is skipped unless `TEST_POSTGRES_URL` points to a disposable test database. It creates and removes a uniquely named test schema. It uses mocked OpenRouter responses; it does not spend API credits.

## References

- [OpenRouter free NVIDIA embeddings](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free)
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)

## Provider connection checks

An administrator can test the configured OpenRouter services with POST /api/system/check-provider?kind=embeddings or kind=llm, including the normal X-CSRF-Token header. Each explicit check sends one tiny request through the existing free-only gateway and creates no tickets, articles, or index entries. The response reports success or a safe provider error without returning API keys. These checks count toward free-model rate limits.
