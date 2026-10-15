# Measuring triage quality

The 24 tickets in `cases.json` are hand-labelled **test fixtures**, not real customer data. They cover five categories, four priorities, ambiguous/unrelated requests and hard language cases. Expected labels reflect the explicit guidance in `knowledge.json`. Neither fixture file is imported or seeded by the application.

Run the offline rules baseline:

```powershell
python -m evaluation.run --output artifacts/rules-evaluation.json
```

The checked-in `results/rules.json` is an actual offline run. Category and priority accuracy use all 22 labelled cases, including abstentions as incorrect. Review accuracy uses the two review cases. Coverage uses all 24 cases. Latency is local execution time, not an API/service latency estimate.

Run a small, explicitly opt-in live RAG check with your configured OpenRouter key:

```powershell
python -m evaluation.run --live --output artifacts/live-rag-evaluation.json
```

Live mode uses the same free-only provider, retrieval, evidence validator and durable request-budget wrapper as the app, but a disposable local database. It evaluates at most three cases (at most seven normal provider requests: one index batch and embedding/completion for each ticket). It accepts only `:free` model IDs and enforces zero-price routing. A paid fallback is never attempted. No production database is modified. Free-provider limits and failed requests can affect results.

Live rows additionally report whether the expected support article appears in the top four passages and whether returned citations are exact substrings. Exact quotes prove provenance, not that a recommendation is semantically correct. A tiny hand-authored set is not sufficient to claim reliable production accuracy. Increase independent, human-reviewed coverage before making such claims.

To test the deployed application instead of supplying a local key:

```powershell
python -m evaluation.remote https://ai-ticket-triage-chi.vercel.app --output artifacts/deployed-rag-evaluation.json
```

This explicitly creates an isolated demo workspace through the normal public API, adds labelled evaluation guidance and three tickets, then measures a refund paraphrase, negation, and an unrelated question. It checks source quotes and persists accepted decisions. It uses up to seven free provider requests and logs out when finished. The temporary workspace expires automatically. Do not use it as a quota-free health check.

To strengthen the benchmark over time, add anonymized, independently labelled tickets; review disagreements; keep a held-out set; and compare prompt/model changes using the same fixtures. Always label live provider results separately from mocked integration tests and the rules baseline.
