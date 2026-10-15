# Triage Desk: autonomous support and human exception handling

## Intended product

Two distinct interfaces share the existing FastAPI/React application. Customers submit an enquiry and get a grounded, customer-facing answer without waiting for approval when the question can be answered from current knowledge. Administrators manage exceptions and can review any completed ticket, replace an answer, reopen it, or request an AI revision. Automatic completion means an informational enquiry was answered; it never means a refund, account change, or operational repair was executed.

## Research and policy decisions

Research inspected on 15 October 2026:

- Intercom escalation guidance: https://www.intercom.com/help/en/articles/12396892-manage-fin-ai-agent-s-escalation-guidance-and-rules
- Intercom human approvals: https://www.intercom.com/help/en/articles/14468561-human-in-the-loop-approvals-for-fin-procedures
- Zendesk knowledge answers and escalation: https://support.zendesk.com/hc/en-us/articles/10448933203994-Customizing-the-Knowledge-reply-in-an-AI-agent-with-agentic-AI
- Zendesk conversation audit: https://support.zendesk.com/hc/en-us/articles/8357749580186-Reviewing-conversation-logs-for-AI-agents

These sources support configurable escalation, grounded knowledge answers, customer-requested handoff, exception approvals, and post-resolution auditing. The specific gates below are project design decisions, not a claim that every company uses the same policy.

Automatically answer routine documented how-to, onboarding, product limitations, troubleshooting with a safe workaround, feature availability, billing-policy explanations, and password-reset instructions. Require a human for actual refunds/financial adjustments, account recovery requiring identity verification, account/data deletion, suspected compromise/fraud, legal/privacy requests, widespread outages, exceptional permissions, customer-requested handoff, or an unsuccessful prior answer. Missing/stale knowledge, contradictory or insufficient evidence, invalid citations, provider failures, and quota exhaustion also go to the admin queue with explicit reasons. Do not interpret a similarity score as a correctness probability.

## Architecture and delivery order

1. Add a versioned migration for customer sessions, customer ownership, immutable public conversation messages, outcome state/version, and admin review history. Preserve all existing owner and demo content.
2. Add a resolution service: deterministic risk gates plus structured OpenRouter generation grounded in retrieved support articles and urgency policy. Validate category, priority and exact evidence quotes. Embeddings retrieve evidence; the language model writes the answer. Preserve free-only model validation, atomic budgets and no paid fallback.
3. Give customer sessions separate cookies and CSRF tokens. Customers see only their own tickets and public messages, never internal notes, admin endpoints, or other customers' records. Public submissions use owner knowledge. A signed-in demo can preview the customer portal in its isolated workspace. Session credentials identify anonymous customers; no email verification is implied.
4. Automatically run resolution on customer submission. Record the answer, labels, immutable evidence snapshot and audit event atomically. Use outcome versions to prevent an in-flight AI answer overwriting human intervention, changed knowledge, edited tickets, or a reopened case.
5. Customer follow-up reopens the ticket for human review; explicit handoff is always honored. Admins can publish a correction, request AI changes, or approve an existing answer. Preserve every prior answer and correction. AI revision of an admin-requested change remains for admin review before publication.
6. Refurbish customer and admin interfaces: clear entry points, dedicated customer conversation page, admin exception queue, completed-ticket inspection, automation metrics, review controls, evidence and activity history. Keep existing knowledge/taxonomy management and manual workflows.
7. Verify meaningful tests for resolution/escalation boundaries, access isolation, CSRF, stale/concurrent writes, migration preservation, free-only behavior, failure handling, UI build and browser journeys. Update documentation and evaluation examples for the new product.

## Acceptance evidence

- Routine documented enquiry produces a cited answer and resolved status without admin confirmation.
- High-risk/action requests and explicit human requests appear in admin review, without falsely claiming external actions.
- Missing evidence, malformed generation, provider errors and budget limits preserve the enquiry and request review.
- Customer cannot read another customer's ticket, internal feedback, or administration APIs.
- Admin can open an automatically completed case, publish a correction, request revised output, review the draft and publish it. Customer can reopen an unsatisfactory answer.
- In-flight work cannot overwrite a newer human decision or publish against stale knowledge.
- Existing migration/test flows remain valid; new lifecycle is tested through API and browser.
- No paid model/provider fallback, new paid service, external message delivery, or production deployment is needed for local implementation verification.

## Initial constraints

Anonymous customer history is tied to its browser session, with a clearly visible expiry. No external account/payment integrations exist, so requests requiring those actions must escalate. AI resolution counts are labeled as answered automatically, distinct from customer-confirmed success. Free-provider quotas and the current bounded SQL index remain explicit operational limits. This plan does not claim unlimited scale or enterprise certification.

## Implementation and release status

Implemented in this checkout: migration `0004`, separate customer session/CSRF and ownership checks, customer enquiry/conversation interface, automatic sourced resolution, deterministic and model-selected escalation, admin review queue and automation counters, public corrections, private AI revision drafts, customer reopening, outcome-version protection, interrupted-job recovery, and updated documentation. Customer tickets cannot be falsely closed through the legacy label/status endpoint.

Verified locally: TypeScript and production frontend build; frontend unit tests; full existing backend regression coverage; new resolution, access, evidence, failure, budget, expiry, concurrent-intervention and cleanup tests; all eight Playwright browser workflows, including the complete customer/admin correction journey and a mobile no-overflow check. Browser tests explicitly mock the provider and run a real isolated API/database. Screenshots are generated under ignored `artifacts/`.

The release audit additionally covers overdue request recovery on a warm server: a customer read transfers an interrupted answer to support without waiting for a restart or another inference job, while active requests remain untouched and repeated polling creates no duplicate handoff notice. The PostgreSQL workflow includes automatic customer resolution, reopening, human correction, session/conversation persistence across application restart, and preservation of populated prior-schema data. This check passed against hosted PostgreSQL in a uniquely named disposable schema, which was removed afterwards. The Neon CLI required a separate sign-in, so verification used the existing Vercel-injected database connection and schema isolation instead of creating a Neon branch.

Released to the existing Vercel application after the user authorized production deployment and the database update. Production deployment `dpl_3vyt92JpJTcXPckgfMussWS9etJE` serves https://ai-ticket-triage-chi.vercel.app/ with the customer interface at `/support`. The production build passed, its authenticated health check returned 200, and the public domain was verified to resolve to that deployment. Migration `0004` is applied. Owner-content digests match before migration, after migration, and after live verification; no persistent owner tickets, articles, decisions, notes, or revisions were altered.

The real deployed resolution verification passed using the existing protected server-side OpenRouter key and the configured `:free` embedding and generation models. It consumed five free requests: indexing, automatic-answer embedding/generation, and revised-answer embedding/generation. A routine refund-policy enquiry received an exact-quote-supported answer and completed automatically. Explicit human requests, financial actions, security incidents, outages, and privacy requests escalated without provider calls. Private revision, administrator publication, correction, immutable answer history, customer reopening, ownership checks, and administrator authentication all passed. Its temporary demo was ended and its sessions were revoked.

The deployed browser verification also passed: customer submission/handoff, administrator correction, customer-visible updated answer, reopening, no browser errors, and demo/session cleanup. Evidence is saved under ignored `artifacts/deployed-resolution-verification.json`, `artifacts/live-browser-resolution.json`, and the owner-digest snapshots. The production OpenRouter secret was neither exported nor replaced. The Vercel MCP account lacked project access; deployment and scoped database checks used the CLI's existing authorized credentials. Local placeholder credentials were not used for live verification.
