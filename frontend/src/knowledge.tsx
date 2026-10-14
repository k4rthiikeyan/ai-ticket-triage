import { useEffect, useState, type FormEvent } from "react";
import {
  BookOpen,
  Plus,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Archive,
  Save,
  Layers3,
  Settings2,
  X,
  Search,
} from "lucide-react";
import { api, patch, post, dateLabel } from "./api";
import { useWorkspace } from "./App";
import { PageHeading, ErrorBox, Loading, Dialog, Badge } from "./ui";
import type { Article, Job, Category, Queue, Source } from "./types";

function KnowledgeSearch({ onSelect }: { onSelect: (id: string) => void }) {
  const { system } = useWorkspace();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Source[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setResults(null);
  }, [system?.index_id, system?.index_ready]);
  async function search(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setResults(null);
    try {
      const data = await post<{ items: Source[] }>("/knowledge/search", {
        query,
      });
      setResults(data.items);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card semantic-search">
      <div className="card-header">
        <div>
          <h2>Search your knowledge</h2>
          <p>
            Type a question to find relevant passages with OpenRouter
            embeddings.
          </p>
        </div>
      </div>
      <form className="padded" onSubmit={search}>
        <label>
          Search question
          <input
            required
            minLength={3}
            maxLength={12000}
            placeholder="What would you like to find in your articles?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          className="button primary"
          disabled={busy || !system?.index_ready}
        >
          <Search size={16} />
          {busy ? "Searching…" : "Search knowledge"}
        </button>
        {!system?.index_ready && (
          <p className="small muted">
            Add your articles and rebuild the index to search.
          </p>
        )}
        <ErrorBox message={error} />
      </form>
      {results !== null && (
        <div className="padded" aria-live="polite">
          {results.length === 0 ? (
            <p>
              No passages met the relevance threshold. Try another question or
              add more knowledge.
            </p>
          ) : (
            results.map((source) => (
              <article className="search-result" key={source.chunk_id}>
                <button
                  className="text-link"
                  onClick={() => onSelect(source.article_id)}
                >
                  {source.title}
                </button>
                <span className="small muted">
                  {" "}
                  · {Math.round(source.similarity * 100)}% similarity · v
                  {source.article_revision}
                </span>
                <p className="pre-wrap">{source.text}</p>
              </article>
            ))
          )}
        </div>
      )}
    </section>
  );
}

export function KnowledgePage() {
  const { system, refresh, startJob, lastJob } = useWorkspace();
  const [articles, setArticles] = useState<Article[] | null>(null),
    [selected, setSelected] = useState<string | null>(null),
    [title, setTitle] = useState(""),
    [body, setBody] = useState(""),
    [isPolicy, setIsPolicy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [busy, setBusy] = useState(false),
    [showArchived, setShowArchived] = useState(false),
    [history, setHistory] = useState<
      | {
          revision: number;
          title: string;
          body: string;
          active: boolean;
          created_at: string;
        }[]
      | null
    >(null);
  useEffect(() => {
    let live = true;
    api<Article[]>("/articles")
      .then((a) => {
        if (live) {
          setArticles(a);
          setSelected((prev) => prev ?? a[0]?.id ?? "new");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (lastJob) refresh().catch((e) => setError(e.message));
  }, [lastJob, refresh]);
  const current = articles?.find((a) => a.id === selected);
  useEffect(() => {
    setTitle(current?.title || "");
    setBody(current?.body || "");
    setIsPolicy(current?.is_policy || false);
    setHistory(null);
    setSuccess("");
  }, [selected, current?.revision]);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = current
        ? await patch<Article>("/articles/" + current.id, {
            title,
            body,
            expected_revision: current.revision,
            active: current.active,
          })
        : await post<Article>("/articles", {
            title,
            body,
            is_policy: isPolicy,
          });
      setArticles(await api<Article[]>("/articles"));
      setSelected(saved.id);
      await refresh();
      setSuccess(
        "Article saved. Rebuild the index to use these changes in RAG.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function archive() {
    if (!current) return;
    setBusy(true);
    setError("");
    try {
      await patch("/articles/" + current.id, {
        title: current.title,
        body: current.body,
        active: !current.active,
        expected_revision: current.revision,
      });
      setArticles(await api<Article[]>("/articles"));
      await refresh();
      setSuccess(
        current.active
          ? "Article archived. Rebuild the index to remove it from retrieval."
          : "Article restored. Rebuild the index to include it.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reindex() {
    setBusy(true);
    setError("");
    try {
      startJob(await post<Job>("/knowledge/reindex"));
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="RETRIEVAL FOUNDATION"
        title="Knowledge base"
        description="The articles and policies behind every grounded recommendation."
        action={
          <button
            className="button primary"
            disabled={busy || !!system?.busy}
            onClick={reindex}
          >
            <RefreshCw size={16} />
            Rebuild index
          </button>
        }
      />
      <div className={"index-banner " + (system?.index_ready ? "ready" : "")}>
        <div>
          {system?.index_ready ? (
            <CheckCircle2 size={23} />
          ) : (
            <AlertTriangle size={23} />
          )}
        </div>
        <div>
          <strong>
            {system?.index_ready
              ? "Knowledge index is up to date"
              : system?.index_id
                ? "Changes are waiting to be indexed"
                : "Your knowledge index is ready to build"}
          </strong>
          <p>
            {system?.index_ready
              ? `Indexed version ${system.indexed_version} · ${system.embedding_model}`
              : "Add at least one support article and an urgency policy, then rebuild. Rules and manual decisions are available now."}
          </p>
        </div>
        <span className="subtle-label">
          {articles?.filter((a) => a.active).length || 0} ACTIVE ARTICLES
        </span>
      </div>
      <ErrorBox message={error} />
      {success && (
        <div className="success-box" role="status">
          <CheckCircle2 size={16} />
          {success}
        </div>
      )}
      <KnowledgeSearch onSelect={setSelected} />
      {articles?.length === 0 && (
        <div className="info-strip">
          <BookOpen size={17} />
          Your library is empty. Write your own support guidance below, then add
          a separate article marked as an urgency policy.
        </div>
      )}
      <div className="knowledge-grid">
        <section className="card article-list">
          <div className="card-header">
            <h2>Support library</h2>
            <button
              className="icon-button"
              aria-label="New article"
              onClick={() => setSelected("new")}
            >
              <Plus size={18} />
            </button>
          </div>
          <label className="checkbox-label archive-filter">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            Show archived articles
          </label>
          {articles ? (
            articles
              .filter((a) => showArchived || a.active)
              .map((a) => (
                <button
                  className={
                    "article-item " + (selected === a.id ? "selected" : "")
                  }
                  key={a.id}
                  onClick={() => setSelected(a.id)}
                >
                  <BookOpen size={16} />
                  <div>
                    <strong>{a.title}</strong>
                    <span>
                      {a.is_policy ? "Shared policy" : "Support article"} · v
                      {a.revision}
                      {!a.active ? " · Archived" : ""}
                    </span>
                  </div>
                </button>
              ))
          ) : (
            <Loading />
          )}
        </section>
        <section className="card article-editor">
          <div className="card-header">
            <div>
              <h2>{current ? "Edit article" : "New support article"}</h2>
              <p>
                {current
                  ? `Last updated ${dateLabel(current.updated_at)} · Revision ${current.revision}`
                  : "Write or paste your own support guidance"}
              </p>
            </div>
            {current && (
              <span className="badge new">
                {current.is_policy
                  ? "Policy"
                  : current.active
                    ? "Active"
                    : "Archived"}
              </span>
            )}
          </div>
          <form className="padded" onSubmit={save}>
            {!current && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={isPolicy}
                  onChange={(e) => setIsPolicy(e.target.checked)}
                />
                Use as urgency policy
              </label>
            )}
            {!current && isPolicy && (
              <p className="small muted">
                Define when your team uses low, normal, high, or urgent
                priority. This policy is included in every triage request.
              </p>
            )}
            <label>
              Article title
              <input
                required
                minLength={3}
                maxLength={180}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="A clear, searchable title"
              />
            </label>
            <label>
              Article content <span className="muted">· Markdown text</span>
              <textarea
                className="article-textarea"
                required
                minLength={30}
                maxLength={50000}
                rows={15}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Describe the issue, category guidance, and urgency conditions…"
              />
            </label>
            <div className="editor-help">
              <Layers3 size={16} />
              <span>
                Articles are split into chunks, embedded through OpenRouter, and
                retrieved by similarity. Changes enter retrieval after a
                rebuild.
              </span>
            </div>
            <div className="form-actions spread">
              <div>
                {current && !current.is_policy && (
                  <button
                    className="button"
                    type="button"
                    disabled={busy}
                    onClick={archive}
                  >
                    <Archive size={15} />
                    {current.active ? "Archive article" : "Restore article"}
                  </button>
                )}
              </div>
              <button className="button primary" disabled={busy}>
                <Save size={16} />
                Save article
              </button>
            </div>
          </form>
          {current && (
            <div className="article-history">
              <button
                className="text-link"
                onClick={() =>
                  history
                    ? setHistory(null)
                    : api<typeof history>(
                        "/articles/" + current.id + "/revisions",
                      )
                        .then(setHistory)
                        .catch((e) => setError(e.message))
                }
              >
                {history ? "Hide" : "View"} article revision history
              </button>
              {history?.map((r) => (
                <details key={r.revision}>
                  <summary>
                    Version {r.revision} · {r.active ? "Active" : "Archived"} ·{" "}
                    {dateLabel(r.created_at)}
                  </summary>
                  <strong>{r.title}</strong>
                  <p className="pre-wrap">{r.body}</p>
                </details>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

type Editor =
  | { kind: "category"; item?: Category }
  | { kind: "queue"; item?: Queue };
function TaxonomyEditor({
  editor,
  close,
}: {
  editor: Editor;
  close: () => void;
}) {
  const { taxonomy, refresh } = useWorkspace();
  const [name, setName] = useState(editor.item?.name || ""),
    [queue, setQueue] = useState(
      editor.kind === "category"
        ? String(
            editor.item?.queue_id ||
              taxonomy.queues.find((q) => q.active)?.id ||
              "",
          )
        : "",
    ),
    [keywords, setKeywords] = useState(
      editor.kind === "category" ? editor.item?.keywords.join(", ") || "" : "",
    ),
    [active, setActive] = useState(editor.item?.active ?? true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resource = editor.kind === "category" ? "categories" : "queues";
      const data =
        editor.kind === "category"
          ? {
              name,
              queue_id: Number(queue),
              keywords: keywords
                .split(",")
                .map((w) => w.trim())
                .filter(Boolean),
              active,
            }
          : { name, active };
      if (editor.item) await patch("/" + resource + "/" + editor.item.id, data);
      else await post("/" + resource, data);
      await refresh();
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={(editor.item ? "Edit " : "Create ") + editor.kind}
      onClose={close}
    >
      <form onSubmit={submit}>
        <label>
          Name
          <input
            autoFocus
            required
            minLength={2}
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        {editor.kind === "category" && (
          <>
            <label>
              Default queue
              <select
                value={queue}
                onChange={(e) => setQueue(e.target.value)}
                required
              >
                <option value="">Choose a queue</option>
                {taxonomy.queues
                  .filter((q) => q.active || q.id === editor.item?.queue_id)
                  .map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.name}
                      {q.active ? "" : " (archived)"}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Rules baseline keywords
              <textarea
                rows={3}
                placeholder="Separate keywords or phrases with commas"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
              />
            </label>
            <p className="small muted">
              Keywords affect rules comparison. RAG uses the retrieved knowledge
              and active taxonomy.
            </p>
          </>
        )}
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          Active
        </label>
        <ErrorBox message={error} />
        <div className="form-actions">
          <button className="button" type="button" onClick={close}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            Save {editor.kind}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function SettingsPage() {
  const { taxonomy, system } = useWorkspace();
  const [editor, setEditor] = useState<Editor | null>(null);
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE CONFIGURATION"
        title="Keep triage consistent."
        description="Manage your categories, destination queues, and transparent routing defaults."
      />
      <div className="settings-grid">
        <section className="card">
          <div className="card-header">
            <div>
              <h2>Categories & routing</h2>
              <p>Queue recommendations follow these mappings</p>
            </div>
            <button
              className="button small-button"
              onClick={() => setEditor({ kind: "category" })}
            >
              <Plus size={14} />
              Add category
            </button>
          </div>
          <div className="taxonomy-list">
            {taxonomy.categories.map((c) => (
              <div className="taxonomy-row" key={c.id}>
                <span className="category-icon">
                  <Layers3 size={17} />
                </span>
                <div>
                  <strong>{c.name}</strong>
                  <span>
                    {taxonomy.queues.find((q) => q.id === c.queue_id)?.name ||
                      "Unknown queue"}{" "}
                    · {c.keywords.length} keywords
                    {!c.active ? " · Archived" : ""}
                  </span>
                </div>
                <button
                  className="button small-button"
                  onClick={() => setEditor({ kind: "category", item: c })}
                >
                  Edit
                </button>
              </div>
            ))}
          </div>
        </section>
        <section className="card">
          <div className="card-header">
            <div>
              <h2>Destination queues</h2>
              <p>Logical queues for a single support team</p>
            </div>
            <button
              className="icon-button"
              aria-label="Add queue"
              onClick={() => setEditor({ kind: "queue" })}
            >
              <Plus size={18} />
            </button>
          </div>
          <div className="taxonomy-list">
            {taxonomy.queues.map((q) => (
              <div className="taxonomy-row" key={q.id}>
                <span className="category-icon">
                  <Settings2 size={17} />
                </span>
                <div>
                  <strong>{q.name}</strong>
                  <span>{q.active ? "Active" : "Archived"}</span>
                </div>
                <button
                  className="button small-button"
                  onClick={() => setEditor({ kind: "queue", item: q })}
                >
                  Edit
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="info-strip settings-info">
        <AlertTriangle size={17} />
        Taxonomy changes invalidate earlier recommendations and require an index
        rebuild. Archived records remain in ticket history.
      </div>
      <section className="card runtime-card">
        <div className="card-header">
          <div>
            <h2>OpenRouter inference</h2>
            <p>Free models only · paid routing is blocked</p>
          </div>
          <Badge value={system?.provider.available ? "open" : "new"} />
        </div>
        <dl>
          <div>
            <dt>Generation model</dt>
            <dd>
              <code>{system?.generation_model || "Loading…"}</code>
            </dd>
          </div>
          <div>
            <dt>Embedding model</dt>
            <dd>
              <code>{system?.embedding_model || "Loading…"}</code>
            </dd>
          </div>
          <div>
            <dt>Vector database</dt>
            <dd>SQL database · stored embeddings with cosine search</dd>
          </div>
          <div>
            <dt>Operator account</dt>
            <dd>One configured administrator</dd>
          </div>
        </dl>
        <div className="card-footer">
          {system?.provider.message || "Checking OpenRouter configuration…"}
        </div>
      </section>
      {editor && (
        <TaxonomyEditor editor={editor} close={() => setEditor(null)} />
      )}
    </>
  );
}
