import { getInitData } from "../lib/telegram";
import type { ApiErrorBody } from "../types/api";

export class ApiRequestError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  constructor(code: string, message: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code; this.status = status; this.details = details;
  }
}

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

async function request<T>(path: string, init: RequestInit = {}, withAuth = true): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (withAuth) {
    const initData = getInitData();
    // Real backend verifies HMAC of the raw initData string.
    if (initData) headers.set("X-Telegram-Init-Data", initData);
  }
  let resp: Response;
  try {
    resp = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new ApiRequestError("network_error", "Нет связи с сервером. Попробуйте ещё раз.", 0);
  }
  let body: unknown = null;
  const text = await resp.text();
  if (text) { try { body = JSON.parse(text); } catch { /* non-JSON */ } }
  if (!resp.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    throw new ApiRequestError(
      err?.code ?? "http_error",
      err?.message ?? `Ошибка ${resp.status}`,
      resp.status,
      err?.details ?? {},
    );
  }
  return body as T;
}

export const api = {
  me: () => request<import("../types/api").Me>("/auth/me"),
  catalog: () => request<import("../types/api").Catalog>("/catalog", {}, false),
  createReading: (body: { spread_code: string; theme_code: string; question?: string | null; idempotencyKey: string }) =>
    request<{ reading_id: string; replayed: boolean }>("/readings", { method: "POST", body: JSON.stringify(body) }),
  getReading: (id: string) => request<import("../types/api").ReadingDetail>(`/readings/${id}`),
  history: (cursor?: string | null, limit = 20) =>
    request<import("../types/api").HistoryPage>(`/readings?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  products: () => request<import("../types/api").ProductsResponse>("/premium/products"),
  createPayment: (product_code: string) =>
    request<import("../types/api").PaymentCreate>("/payments/create", { method: "POST", body: JSON.stringify({ product_code }) }),
  paymentStatus: (id: number) => request<{ status: string }>(`/payments/${id}/status`),
};

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
