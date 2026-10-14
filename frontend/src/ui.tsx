import { useEffect, useRef, type ReactNode } from "react";
import { LoaderCircle, X, Inbox, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { Ticket } from "./types";
import { dateLabel } from "./api";

export function Badge({ value }: { value: string | null | undefined }) {
  return (
    <span className={"badge " + (value || "untriaged")}>
      {value ? value.charAt(0).toUpperCase() + value.slice(1) : "Untriaged"}
    </span>
  );
}
export function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div role="alert" className="error-box">
      {message}
    </div>
  ) : null;
}
export function Loading({ text = "Loading workspace…" }: { text?: string }) {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={20} />
      {text}
    </div>
  );
}
export function Empty({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="empty">
      <Inbox size={28} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog ref={ref} className="dialog" onCancel={onClose} aria-label={title}>
      <div className="dialog-heading">
        <h2>{title}</h2>
        <button
          className="icon-button"
          type="button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function TicketTable({ tickets }: { tickets: Ticket[] }) {
  return tickets.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Status</th>
            <th>Category</th>
            <th>Priority</th>
            <th>Updated</th>
            <th>
              <span className="sr-only">Open ticket</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td className="ticket-subject">
                <Link to={"/tickets/" + t.id}>
                  <span className="ticket-id">
                    #{String(t.id).padStart(4, "0")}
                  </span>
                  <strong>{t.subject}</strong>
                </Link>
              </td>
              <td>
                <Badge value={t.status} />
              </td>
              <td className="muted">{t.category_name || "Awaiting review"}</td>
              <td>
                <Badge value={t.priority} />
              </td>
              <td className="muted nowrap">{dateLabel(t.updated_at)}</td>
              <td>
                <Link
                  className="table-arrow"
                  aria-label={"Open ticket " + t.id}
                  to={"/tickets/" + t.id}
                >
                  <ArrowUpRight size={17} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty
      title="No tickets here"
      description="Try another filter or create your first ticket."
    />
  );
}
