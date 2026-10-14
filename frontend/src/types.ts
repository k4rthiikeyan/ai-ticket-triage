export type Priority = "low" | "normal" | "high" | "urgent";
export interface Category {
  id: number;
  slug: string;
  name: string;
  queue_id: number;
  keywords: string[];
  active: boolean;
}
export interface Queue {
  id: number;
  name: string;
  active: boolean;
}
export interface Taxonomy {
  categories: Category[];
  queues: Queue[];
}
export interface Ticket {
  id: number;
  subject: string;
  body: string;
  original_subject: string;
  original_body: string;
  revision: number;
  status: "new" | "open" | "resolved";
  category_id: number | null;
  category_name: string | null;
  priority: Priority | null;
  queue_id: number | null;
  queue_name: string | null;
  created_at: string;
  updated_at: string;
}
export interface Source {
  chunk_id: string;
  article_id: string;
  article_revision: number;
  title: string;
  text: string;
  similarity: number;
}
export interface Citation extends Source {
  field: string;
  quote: string;
}
export interface Suggestions {
  category_id: number;
  priority: Priority;
  queue_id: number;
}
export interface Run {
  id: string;
  ticket_revision: number;
  index_version: string | null;
  method: "rag" | "rules";
  model: string;
  outcome: string;
  stale: boolean;
  created_at: string;
  payload: {
    suggestions: Suggestions | null;
    rationales: Record<string, string>;
    scores: Record<string, number>;
    citations: Citation[];
    retrieved: Source[];
    sources: Source[];
    error?: string;
    latency_ms?: number;
  };
}
export interface TicketDetail {
  ticket: Ticket;
  runs: Run[];
  notes: { id: number; body: string; created_at: string }[];
  decisions: {
    id: number;
    action: string;
    note: string;
    created_at: string;
    category_id: number;
    priority: Priority;
    queue_id: number;
    ticket_revision: number;
  }[];
  revisions: {
    revision: number;
    subject: string;
    body: string;
    created_at: string;
  }[];
  audit: {
    id: number;
    action: string;
    detail: Record<string, unknown>;
    actor: string;
    created_at: string;
  }[];
}
export interface Job {
  id: string;
  kind: string;
  ticket_id: number | null;
  status: string;
  progress: string;
  error: string | null;
  result: Record<string, unknown>;
}
export interface System {
  index_ready: boolean;
  index_id: string | null;
  knowledge_version: number;
  indexed_version: number;
  generation_model: string;
  embedding_model: string;
  provider: { available: boolean; message: string };
  busy: boolean;
  jobs: Job[];
}
export interface Dashboard {
  total: number;
  status: Record<string, number>;
  categories: { name: string; count: number }[];
  priorities: { name: string; count: number }[];
  queues: { name: string; count: number }[];
  recent: Ticket[];
}
export interface Article {
  id: string;
  title: string;
  body: string;
  revision: number;
  is_policy: boolean;
  active: boolean;
  updated_at: string;
}
export const priorities: Priority[] = ["low", "normal", "high", "urgent"];
