import { useDeferredValue, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Search, ArrowRight } from "lucide-react";
import { api } from "./api";
import { useWorkspace } from "./workspace";
import { ErrorBox, Loading, PageHeading, TicketTable } from "./ui";
import type { Ticket } from "./types";
import { priorities } from "./types";

export function TicketsPage() {
  const { taxonomy, dashboard, newTicket, lastJob } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const resolution = params.get("resolution") || "";
  const [query, setQuery] = useState(""),
    [category, setCategory] = useState(""),
    [priority, setPriority] = useState(""),
    [queue, setQueue] = useState(""),
    [offset, setOffset] = useState(0),
    [data, setData] = useState<{ items: Ticket[]; total: number } | null>(null),
    [error, setError] = useState("");
  const deferred = useDeferredValue(query);
  useEffect(() => {
    setOffset(0);
  }, [deferred, status, category, priority, queue, resolution]);
  useEffect(() => {
    let live = true;
    const p = new URLSearchParams({
      q: deferred,
      status,
      priority,
      offset: String(offset),
      resolution,
    });
    if (category) p.set("category_id", category);
    if (queue) p.set("queue_id", queue);
    api<{ items: Ticket[]; total: number }>("/tickets?" + p)
      .then((d) => {
        if (live) {
          setData(d);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [
    deferred,
    status,
    category,
    priority,
    queue,
    offset,
    lastJob,
    resolution,
  ]);
  return (
    <>
      <PageHeading
        eyebrow="TEAM INBOX"
        title={
          resolution === "review"
            ? "Needs your attention"
            : resolution === "resolved_ai"
              ? "Answered automatically"
              : "All tickets"
        }
        description={
          resolution === "review"
            ? "Exceptions, follow-ups, and revised answers waiting for a person."
            : "Every enquiry and outcome, ready to inspect or improve."
        }
        action={
          <button className="button primary" onClick={newTicket}>
            <Plus size={17} />
            New ticket
          </button>
        }
      />
      <section className="card">
        <div className="ticket-tabs">
          {[
            ["", "All tickets", dashboard?.total],
            ["new", "New", dashboard?.status.new],
            ["open", "Open", dashboard?.status.open],
            ["resolved", "Resolved", dashboard?.status.resolved],
          ].map(([value, label, count]) => (
            <button
              key={String(value)}
              className={status === value ? "active" : ""}
              onClick={() =>
                setParams({
                  ...Object.fromEntries(params),
                  status: String(value),
                })
              }
            >
              {label}
              <span>{count || 0}</span>
            </button>
          ))}
        </div>
        <div className="filter-bar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search tickets"
              placeholder="Search by subject, message, or ticket ID…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select
            aria-label="Filter category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {taxonomy.categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.active ? "" : " (archived)"}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="">All priorities</option>
            {priorities.map((p) => (
              <option key={p} value={p}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter queue"
            value={queue}
            onChange={(e) => setQueue(e.target.value)}
          >
            <option value="">All queues</option>
            {taxonomy.queues.map((q) => (
              <option key={q.id} value={q.id}>
                {q.name}
              </option>
            ))}
          </select>
        </div>
        <ErrorBox message={error} />
        {data ? (
          <TicketTable tickets={data.items} />
        ) : (
          <Loading text="Loading tickets…" />
        )}
        <div className="pagination">
          <span className="muted small">
            {data?.total
              ? `${offset + 1}–${Math.min(offset + 25, data.total)} of ${data.total} tickets`
              : "0 tickets"}
          </span>
          <div>
            <button
              className="button small-button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous
            </button>
            <button
              className="button small-button"
              disabled={!data || offset + 25 >= data.total}
              onClick={() => setOffset(offset + 25)}
            >
              Next
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
