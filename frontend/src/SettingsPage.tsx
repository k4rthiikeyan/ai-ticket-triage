import { useState, type FormEvent } from "react";
import { Plus, AlertTriangle, Layers3, Settings2 } from "lucide-react";
import { patch, post } from "./api";
import { useWorkspace } from "./workspace";
import { PageHeading, ErrorBox, Dialog, Badge } from "./ui";
import type { Category, Queue } from "./types";

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
  const { taxonomy, system, isDemo } = useWorkspace();
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
              disabled={isDemo}
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
                  disabled={isDemo}
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
              disabled={isDemo}
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
                  disabled={isDemo}
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
        {isDemo
          ? "Category and queue settings are managed by the administrator. You can try tickets, articles, and triage in the demo."
          : "Taxonomy changes invalidate earlier recommendations and require an index rebuild. Archived records remain in ticket history."}
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
            <dd>
              {isDemo ? "Public demo visitor" : "Workspace administrator"}
            </dd>
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
