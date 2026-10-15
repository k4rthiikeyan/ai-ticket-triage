import { useEffect, useState, type FormEvent } from "react";

import {
  Layers3,
  BookOpen,
  ArrowRight,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import { api, post, setCsrf } from "./api";

import { ErrorBox } from "./ui";

export function Login({
  onLogin,
}: {
  onLogin: (username: string, isDemo: boolean) => void;
}) {
  const [username, setUsername] = useState("admin"),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<{
    enabled: boolean;
    username?: string;
    password?: string;
  } | null>(null);
  useEffect(() => {
    let live = true;
    api<{ enabled: boolean; username?: string; password?: string }>(
      "/auth/demo",
    )
      .then((data) => {
        if (live) setDemo(data);
      })
      .catch(() => {
        if (live)
          setError(
            "Demo access could not be loaded. Refresh the page or use your workspace credentials.",
          );
      });
    return () => {
      live = false;
    };
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    await signIn(username, password);
  }
  async function signIn(loginUsername: string, loginPassword: string) {
    setBusy(true);
    setError("");
    try {
      const data = await post<{
        username: string;
        csrf_token: string;
        is_demo: boolean;
      }>("/auth/login", { username: loginUsername, password: loginPassword });
      setCsrf(data.csrf_token);
      onLogin(data.username, Boolean(data.is_demo));
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
          <h2>{demo?.enabled ? "Take a look around" : "Welcome back"}</h2>
          <p className="muted">
            {demo?.enabled
              ? "Try the demo, or sign in with your workspace account."
              : "Sign in to review your team’s requests."}
          </p>
          {demo?.enabled && demo.username && demo.password && (
            <section className="demo-access" aria-label="Public demo access">
              <strong>Explore the public demo</strong>
              <p>No account needed. Try the workspace for yourself.</p>
              <dl>
                <div>
                  <dt>Username</dt>
                  <dd>
                    <code>{demo.username}</code>
                  </dd>
                </div>
                <div>
                  <dt>Password</dt>
                  <dd>
                    <code>{demo.password}</code>
                  </dd>
                </div>
              </dl>
              <button
                type="button"
                className="button primary wide"
                disabled={busy}
                onClick={() => {
                  void signIn(demo.username!, demo.password!);
                }}
              >
                Try the demo <ArrowRight size={17} />
              </button>
              <p className="demo-access-note">
                Your own temporary workspace. No other visitor can see your
                tickets or knowledge. Free AI usage limits apply.
              </p>
            </section>
          )}
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
