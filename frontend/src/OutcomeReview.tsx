import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, RotateCcw, Sparkles, ShieldCheck } from "lucide-react";
import { post, dateLabel } from "./api";
import { useWorkspace } from "./workspace";
import { ErrorBox } from "./ui";
import type { Job, TicketDetail } from "./types";
import { outcomeLabel } from "./CustomerPortal";

export function OutcomeReview({
  detail,
  reload,
}: {
  detail: TicketDetail;
  reload: () => Promise<unknown>;
}) {
  const { refresh, startJob } = useWorkspace();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const ticket = detail.ticket;
  const draft = detail.runs.find((r) => r.id === ticket.draft_run_id);
  useEffect(() => {
    setText("");
    setError("");
    setSuccess("");
  }, [ticket.id]);
  async function action(
    kind: "approve" | "correct" | "request_changes" | "reopen" | "generate",
  ) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      if (kind === "generate") {
        startJob(await post<Job>("/tickets/" + ticket.id + "/resolve"));
        setSuccess("Answer run complete. Review the outcome below.");
      } else {
        await post("/tickets/" + ticket.id + "/review", {
          action: kind,
          expected_version: ticket.outcome_version,
          body: text,
        });
        if (kind === "request_changes") {
          startJob(await post<Job>("/tickets/" + ticket.id + "/resolve"));
          setSuccess(
            "Revision prepared for review. Publish the draft when it is ready.",
          );
        } else
          setSuccess(
            kind === "correct"
              ? "Correction published to the customer."
              : "Review recorded.",
          );
        setText("");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      await Promise.allSettled([reload(), refresh()]);
      setBusy(false);
    }
  }
  function publish(e: FormEvent) {
    e.preventDefault();
    void action("correct");
  }
  return (
    <section className="card outcome-review">
      <div className="card-header">
        <div>
          <span className="eyebrow">RESOLUTION CONTROL</span>
          <h2>{outcomeLabel(ticket.resolution_state)}</h2>
          <p>
            {detail.review_explanation ||
              "Inspect completed answers, publish a correction, or ask AI for a revised draft."}
          </p>
        </div>
        <ShieldCheck size={22} />
      </div>
      <div className="outcome-body">
        <ErrorBox message={error} />
        {success && (
          <p role="status" className="success-box">
            {success}
          </p>
        )}
        {ticket.answer && (
          <div className="published-answer">
            <span className="eyebrow">LATEST CUSTOMER ANSWER</span>
            <p className="pre-wrap">{ticket.answer}</p>
          </div>
        )}
        {draft?.payload.answer && (
          <div className="draft-answer">
            <span className="badge new">Draft · not visible to customer</span>
            <p className="pre-wrap">{draft.payload.answer}</p>
            {draft.stale && (
              <p className="error-box">
                Knowledge changed. Generate a fresh draft before publishing.
              </p>
            )}
            <button
              className="button primary"
              disabled={busy || draft.stale}
              onClick={() => void action("approve")}
            >
              <CheckCircle2 size={16} />
              Publish revised answer
            </button>
          </div>
        )}
        <div className="review-actions">
          <button
            className="button"
            disabled={busy || ticket.resolution_state === "processing"}
            onClick={() => void action("generate")}
          >
            <Sparkles size={16} />
            {ticket.answer ? "Generate revised draft" : "Run resolution"}
          </button>
          {ticket.answer && !draft && ticket.status === "resolved" && (
            <button
              className="button"
              disabled={busy}
              onClick={() => void action("approve")}
            >
              <ShieldCheck size={16} />
              Mark reviewed
            </button>
          )}
        </div>
        <form onSubmit={publish} className="review-compose">
          <label htmlFor="outcome-feedback">
            Correction or revision instructions
          </label>
          <textarea
            id="outcome-feedback"
            rows={3}
            value={text}
            minLength={3}
            maxLength={6000}
            required
            onChange={(e) => setText(e.target.value)}
            placeholder="Write a customer-ready correction, or describe what the AI should change…"
          />
          <div className="review-actions">
            <button
              className="button primary"
              disabled={busy || text.trim().length < 3}
            >
              Publish correction
            </button>
            <button
              type="button"
              className="button"
              disabled={busy || text.trim().length < 3}
              onClick={() => void action("request_changes")}
            >
              Request AI changes
            </button>
            <button
              type="button"
              className="text-button"
              disabled={busy || text.trim().length < 3}
              onClick={() => void action("reopen")}
            >
              <RotateCcw size={14} />
              Reopen for review
            </button>
          </div>
          <p className="small muted">
            Corrections are visible to the customer. Revision instructions stay
            internal. Every change is recorded.
          </p>
        </form>
        {detail.messages.length > 0 && (
          <details className="customer-transcript">
            <summary>
              Customer conversation · {detail.messages.length} messages
            </summary>
            {detail.messages.map((m) => (
              <article key={m.id} className="transcript-message">
                <div className="message-meta">
                  <strong>{m.author}</strong>
                  <span>{dateLabel(m.created_at)}</span>
                </div>
                <p className="pre-wrap">{m.body}</p>
                {m.citations.map((c, i) => (
                  <blockquote key={c.chunk_id + i}>
                    {c.title}: “{c.quote}”
                  </blockquote>
                ))}
              </article>
            ))}
          </details>
        )}
        <details className="escalation-policy">
          <summary>When human review is required</summary>
          <p>
            Account-specific actions, financial approvals, identity recovery,
            security incidents, service outages, privacy or legal requests,
            policy exceptions, explicit human requests, unsuccessful answers,
            and missing or invalid evidence. Routine documented informational
            enquiries are answered automatically.
          </p>
        </details>
      </div>
    </section>
  );
}
