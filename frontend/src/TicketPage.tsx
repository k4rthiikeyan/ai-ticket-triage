import { Recommendation } from "./Recommendation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useParams } from "react-router-dom";
import {
  Plus,
  ArrowLeft,
  ArrowRight,
  Sparkles,
  GitCompareArrows,
  Check,
  ChevronDown,
  Pencil,
  MessageSquare,
  History,
  AlertTriangle,
} from "lucide-react";
import { api, post, patch, dateLabel } from "./api";
import { useWorkspace } from "./workspace";
import { Badge, ErrorBox, Loading } from "./ui";
import type { TicketDetail, Job, Priority } from "./types";
import { priorities } from "./types";

export function TicketPage() {
  const { id } = useParams();
  const { taxonomy, system, startJob, lastJob, refresh, isDemo } =
    useWorkspace();
  const [detail, setDetail] = useState<TicketDetail | null>(null),
    [selectedId, setSelectedId] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [success, setSuccess] = useState("");
  const [editing, setEditing] = useState(false),
    [subject, setSubject] = useState(""),
    [body, setBody] = useState(""),
    [note, setNote] = useState("");
  const [category, setCategory] = useState(""),
    [priority, setPriority] = useState<Priority>("normal"),
    [queue, setQueue] = useState(""),
    [decisionNote, setDecisionNote] = useState(""),
    [manual, setManual] = useState(true);
  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    const d = await api<TicketDetail>("/tickets/" + id);
    if (version === requestVersion.current) setDetail(d);
    return d;
  }, [id]);
  useEffect(() => {
    let live = true;
    setDetail(null);
    setError("");
    load().catch((e) => {
      if (live) setError(e.message);
    });
    return () => {
      live = false;
      requestVersion.current++;
    };
  }, [load]);
  useEffect(() => {
    if (lastJob) load().catch((e) => setError(e.message));
  }, [lastJob, load]);
  useEffect(() => {
    setSelectedId(detail?.runs[0]?.id || "");
  }, [detail?.runs[0]?.id]);
  const selected = detail?.runs.find((r) => r.id === selectedId),
    ticket = detail?.ticket;
  useEffect(() => {
    if (!ticket) return;
    const suggested = selected?.payload.suggestions;
    setCategory(String(suggested?.category_id || ticket.category_id || ""));
    setPriority(suggested?.priority || ticket.priority || "normal");
    setQueue(String(suggested?.queue_id || ticket.queue_id || ""));
    setManual(!suggested || !!selected?.stale);
    setDecisionNote("");
  }, [
    selected?.id,
    ticket?.revision,
    ticket?.category_id,
    ticket?.priority,
    ticket?.queue_id,
  ]);
  async function operation(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await work();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function run(method: "rag" | "rules") {
    await operation(async () => {
      const job = await post<Job>(
        "/tickets/" + id + "/triage?method=" + method,
      );
      startJob(job);
      await refresh();
    });
  }
  async function saveText(e: FormEvent) {
    e.preventDefault();
    await operation(async () => {
      await patch("/tickets/" + id, {
        expected_revision: ticket!.revision,
        subject,
        body,
      });
      setEditing(false);
      await load();
      await refresh();
      setSuccess(
        "Request updated. Earlier recommendations and confirmed labels were invalidated.",
      );
    });
  }
  async function saveDecision(e: FormEvent) {
    e.preventDefault();
    await operation(async () => {
      await post("/tickets/" + id + "/decisions", {
        expected_revision: ticket!.revision,
        category_id: Number(category),
        priority,
        queue_id: Number(queue),
        recommendation_id: manual ? null : selected?.id,
        note: decisionNote,
      });
      await load();
      await refresh();
      setSuccess("Decision confirmed and recorded in the audit trail.");
    });
  }
  async function saveNote(e: FormEvent) {
    e.preventDefault();
    await operation(async () => {
      await post("/tickets/" + id + "/notes", { body: note });
      setNote("");
      await load();
      setSuccess("Internal note added.");
    });
  }
  if (!detail)
    return error ? (
      <ErrorBox message={error} />
    ) : (
      <Loading text="Opening ticket…" />
    );
  const suggestion = selected?.payload.suggestions;
  const working = busy || !!system?.busy;
  const categoryName = (identifier: number | null | undefined) =>
    taxonomy.categories.find((c) => c.id === identifier)?.name || "Untriaged";
  const queueName = (identifier: number | null | undefined) =>
    taxonomy.queues.find((q) => q.id === identifier)?.name || "Unassigned";
  return (
    <>
      <Link className="back-link" to="/tickets">
        <ArrowLeft size={15} />
        Back to tickets
      </Link>
      <div className="ticket-page-heading">
        <div>
          <div className="ticket-title-meta">
            <span className="ticket-id">
              TICKET #{String(ticket!.id).padStart(4, "0")}
            </span>
            <Badge value={ticket!.status} />
          </div>
          <h1>{ticket!.subject}</h1>
          <p className="muted small">
            Created {dateLabel(ticket!.created_at)}
            <span className="middot">·</span>Request revision {ticket!.revision}
          </p>
        </div>
        <button
          className="button"
          disabled={busy || !ticket!.category_id}
          onClick={() =>
            operation(async () => {
              await patch("/tickets/" + id, {
                expected_revision: ticket!.revision,
                status: ticket!.status === "resolved" ? "open" : "resolved",
              });
              await load();
              await refresh();
            })
          }
        >
          <Check size={16} />
          {ticket!.status === "resolved" ? "Reopen ticket" : "Mark resolved"}
        </button>
      </div>
      <ErrorBox message={error} />
      {success && (
        <div className="success-box" role="status">
          <Check size={16} />
          {success}
        </div>
      )}
      <div className="ticket-detail-grid">
        <div className="ticket-main">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>Customer request</h2>
                <p>The context behind this ticket</p>
              </div>
              <button
                className="button small-button"
                onClick={() => {
                  setEditing(!editing);
                  setSubject(ticket!.subject);
                  setBody(ticket!.body);
                }}
              >
                <Pencil size={13} />
                {editing ? "Cancel edit" : "Edit request"}
              </button>
            </div>
            {editing ? (
              <form className="padded" onSubmit={saveText}>
                <label>
                  Subject
                  <input
                    required
                    minLength={3}
                    maxLength={180}
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                  />
                </label>
                <label>
                  Request
                  <textarea
                    required
                    rows={6}
                    minLength={10}
                    maxLength={12000}
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                  />
                </label>
                <p className="small muted">
                  Saving a text change preserves the original, resets confirmed
                  labels, and requires a new decision.
                </p>
                <button className="button primary" disabled={busy}>
                  Save revision
                </button>
              </form>
            ) : (
              <div className="request-body">{ticket!.body}</div>
            )}
            <details className="original-request">
              <summary>
                Original request & text history
                <ChevronDown size={14} />
              </summary>
              <div className="padded">
                <strong>{ticket!.original_subject}</strong>
                <p className="pre-wrap">{ticket!.original_body}</p>
                {detail.revisions.length > 1 &&
                  detail.revisions.map((r) => (
                    <details key={r.revision}>
                      <summary>
                        Revision {r.revision} · {dateLabel(r.created_at)}
                      </summary>
                      <p className="pre-wrap">
                        {r.subject}\n{r.body}
                      </p>
                    </details>
                  ))}
              </div>
            </details>
          </section>
          <section className="card triage-card">
            <div className="card-header">
              <div className="with-icon">
                <span className="ai-icon">
                  <Sparkles size={20} />
                </span>
                <div>
                  <h2>AI triage</h2>
                  <p>Grounded suggestions. Your final decision.</p>
                </div>
              </div>
              <span className="subtle-label">HUMAN REVIEW</span>
            </div>
            <div className="triage-actions">
              <button
                className="button primary"
                disabled={working || !system?.index_ready}
                onClick={() => run("rag")}
              >
                <Sparkles size={16} />
                Run triage
              </button>
              <button
                className="button"
                disabled={working}
                onClick={() => run("rules")}
              >
                <GitCompareArrows size={16} />
                Compare rules
              </button>
              {system?.index_ready ? (
                <span className="small muted">{system.generation_model}</span>
              ) : (
                <Link className="small text-link" to="/knowledge">
                  Rebuild the knowledge index
                  <ArrowRight size={13} />
                </Link>
              )}
            </div>
            {!system?.provider.available && (
              <div className="info-strip">
                <AlertTriangle size={15} />
                {system?.provider.message ||
                  "OpenRouter setup is needed. Rules comparison is available."}
              </div>
            )}
            {detail.runs.length > 0 && (
              <div className="run-selector">
                <label htmlFor="run-history">Recommendation history</label>
                <select
                  id="run-history"
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
                >
                  {detail.runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.method === "rag" ? "RAG" : "Rules"} ·{" "}
                      {dateLabel(r.created_at)} ·{" "}
                      {r.outcome.replaceAll("_", " ")}
                      {r.stale ? " · stale" : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <Recommendation selected={selected} />
          </section>
          <section className="card">
            <div className="card-header">
              <div className="with-icon">
                <MessageSquare size={18} />
                <h2>Internal notes</h2>
              </div>
              <span className="subtle-label">{detail.notes.length}</span>
            </div>
            <form className="note-form" onSubmit={saveNote}>
              <textarea
                aria-label="Internal note"
                placeholder="Add context for the support team…"
                required
                maxLength={4000}
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <button
                className="button small-button"
                disabled={busy || !note.trim()}
              >
                Add note
                <Plus size={14} />
              </button>
            </form>
            {detail.notes.map((n) => (
              <div className="note-entry" key={n.id}>
                <span className="avatar">A</span>
                <div>
                  <strong>
                    {isDemo ? "Demo visitor" : "Administrator"}{" "}
                    <time>{dateLabel(n.created_at)}</time>
                  </strong>
                  <p className="pre-wrap">{n.body}</p>
                </div>
              </div>
            ))}
          </section>
        </div>
        <aside className="ticket-side">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>Confirmed decision</h2>
                <p>Only human-confirmed labels are final</p>
              </div>
            </div>
            <dl className="confirmed-data">
              <div>
                <dt>Category</dt>
                <dd>{ticket!.category_name || "Awaiting review"}</dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>
                  <Badge value={ticket!.priority} />
                </dd>
              </div>
              <div>
                <dt>Queue</dt>
                <dd>{ticket!.queue_name || "Unassigned"}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  <Badge value={ticket!.status} />
                </dd>
              </div>
            </dl>
          </section>
          <section className="card confirmation-card">
            <div className="card-header">
              <div>
                <h2>Review & confirm</h2>
                <p>Accept the suggestion or choose your own</p>
              </div>
            </div>
            <form className="padded" onSubmit={saveDecision}>
              <label>
                Final category
                <select
                  value={category}
                  onChange={(e) => {
                    setCategory(e.target.value);
                    const c = taxonomy.categories.find(
                      (c) => String(c.id) === e.target.value,
                    );
                    if (c) setQueue(String(c.queue_id));
                  }}
                  required
                >
                  <option value="">Choose a category</option>
                  {taxonomy.categories
                    .filter((c) => c.active)
                    .map((c) => (
                      <option value={c.id} key={c.id}>
                        {c.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Final priority
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority)}
                >
                  {priorities.map((p) => (
                    <option value={p} key={p}>
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Final queue
                <select
                  required
                  value={queue}
                  onChange={(e) => setQueue(e.target.value)}
                >
                  <option value="">Choose a queue</option>
                  {taxonomy.queues
                    .filter((q) => q.active)
                    .map((q) => (
                      <option value={q.id} key={q.id}>
                        {q.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Decision note <span className="muted">(optional)</span>
                <textarea
                  rows={3}
                  maxLength={2000}
                  placeholder="Why was this decision made?"
                  value={decisionNote}
                  onChange={(e) => setDecisionNote(e.target.value)}
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={manual}
                  onChange={(e) => setManual(e.target.checked)}
                  disabled={!suggestion || selected?.stale}
                />
                Record as a manual decision
              </label>
              <button
                className="button primary wide"
                disabled={
                  busy || !category || !queue || (!manual && !!selected?.stale)
                }
              >
                <Check size={16} />
                Confirm decision
              </button>
              <p className="small muted confirmation-hint">
                The final labels and any overrides are recorded. No customer
                message is sent.
              </p>
            </form>
          </section>
          <section className="card history-card">
            <div className="card-header">
              <div className="with-icon">
                <History size={17} />
                <h2>Decision history</h2>
              </div>
            </div>
            {detail.decisions.length ? (
              detail.decisions.map((d) => (
                <div className="decision-entry" key={d.id}>
                  <span className="timeline-dot" />
                  <strong>
                    {d.action.charAt(0).toUpperCase() + d.action.slice(1)}{" "}
                    decision
                  </strong>
                  <p>
                    {categoryName(d.category_id)} · {d.priority}
                  </p>
                  <span className="small muted">
                    {dateLabel(d.created_at)} · Request v{d.ticket_revision}
                  </span>
                  {d.note && <p>{d.note}</p>}
                </div>
              ))
            ) : (
              <p className="padded muted small">
                No decisions have been confirmed.
              </p>
            )}
          </section>
          <details className="card audit-card">
            <summary>
              Audit trail <span>{detail.audit.length} events</span>
              <ChevronDown size={14} />
            </summary>
            <div className="audit-list">
              {detail.audit.map((event) => (
                <details key={event.id}>
                  <summary>
                    {event.action.replaceAll("_", " ")}
                    <span>{dateLabel(event.created_at)}</span>
                  </summary>
                  <pre>{JSON.stringify(event.detail, null, 2)}</pre>
                </details>
              ))}
            </div>
          </details>
        </aside>
      </div>
    </>
  );
}
