import { useCallback, useEffect, useState } from "react";
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
  ArrowRight,
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
} from "./types";
import { ErrorBox, Loading, PageHeading } from "./ui";
import { WorkspaceContext } from "./workspace";
import { Login } from "./Login";
import { CreateTicket } from "./CreateTicket";
import { DashboardPage } from "./DashboardPage";
import { TicketsPage } from "./TicketsPage";
import { TicketPage } from "./TicketPage";
import { KnowledgePage } from "./KnowledgePage";
import { SettingsPage } from "./SettingsPage";
import { useDemoActivity } from "./useDemoActivity";
import { CustomerPortal } from "./CustomerPortal";
export default function App() {
  const location = useLocation();
  return location.pathname.startsWith("/support") ? (
    <CustomerPortal />
  ) : (
    <AdminApp />
  );
}
function AdminApp() {
  const [user, setUser] = useState<string | null>(null),
    [isDemo, setIsDemo] = useState(false),
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
  useDemoActivity(
    Boolean(user && isDemo),
    system?.demo_limits.idle_minutes ?? 30,
  );
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
    api<{ username: string; csrf_token: string; is_demo: boolean }>("/auth/me")
      .then((data) => {
        if (live) {
          setCsrf(data.csrf_token);
          setUser(data.username);
          setIsDemo(Boolean(data.is_demo));
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
      setIsDemo(false);
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
    if (!user || isDemo) return;
    const timer = window.setInterval(() => {
      if (!document.hidden)
        refresh().catch((e) => setWorkspaceError(e.message));
    }, 15000);
    return () => window.clearInterval(timer);
  }, [user, isDemo, refresh]);
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
      setIsDemo(false);
      setJob(null);
      setDashboard(null);
      navigate("/");
    } catch (e) {
      setWorkspaceError((e as Error).message);
    }
  }
  const context = {
    isDemo,
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
          onLogin={(username, demoAccount) => {
            setBootError("");
            setUser(username);
            setIsDemo(demoAccount);
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
              <span>
                {isDemo ? "Your demo workspace" : "Support operations"}
              </span>
            </div>
          </div>
          <div className="nav-label">WORKSPACE</div>
          <nav>
            <Link
              to="/tickets?resolution=review"
              className={
                location.pathname === "/tickets" &&
                location.search.includes("resolution=review")
                  ? "active"
                  : ""
              }
            >
              <ShieldCheck size={18} />
              Needs review
              <span className="nav-count">
                {(dashboard?.automation.needs_review || 0) +
                  (dashboard?.automation.changes_requested || 0)}
              </span>
            </Link>
            <NavLink to="/" end>
              <LayoutDashboard size={18} />
              Overview
            </NavLink>
            <NavLink
              to="/tickets"
              className={({ isActive }) =>
                isActive && !location.search.includes("resolution=review")
                  ? "active"
                  : ""
              }
            >
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
                <span>{isDemo ? "Demo visitor" : "Administrator"}</span>
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
              Admin workspace
            </div>
            <Link to="/support" className="button small-button">
              Customer portal
              <ArrowUpRight size={14} />
            </Link>
            <span className="avatar small-avatar">A</span>
          </header>
          <main className="page-content">
            {isDemo && (
              <div className="info-strip">
                <ShieldCheck size={17} />
                <span>
                  Your tickets and knowledge are isolated from other visitors.
                  Ending the demo deletes its data and embeddings. An abandoned
                  session expires after {system?.demo_limits.idle_minutes ?? 30}{" "}
                  minutes of inactivity.{" "}
                  {system?.demo_limits.ai_remaining_today ?? "—"} free AI
                  requests available today; indexing, search, and triage share
                  this allowance. Use non-sensitive examples.
                </span>
                <button className="button small-button" onClick={logout}>
                  End demo &amp; delete data
                </button>
              </div>
            )}
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
                Triage Desk <span>·</span>{" "}
                {isDemo ? "Your demo workspace" : "Support workspace"}
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
                    : job.kind === "resolve"
                      ? "Automatic resolution"
                      : job.kind === "revise"
                        ? "Answer revision"
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
