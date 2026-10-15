import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Layers3,
  LoaderCircle,
  MessageSquare,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { dateLabel } from "./api";
import { ErrorBox } from "./ui";
import type { ConversationMessage, Ticket } from "./types";

type Session = { csrf_token: string; expires_at: string; is_demo: boolean };
type Enquiry = Pick<
  Ticket,
  | "id"
  | "subject"
  | "body"
  | "status"
  | "resolution_state"
  | "outcome_version"
  | "answer"
  | "created_at"
  | "updated_at"
>;
type Detail = { ticket: Enquiry; messages: ConversationMessage[] };

export function outcomeLabel(state: string) {
  return (
    (
      {
        resolved_ai: "Answered by AI",
        resolved_human: "Resolved by support",
        needs_review: "With support",
        changes_requested: "Being reviewed",
        processing: "Finding your answer",
      } as Record<string, string>
    )[state] || "Received"
  );
}

async function portalRequest<T>(
  path: string,
  csrf = "",
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/portal" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Customer-CSRF": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check your enquiry and try again.",
    );
  return data as T;
}

export function CustomerPortal() {
  const [session, setSession] = useState<Session | null>(null);
  const [tickets, setTickets] = useState<Enquiry[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [followup, setFollowup] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [booting, setBooting] = useState(true);
  const initial = useRef<Promise<Session> | null>(null);
  const requestVersion = useRef(0);
  const detailId = detail?.ticket.id;

  useEffect(() => {
    let live = true;
    initial.current ??= portalRequest<Session>("/session", "", "POST");
    initial.current
      .then(async (s) => {
        const rows = await portalRequest<Enquiry[]>("/tickets", s.csrf_token);
        if (live) {
          setSession(s);
          setTickets(rows);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setBooting(false);
      });
    return () => {
      live = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!session) return;
    const [rows, current] = await Promise.all([
      portalRequest<Enquiry[]>("/tickets", session.csrf_token),
      detailId
        ? portalRequest<Detail>("/tickets/" + detailId, session.csrf_token)
        : Promise.resolve(null),
    ]);
    setTickets(rows);
    if (current)
      setDetail((existing) =>
        existing?.ticket.id === current.ticket.id ? current : existing,
      );
  }, [session, detailId]);
  useEffect(() => {
    if (!detailId) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) refresh().catch((e) => setError(e.message));
    }, 10000);
    return () => window.clearInterval(timer);
  }, [detailId, refresh]);

  async function open(ticket: Enquiry) {
    const version = ++requestVersion.current;
    setError("");
    setFollowup("");
    try {
      const next = await portalRequest<Detail>(
        "/tickets/" + ticket.id,
        session!.csrf_token,
      );
      if (version === requestVersion.current) setDetail(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    requestVersion.current++;
    try {
      const next = await portalRequest<Detail>(
        "/tickets",
        session!.csrf_token,
        "POST",
        { subject, body },
      );
      setDetail(next);
      setSubject("");
      setBody("");
      setTickets(
        await portalRequest<Enquiry[]>("/tickets", session!.csrf_token),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reply(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      setDetail(
        await portalRequest<Detail>(
          "/tickets/" + detail.ticket.id + "/followup",
          session!.csrf_token,
          "POST",
          { body: followup, expected_version: detail.ticket.outcome_version },
        ),
      );
      setFollowup("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="support-shell">
      <header className="support-header">
        <Link to="/support" className="brand">
          <span className="brand-mark">
            <Layers3 size={21} />
          </span>
          Triage Desk<span className="portal-wordmark">Support</span>
        </Link>
        <Link to="/" className="button small-button">
          <ShieldCheck size={15} />
          Admin workspace
        </Link>
      </header>
      <div className="support-layout">
        <aside className="support-sidebar">
          <div className="eyebrow">YOUR SUPPORT SPACE</div>
          <button
            className="button primary wide"
            disabled={!session || busy}
            onClick={() => {
              requestVersion.current++;
              setDetail(null);
              setError("");
            }}
          >
            <Plus size={16} />
            New enquiry
          </button>
          <h2>Recent enquiries</h2>
          {tickets.length ? (
            tickets.map((t) => (
              <button
                key={t.id}
                disabled={busy}
                className={
                  "enquiry-item " + (detailId === t.id ? "selected" : "")
                }
                onClick={() => void open(t)}
              >
                <span className="small muted">
                  #{String(t.id).padStart(4, "0")}
                </span>
                <strong>{t.subject}</strong>
                <span className="enquiry-state">
                  {outcomeLabel(t.resolution_state)}
                </span>
              </button>
            ))
          ) : (
            <p className="muted small">Your enquiries will appear here.</p>
          )}
          <div className="support-session">
            <ShieldCheck size={17} />
            <p>
              Private to this browser session.{" "}
              {session
                ? "Access expires " + dateLabel(session.expires_at) + "."
                : "Starting your session…"}{" "}
              Keep this browser session to return to your enquiries.
            </p>
            {session?.is_demo && (
              <>
                <span className="badge new">Isolated demo preview</span>
                <p>Starter guidance describes a fictional product.</p>
              </>
            )}
          </div>
        </aside>
        <main className="support-main">
          <ErrorBox message={error} />
          {booting ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              Opening your support space…
            </div>
          ) : !session ? (
            <div className="empty">
              <h1>Support is unavailable</h1>
              <button
                className="button"
                onClick={() => window.location.reload()}
              >
                Try again
              </button>
            </div>
          ) : !detail ? (
            <>
              <div className="support-intro">
                <span className="support-kicker">
                  <Sparkles size={16} /> Answers grounded in our knowledge
                </span>
                <h1>
                  Let’s get you
                  <br />
                  moving again.
                </h1>
                <p>
                  Tell us what you need. We’ll answer routine questions right
                  away and bring in our support team when your issue needs a
                  person.
                </p>
              </div>
              <form className="card enquiry-form" onSubmit={submit}>
                <div className="card-header">
                  <div>
                    <h2>How can we help?</h2>
                    <p>A little context helps us find the right answer.</p>
                  </div>
                  <MessageSquare size={20} />
                </div>
                <div className="support-fields">
                  <label>
                    Subject
                    <input
                      required
                      minLength={3}
                      maxLength={180}
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      placeholder="A short summary of your question"
                    />
                  </label>
                  <label>
                    Your enquiry
                    <textarea
                      required
                      minLength={10}
                      maxLength={12000}
                      rows={6}
                      value={body}
                      onChange={(e) => setBody(e.target.value)}
                      placeholder="What are you trying to do? Include any error and what you’ve already tried."
                    />
                  </label>
                  <p className="small muted">
                    Use non-sensitive examples. Do not include personal data,
                    passwords, verification codes, or payment details. Relevant
                    passages are processed by free AI providers.
                  </p>
                  <button className="button primary" disabled={busy}>
                    {busy ? (
                      <>
                        <LoaderCircle className="spin" size={17} />
                        Finding your answer…
                      </>
                    ) : (
                      <>
                        Get help
                        <ArrowRight size={17} />
                      </>
                    )}
                  </button>
                  <span className="small muted">
                    You can ask for a person whenever you need one.
                  </span>
                </div>
              </form>
              <div className="support-promises">
                <span>
                  <CheckCircle2 size={16} />
                  Sourced answers
                </span>
                <span>
                  <Clock3 size={16} />
                  Automatic help for routine enquiries
                </span>
                <span>
                  <ShieldCheck size={16} />
                  Human help for exceptions
                </span>
              </div>
            </>
          ) : (
            <>
              <button className="text-button" onClick={() => setDetail(null)}>
                <ArrowLeft size={15} />
                New enquiry
              </button>
              <div className="conversation-heading">
                <span className="eyebrow">
                  ENQUIRY #{String(detail.ticket.id).padStart(4, "0")}
                </span>
                <h1>{detail.ticket.subject}</h1>
                <span
                  className={
                    "outcome-status " +
                    (detail.ticket.status === "resolved" ? "complete" : "")
                  }
                >
                  <span className="status-dot online" />
                  {outcomeLabel(detail.ticket.resolution_state)}
                </span>
                <button
                  className="text-button"
                  onClick={() =>
                    void refresh().catch((e) => setError(e.message))
                  }
                >
                  Refresh
                </button>
              </div>
              <div className="conversation" aria-live="polite">
                {detail.messages.map((m) => (
                  <article key={m.id} className={"message message-" + m.author}>
                    <div className="message-meta">
                      <strong>
                        {m.author === "customer"
                          ? "You"
                          : m.author === "assistant"
                            ? "Triage Desk AI"
                            : m.author === "admin"
                              ? "Support team"
                              : "Support update"}
                      </strong>
                      <span>{dateLabel(m.created_at)}</span>
                      {m.kind === "correction" && (
                        <span className="badge open">Updated answer</span>
                      )}
                    </div>
                    <p className="pre-wrap">{m.body}</p>
                    {m.citations.length > 0 && (
                      <details className="answer-sources">
                        <summary>
                          Sources behind this answer · {m.citations.length}
                        </summary>
                        {m.citations.map((c, i) => (
                          <div key={c.chunk_id + i}>
                            <strong>{c.title}</strong>
                            <blockquote>{c.quote}</blockquote>
                          </div>
                        ))}
                      </details>
                    )}
                  </article>
                ))}
              </div>
              {detail.ticket.status === "resolved" ? (
                <div className="resolution-notice">
                  <CheckCircle2 size={20} />
                  <div>
                    <strong>Your enquiry has been answered.</strong>
                    <p>
                      This ticket is complete. If the answer doesn’t solve your
                      issue, reply below to reopen it with our support team.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="resolution-notice pending">
                  <Clock3 size={20} />
                  <div>
                    <strong>
                      {detail.ticket.resolution_state === "processing"
                        ? "We’re preparing your answer."
                        : "Our support team is reviewing your enquiry."}
                    </strong>
                    <p>
                      Your context is saved. You can add details below; updates
                      appear here.
                    </p>
                  </div>
                </div>
              )}
              <form className="followup-form" onSubmit={reply}>
                <label htmlFor="followup">
                  {detail.ticket.status === "resolved"
                    ? "Still need help?"
                    : "Add a detail for the support team"}
                </label>
                <textarea
                  id="followup"
                  rows={3}
                  minLength={3}
                  maxLength={4000}
                  required
                  value={followup}
                  onChange={(e) => setFollowup(e.target.value)}
                  placeholder="Tell us what needs a closer look…"
                />
                <button className="button" disabled={busy}>
                  {busy ? "Sending…" : "Send to support team"}
                  <ArrowRight size={16} />
                </button>
              </form>
            </>
          )}
          <footer className="support-footer">
            Triage Desk · AI assistance with human accountability
          </footer>
        </main>
      </div>
    </div>
  );
}
