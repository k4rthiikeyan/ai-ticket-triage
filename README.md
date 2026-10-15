# Triage Desk

**AI support ticketing with cited answers and human review.**

[Live demo](https://ai-ticket-triage-chi.vercel.app/) · [Customer portal](https://ai-ticket-triage-chi.vercel.app/support) · [Full walkthrough](docs/walkthrough.md)

## The idea

Answer repetitive support questions using approved knowledge, while sending sensitive or unsupported requests to a person. Customers submit enquiries through a dedicated portal; administrators handle exceptions and can review or correct any completed answer.

![Administrator workspace showing a corrected support answer](docs/images/admin-review.jpg)

## Features

- **Grounded AI answers:** retrieve knowledge articles, validate quoted evidence, and automatically answer routine enquiries.
- **Ticket routing:** assign category, priority, and queue; escalate requests that need human attention.
- **Admin review:** publish corrections, approve private AI revisions, and inspect conversation and audit history.
- **Customer follow-up:** revisit enquiries and reopen an issue when the answer does not help.
- **Isolated demos:** temporary visitor workspaces with starter articles, example tickets, and bounded AI usage.

## Tech stack

**Frontend:** React, TypeScript, Vite. **Backend:** Python 3.13, FastAPI, SQLModel, Alembic.

**AI:** OpenRouter embeddings and structured generation. **Data:** SQLite locally, Neon PostgreSQL in production. **Hosting:** Vercel.

**Testing:** pytest, Vitest, Playwright, and GitHub Actions.

## Try it as both customer and admin

1. Open the [live demo](https://ai-ticket-triage-chi.vercel.app/) and click **Try the demo** (`demo` / `try-triage`).
2. In **Knowledge base**, click **Rebuild index** and wait for completion.
3. Open **Customer portal** in a second tab **in the same browser profile**. Submit an enquiry, such as “How long does an approved refund take?”
4. Return to admin: inspect escalations in **Needs review**, or open completed enquiries in **All tickets**. Enter a customer-ready response and click **Publish correction**; refresh the customer tab to see it.

Demo data is temporary. Free-provider quotas and availability may affect automatic answers. See the [full walkthrough](docs/walkthrough.md) for sample enquiries, AI revisions, and reopening tickets.

## Run locally

Requires **Python 3.13**, **Node.js 22 or 24**, and Git.

```powershell
git clone https://github.com/k4rthiikeyan/ai-ticket-triage.git
cd ai-ticket-triage
Copy-Item .env.example .env
```

Edit `.env`: set `ADMIN_PASSWORD`, your own `OPENROUTER_API_KEY`, and `PUBLIC_DEMO_ENABLED=true` for starter examples. Keep keys out of Git.

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

Open [admin](http://127.0.0.1:8000/) and [customer portal](http://127.0.0.1:8000/support) in the same browser. Use **Try the demo** for temporary examples, or sign in with your configured admin credentials for a persistent workspace. The persistent workspace starts empty: add a support article and a separate urgency policy, then **Rebuild index**.

## Further documentation

- [Customer and admin walkthrough](docs/walkthrough.md) — sample enquiries, corrections, revisions, and follow-up.
- [Engineering guide](docs/engineering.md) — setup alternatives, deployment, configuration, and tests.
- [Evaluation](evaluation/README.md) — benchmark methodology and limitations.
