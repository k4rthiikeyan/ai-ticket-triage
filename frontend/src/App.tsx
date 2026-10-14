import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import {
  NavLink,
  Routes,
  Route,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  Layers3,
  LayoutDashboard,
  Inbox,
  BookOpen,
  Settings2,
  LogOut,
  Plus,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  LoaderCircle,
  X,
  Search,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { api, post, setCsrf, ApiError } from "./api";
import type {
  Dashboard as DashboardData,
  Taxonomy,
  System,
  Job,
  Ticket,
} from "./types";
import { ErrorBox, Loading, PageHeading, Dialog, TicketTable } from "./ui";
import { TicketsPage, TicketPage } from "./tickets";
import { KnowledgePage, SettingsPage } from "./knowledge";

type ContextValue = {
  taxonomy: Taxonomy;
  system: System | null;
  dashboard: DashboardData | null;
  refresh: () => Promise<void>;
  startJob: (job: Job) => void;
  lastJob: string;
  newTicket: () => void;
};
const WorkspaceContext = createContext<ContextValue>(null!);
export const useWorkspace = () => useContext(WorkspaceContext);

function Login({ onLogin }: { onLogin: (username: string) => void }) {
  const [username, setUsername] = useState("admin"),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await post<{ username: string; csrf_token: string }>(
        "/auth/login",
        { username, password },
      );
      setCsrf(data.csrf_token);
      onLogin(data.username);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <div className="brand">
          <span className="brand-mark">
            <Layers3 size={23} />
          </span>
          Triage Desk
        </div>
        <span className="story-label">LESS SORTING. MORE SUPPORT.</span>
        <h1>
          Every request.
          <br />A clearer next step.
        </h1>
        <p>
          A thoughtful support workspace that connects tickets to your
          knowledge, then puts the decision in your hands.
        </p>
        <div className="story-cards">
          <div>
            <BookOpen size={20} />
            <strong>Grounded in your knowledge</strong>
            <span>Relevant articles, visible sources.</span>
          </div>
          <div>
            <ShieldCheck size={20} />
            <strong>Always a human decision</strong>
            <span>Review, correct, and confirm.</span>
          </div>
        </div>
        <div className="story-footer">
          Your requests · Your knowledge · OpenRouter-powered triage
        </div>
      </section>
      <section className="login-form">
        <div className="login-form-inner">
          <span className="eyebrow">YOUR SUPPORT WORKSPACE</span>
          <h2>Welcome back</h2>
          <p className="muted">Sign in to review your team’s requests.</p>
          <form onSubmit={submit}>
            <label>
              Username
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <ErrorBox message={error} />
            <button className="button primary wide" disabled={busy}>
              {busy ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                "Sign in to workspace"
              )}
              <ArrowRight size={17} />
            </button>
          </form>
          <p className="login-note">
            Use the administrator username and password configured for this
            workspace.
          </p>
        </div>
      </section>
    </main>
  );
}

function CreateTicket({ close }: { close: () => void }) {
  const [subject, setSubject] = useState(""),
    [body, setBody] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useWorkspace();
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const ticket = await post<Ticket>("/tickets", { subject, body });
      await refresh();
      close();
      navigate("/tickets/" + ticket.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Create a support ticket" onClose={close}>
      <p className="muted">
        Type a request to try triage using your knowledge base. The original
        text is preserved.
      </p>
      <form onSubmit={submit}>
        <label>
          Subject
          <input
            autoFocus
            placeholder="A short summary of the request"
            minLength={3}
            maxLength={180}
            required
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
        </label>
        <label>
          Customer request
          <textarea
            placeholder="Describe the issue, its impact, and any useful context…"
            rows={7}
            minLength={10}
            maxLength={12000}
            required
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
        <ErrorBox message={error} />
        <div className="form-actions">
          <button type="button" className="button" onClick={close}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Create ticket"}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function DashboardPage() {
  const { dashboard, system, newTicket } = useWorkspace();
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

export default function App() {
  const [user, setUser] = useState<string | null>(null),
    [booting, setBooting] = useState(true),
    [bootError, setBootError] = useState("");
  const [taxonomy, setTaxonomy] = useState<Taxonomy>({
      categories: [],
      queues: [],
    }),
    [system, setSystem] = useState<System | null>(null),
    [dashboard, setDashboard] = useState<DashboardData | null>(null),
    [workspaceError, setWorkspaceError] = useState("");
  const [job, setJob] = useState<Job | null>(null),
    [lastJob, setLastJob] = useState(""),
    [createOpen, setCreateOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const refresh = useCallback(async () => {
    const [t, s, d] = await Promise.all([
      api<Taxonomy>("/taxonomy"),
      api<System>("/system"),
      api<DashboardData>("/dashboard"),
    ]);
    setTaxonomy(t);
    setSystem(s);
    setDashboard(d);
    setWorkspaceError("");
  }, []);
  useEffect(() => {
    let live = true;
    api<{ username: string; csrf_token: string }>("/auth/me")
      .then((data) => {
        if (live) {
          setCsrf(data.csrf_token);
          setUser(data.username);
        }
      })
      .catch((e) => {
        if (live && !(e instanceof ApiError && e.status === 401))
          setBootError(e.message);
      })
      .finally(() => {
        if (live) setBooting(false);
      });
    const expire = () => {
      setUser(null);
      setJob(null);
      setCsrf("");
    };
    window.addEventListener("session-expired", expire);
    return () => {
      live = false;
      window.removeEventListener("session-expired", expire);
    };
  }, []);
  useEffect(() => {
    if (user) refresh().catch((e) => setWorkspaceError(e.message));
  }, [user, refresh]);
  useEffect(() => {
    if (!job && system) {
      const active = system.jobs.find((j) =>
        ["queued", "running"].includes(j.status),
      );
      if (active) setJob(active);
    }
  }, [system, job]);
  useEffect(() => {
    if (!job || !["succeeded", "needs_review", "failed"].includes(job.status))
      return;
    setLastJob(job.id);
    refresh().catch((e) => setWorkspaceError(e.message));
    if (job.status === "failed") return;
    const timer = window.setTimeout(() => setJob(null), 6000);
    return () => clearTimeout(timer);
  }, [job?.id, job?.status, refresh]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let live = true;
    let polling = false;
    const id = job.id;
    const timer = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const next = await api<Job>("/jobs/" + id);
        if (!live) return;
        setJob(next);
        if (!["queued", "running"].includes(next.status)) {
          setLastJob(id);
          await refresh();
        }
      } catch (e) {
        if (live) setWorkspaceError((e as Error).message);
      } finally {
        polling = false;
      }
    }, 1000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [job?.id, job?.status, refresh]);
  async function logout() {
    try {
      await post("/auth/logout");
      setCsrf("");
      setUser(null);
      setJob(null);
      setDashboard(null);
      navigate("/");
    } catch (e) {
      setWorkspaceError((e as Error).message);
    }
  }
  const context = {
    taxonomy,
    system,
    dashboard,
    refresh,
    startJob: setJob,
    lastJob,
    newTicket: () => setCreateOpen(true),
  };
  if (booting)
    return (
      <div className="boot">
        <Loading />
      </div>
    );
  if (!user)
    return (
      <>
        <Login
          onLogin={(username) => {
            setBootError("");
            setUser(username);
          }}
        />
        {bootError && (
          <div className="boot-error">
            <ErrorBox message={bootError} />
          </div>
        )}
      </>
    );
  const page = location.pathname.startsWith("/tickets")
    ? "Tickets"
    : location.pathname.startsWith("/knowledge")
      ? "Knowledge base"
      : location.pathname.startsWith("/settings")
        ? "Settings"
        : "Overview";
  return (
    <WorkspaceContext.Provider value={context}>
      <div className="app-shell">
        <aside className="sidebar">
          <Link to="/" className="brand">
            <span className="brand-mark">
              <Layers3 size={21} />
            </span>
            Triage Desk
          </Link>
          <div className="workspace-switch">
            <span className="workspace-avatar">T</span>
            <div>
              <strong>Your support workspace</strong>
              <span>Single-team workspace</span>
            </div>
          </div>
          <div className="nav-label">WORKSPACE</div>
          <nav>
            <NavLink to="/" end>
              <LayoutDashboard size={18} />
              Overview
            </NavLink>
            <NavLink to="/tickets">
              <Inbox size={18} />
              All tickets
              <span className="nav-count">{dashboard?.total || 0}</span>
            </NavLink>
            <NavLink to="/knowledge">
              <BookOpen size={18} />
              Knowledge base
            </NavLink>
            <NavLink to="/settings">
              <Settings2 size={18} />
              Settings
            </NavLink>
          </nav>
          <div className="sidebar-bottom">
            <div className="local-status">
              <span
                className={
                  "status-dot " +
                  (system?.provider.available ? "online" : "offline")
                }
              />
              <strong>
                {system?.provider.available
                  ? "OpenRouter configured"
                  : "OpenRouter setup needed"}
              </strong>
              <span>OpenRouter · Embeddings & LLM</span>
            </div>
            <div className="sidebar-user">
              <span className="avatar">A</span>
              <div>
                <strong>{user}</strong>
                <span>Administrator</span>
              </div>
              <button
                className="icon-button"
                title="Sign out"
                aria-label="Sign out"
                onClick={logout}
              >
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-area">
          <header className="topbar">
            <div className="breadcrumb">
              Workspace<span>/</span>
              <strong>{page}</strong>
            </div>
            <Link to="/tickets" className="top-search">
              <Search size={16} />
              Find a ticket<span>⌕</span>
            </Link>
            <div className="local-pill">
              <span className="status-dot online" />
              Support workspace
            </div>
            <span className="avatar small-avatar">A</span>
          </header>
          <main className="page-content">
            <ErrorBox message={workspaceError} />
            {workspaceError && (
              <button
                className="button small-button"
                onClick={() =>
                  refresh().catch((e) => setWorkspaceError(e.message))
                }
              >
                Retry connection
              </button>
            )}
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/tickets" element={<TicketsPage />} />
              <Route path="/tickets/:id" element={<TicketPage />} />
              <Route path="/knowledge" element={<KnowledgePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route
                path="*"
                element={
                  <PageHeading
                    eyebrow="NOT FOUND"
                    title="This page isn’t here."
                    description="Choose a page from the workspace navigation."
                    action={
                      <Link to="/" className="button">
                        Go to overview
                      </Link>
                    }
                  />
                }
              />
            </Routes>
            <footer className="page-footer">
              <span>
                Triage Desk <span>·</span> Synthetic demo workspace
              </span>
              <a href="/api/docs" target="_blank" rel="noreferrer">
                API documentation
                <ArrowUpRight size={12} />
              </a>
            </footer>
          </main>
        </div>
        {createOpen && <CreateTicket close={() => setCreateOpen(false)} />}{" "}
        {job && (
          <div
            className={"job-toast " + (job.status === "failed" ? "failed" : "")}
            role="status"
          >
            <div>
              {["running", "queued"].includes(job.status) ? (
                <LoaderCircle size={20} className="spin" />
              ) : job.status === "failed" ? (
                <AlertCircle size={20} />
              ) : (
                <CheckCircle2 size={20} />
              )}
            </div>
            <div>
              <strong>
                {job.kind === "reindex"
                  ? "Knowledge index"
                  : job.kind === "rag"
                    ? "RAG triage"
                    : "Rules comparison"}
              </strong>
              <p>{job.error || job.progress}</p>
              {job.ticket_id && (
                <Link to={"/tickets/" + job.ticket_id}>
                  Open ticket
                  <ArrowRight size={12} />
                </Link>
              )}
            </div>
            {!["running", "queued"].includes(job.status) && (
              <button
                className="icon-button"
                aria-label="Dismiss job notification"
                onClick={() => setJob(null)}
              >
                <X size={17} />
              </button>
            )}
          </div>
        )}
      </div>
    </WorkspaceContext.Provider>
  );
}
