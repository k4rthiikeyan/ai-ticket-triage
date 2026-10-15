import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { post } from "./api";
import type { Ticket } from "./types";
import { ErrorBox, Dialog } from "./ui";
import { useWorkspace } from "./workspace";

export function CreateTicket({ close }: { close: () => void }) {
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
