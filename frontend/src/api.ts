let csrfToken = "";
export function setCsrf(token: string) {
  csrfToken = token;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method || "GET";
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken)
    headers.set("X-CSRF-Token", csrfToken);
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      headers,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(
      "Cannot reach the server. Check your connection and retry.",
      0,
    );
  }
  const data = await response
    .json()
    .catch(() => ({ detail: "The server returned an unreadable response." }));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    const message = Array.isArray(data.detail)
      ? data.detail.map((d: { msg: string }) => d.msg).join(". ")
      : data.detail;
    throw new ApiError(message || "The request failed.", response.status);
  }
  return data as T;
}
export function post<T>(path: string, body?: unknown) {
  return api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
export function patch<T>(path: string, body: unknown) {
  return api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}
export function dateLabel(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + "Z"));
}
export function scoreLabel(score: number | undefined) {
  return score === undefined ? "—" : Math.round(score * 100) + "%";
}
