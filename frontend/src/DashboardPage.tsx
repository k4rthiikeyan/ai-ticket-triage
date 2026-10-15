import { Link } from "react-router-dom";
import {
  Layers3,
  Inbox,
  Plus,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  LoaderCircle,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";

import { Loading, PageHeading, TicketTable } from "./ui";
import { useWorkspace } from "./workspace";

export function DashboardPage() {
  const { dashboard, system, newTicket, isDemo } = useWorkspace();
  if (!dashboard) return <Loading />;
  const metrics = [
    {
      label: "New tickets",
      value: dashboard.status.new,
      icon: Inbox,
      description: "Waiting for triage",
      tone: "green",
    },
    {
      label: "Open tickets",
      value: dashboard.status.open,
      icon: LoaderCircle,
      description: "In your team’s queue",
      tone: "blue",
    },
    {
      label: "Resolved tickets",
      value: dashboard.status.resolved,
      icon: CheckCircle2,
      description: "Reviewed and completed",
      tone: "purple",
    },
    {
      label: "Total tickets",
      value: dashboard.total,
      icon: Layers3,
      description: "Across your workspace",
      tone: "gray",
    },
  ];
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE OVERVIEW"
        title="A clearer view of your queue."
        description="Track incoming requests, review recommendations, and keep support moving."
        action={
          <button className="button primary" onClick={newTicket}>
            <Plus size={17} />
            New ticket
          </button>
        }
      />
      <div className="metrics">
        {metrics.map((m) => (
          <div className="metric card" key={m.label}>
            <div className="metric-top">
              <span>{m.label}</span>
              <span className={"metric-icon " + m.tone}>
                <m.icon size={19} />
              </span>
            </div>
            <strong>{m.value}</strong>
            <span className="muted small">{m.description}</span>
          </div>
        ))}
      </div>
      <div className="workspace-banner">
        <div className="banner-icon">
          <Sparkles size={22} />
        </div>
        <div>
          <strong>
            {dashboard.total === 0
              ? "Try triage with your own requests."
              : "Recommendations with a reason."}
          </strong>
          <p>
            {dashboard.total === 0
              ? "Add your support articles and urgency policy, rebuild the index, then create a ticket and run triage."
              : isDemo
                ? "Starter examples are labelled Example. Build the knowledge index, open a ticket, run triage, and inspect the evidence before confirming."
                : "Retrieve relevant knowledge. Inspect the evidence. Make the final call."}
          </p>
        </div>
        <Link to="/knowledge" className="button">
          {system?.index_ready
            ? "Explore knowledge"
            : "Build your knowledge index"}
          <ArrowUpRight size={15} />
        </Link>
      </div>
      <div className="dashboard-grid">
        <section className="card">
          <div className="card-header">
            <div>
              <h2>Tickets by category</h2>
              <p>Confirmed labels across the workspace</p>
            </div>
            <span className="subtle-label">{dashboard.total} tickets</span>
          </div>
          <div className="bar-list">
            {dashboard.categories.map((c, i) => (
              <div className="bar-row" key={c.name}>
                <div>
                  <span>{c.name}</span>
                  <strong>{c.count}</strong>
                </div>
                <div className="bar-track">
                  <span
                    className={
                      i === dashboard.categories.length - 1 ? "neutral" : ""
                    }
                    style={{
                      width:
                        Math.max(
                          0,
                          (c.count / Math.max(dashboard.total, 1)) * 100,
                        ) + "%",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
        <section className="card">
          <div className="card-header">
            <div>
              <h2>Priority breakdown</h2>
              <p>Human-confirmed urgency</p>
            </div>
          </div>
          <div className="priority-list">
            {dashboard.priorities.map((p) => (
              <div key={p.name}>
                <span>
                  <i className={"priority-dot " + p.name.toLowerCase()} />
                  {p.name.charAt(0).toUpperCase() + p.name.slice(1)}
                </span>
                <strong>{p.count}</strong>
                <span className="muted">
                  {Math.round((p.count / Math.max(dashboard.total, 1)) * 100)}%
                </span>
              </div>
            ))}
          </div>
          <div className="card-footer">
            <ShieldCheck size={15} />
            Suggestions count only after confirmation.
          </div>
        </section>
      </div>
      <section className="card recent-card">
        <div className="card-header">
          <div>
            <h2>Recent activity</h2>
            <p>The latest requests in your support workspace</p>
          </div>
          <Link className="text-link" to="/tickets">
            View all tickets
            <ArrowRight size={15} />
          </Link>
        </div>
        <TicketTable tickets={dashboard.recent} />
      </section>
      <div className="queue-strip">
        {dashboard.queues.map((q) => (
          <div key={q.name}>
            <span className="muted">{q.name}</span>
            <strong>{q.count} active</strong>
          </div>
        ))}
      </div>
    </>
  );
}
