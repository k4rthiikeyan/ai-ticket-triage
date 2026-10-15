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
      label: "Needs human review",
      value:
        dashboard.automation.needs_review +
        dashboard.automation.changes_requested,
      icon: Inbox,
      description: "Exceptions and follow-ups",
      tone: "green",
    },
    {
      label: "Answered by AI",
      value: dashboard.automation.resolved_ai,
      icon: LoaderCircle,
      description: "Completed without approval",
      tone: "blue",
    },
    {
      label: "Resolved tickets",
      value: dashboard.status.resolved,
      icon: CheckCircle2,
      description: "AI and human outcomes",
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
        eyebrow="SUPPORT OPERATIONS"
        title="More answers. Fewer handoffs."
        description="Routine enquiries finish automatically. Your team handles the moments that need a person."
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
      <div className="operations-links">
        <Link to="/tickets?resolution=review" className="button primary">
          <ShieldCheck size={16} />
          Open review queue
          <ArrowRight size={15} />
        </Link>
        <Link to="/tickets?resolution=resolved_ai" className="button">
          Audit AI answers
        </Link>
        <Link to="/support" className="button">
          Preview customer portal
          <ArrowUpRight size={15} />
        </Link>
      </div>
      <div className="workspace-banner">
        <div className="banner-icon">
          <Sparkles size={22} />
        </div>
        <div>
          <strong>
            {dashboard.total === 0
              ? "Try triage with your own requests."
              : "Every answer remains accountable."}
          </strong>
          <p>
            {dashboard.total === 0
              ? "Add your support articles and urgency policy, rebuild the index, then create a ticket and run triage."
              : isDemo
                ? "Build the knowledge index, then open the customer portal to try automatic answers and exception handling."
                : "Open any completed ticket to inspect sources, publish a correction, or request a revised answer."}
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
              <p>Current classifications across the workspace</p>
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
              <p>Current urgency across all enquiries</p>
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
            Completed AI answers apply their routing labels automatically.
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
