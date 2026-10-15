import { useEffect, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { post } from "./api";
import { useWorkspace } from "./workspace";
import { ErrorBox } from "./ui";
import type { Source } from "./types";

export function KnowledgeSearch({
  onSelect,
}: {
  onSelect: (id: string) => void;
}) {
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
