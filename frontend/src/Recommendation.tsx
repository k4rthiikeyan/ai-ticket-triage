import { BookOpen, ShieldCheck, ChevronDown } from "lucide-react";
import { scoreLabel } from "./api";
import { Empty } from "./ui";
import { useWorkspace } from "./workspace";
import type { Run } from "./types";

export function Recommendation({ selected }: { selected?: Run }) {
  const { taxonomy } = useWorkspace();
  const suggestion = selected?.payload.suggestions;
  const categoryName = (id?: number | null) =>
    taxonomy.categories.find((c) => c.id === id)?.name || "Unknown";
  const queueName = (id?: number | null) =>
    taxonomy.queues.find((q) => q.id === id)?.name || "Unknown";
  return (
    <>
      {selected ? (
        <div className="recommendation">
          <div className="recommendation-meta">
            <span
              className={
                "badge " +
                (selected.outcome === "suggested"
                  ? "open"
                  : selected.outcome === "failed"
                    ? "urgent"
                    : "new")
              }
            >
              {selected.outcome === "suggested"
                ? "Suggested"
                : selected.outcome === "failed"
                  ? "Failed"
                  : "Needs review"}
            </span>
            <span>
              {selected.method === "rules"
                ? "Rules baseline"
                : selected.method === "rag"
                  ? "RAG"
                  : "AI resolution"}{" "}
              · {selected.model}
            </span>
            <span>
              {selected.payload.latency_ms !== undefined
                ? selected.payload.latency_ms + " ms"
                : ""}
            </span>
          </div>
          {selected.stale && (
            <div className="warning-box">
              This result is stale. Rerun triage or record a fresh manual
              decision.
            </div>
          )}
          {suggestion ? (
            <>
              <div className="suggestion-grid">
                {[
                  {
                    key: "category",
                    label: "Category",
                    value: categoryName(suggestion.category_id),
                  },
                  {
                    key: "priority",
                    label: "Priority",
                    value:
                      suggestion.priority.charAt(0).toUpperCase() +
                      suggestion.priority.slice(1),
                  },
                  {
                    key: "queue",
                    label: "Queue",
                    value: queueName(suggestion.queue_id),
                  },
                ].map((s) => (
                  <div key={s.key}>
                    <span className="eyebrow">{s.label}</span>
                    <strong>{s.value}</strong>
                    <span className="evidence-score">
                      {scoreLabel(selected.payload.scores[s.key])}{" "}
                      {selected.method !== "rules"
                        ? "evidence support"
                        : "rule strength"}
                    </span>
                    <p>{selected.payload.rationales[s.key]}</p>
                  </div>
                ))}
              </div>
              <p className="score-note">
                <ShieldCheck size={14} />
                Heuristic scores are not probabilities of correctness. Review
                the rationale and evidence.
              </p>
            </>
          ) : (
            <div className="review-message">
              {selected.payload.error || selected.payload.rationales.review}
            </div>
          )}
          {selected.payload.citations.length > 0 && (
            <div className="evidence-list">
              <h3>
                <BookOpen size={16} />
                Supporting evidence
              </h3>
              {selected.payload.citations.map((source, i) => (
                <div
                  className="source-card"
                  key={source.chunk_id + source.field + i}
                >
                  <div>
                    <strong>{source.title}</strong>
                    <span className="subtle-label">{source.field}</span>
                  </div>
                  <blockquote>“{source.quote}”</blockquote>
                  <div className="source-meta">
                    Article v{source.article_revision} · Similarity{" "}
                    {source.similarity.toFixed(3)} · {source.chunk_id}
                  </div>
                  <details>
                    <summary>View indexed source text</summary>
                    <p className="pre-wrap">{source.text}</p>
                  </details>
                </div>
              ))}
            </div>
          )}
          {selected.payload.retrieved.length > 0 && (
            <details className="retrieval-details">
              <summary>
                Retrieved context · {selected.payload.retrieved.length} chunks
                <ChevronDown size={14} />
              </summary>
              {selected.payload.retrieved.map((s) => (
                <div className="retrieved-row" key={s.chunk_id}>
                  <strong>{s.title}</strong>
                  <span>Cosine similarity {s.similarity.toFixed(3)}</span>
                  <p className="pre-wrap">{s.text}</p>
                </div>
              ))}
            </details>
          )}
          <div className="run-footnote">
            Request v{selected.ticket_revision} ·{" "}
            {selected.index_version
              ? "Index " + selected.index_version.slice(-8)
              : "No retrieval index"}
          </div>
        </div>
      ) : (
        <Empty
          title="Ready for a clearer next step"
          description="Run RAG triage to retrieve sources and generate a recommendation, or compare the rules baseline."
        />
      )}
    </>
  );
}
